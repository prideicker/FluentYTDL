from __future__ import annotations

import asyncio
import http.cookiejar
import os
import random
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, cast

from fluentytdl.utils.logger import get_logger
from fluentytdl.utils.paths import find_bundled_executable, is_frozen, locate_runtime_tool
from .config_manager import config_manager
from .yt_dlp_cli import YtDlpCancelled, resolve_yt_dlp_exe, run_dump_single_json, run_version


LogCallback = Callable[[str, str], None]


@dataclass(slots=True)
class YtDlpAuthOptions:
    """Authentication inputs.

    Priority: cookies_file > cookies_from_browser.
    """

    cookies_file: str | None = None
    cookies_from_browser: str | None = None  # e.g. "chrome", "edge"


@dataclass(slots=True)
class AntiBlockingOptions:
    """Anti-blocking / anti-bot options."""

    rotate_user_agent: bool = True
    player_clients: tuple[str, ...] = ("android", "ios", "web")
    sleep_interval_min: int = 1
    sleep_interval_max: int = 5


@dataclass(slots=True)
class NetworkOptions:
    proxy: str | None = None  # http/socks5
    socket_timeout: int = 15
    retries: int = 10
    fragment_retries: int = 10


@dataclass(slots=True)
class YoutubeServiceOptions:
    auth: YtDlpAuthOptions = field(default_factory=YtDlpAuthOptions)
    anti_blocking: AntiBlockingOptions = field(default_factory=AntiBlockingOptions)
    network: NetworkOptions = field(default_factory=NetworkOptions)


class YoutubeService:
    """Singleton service that wraps yt-dlp calls.

    Stage 1 scope:
    - Cookies injection (cookies.txt and cookies-from-browser)
    - Anti-blocking (random UA, mobile client simulation, random sleep)
    - Proxy
    - Async API via asyncio.to_thread (UI thread must never block)
    """

    _instance: "YoutubeService | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "YoutubeService":
        if cls._instance is not None:
            return cls._instance
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._logger = get_logger("fluentytdl.YoutubeService")
        self._log_callback: LogCallback | None = None

    def set_log_callback(self, callback: LogCallback | None) -> None:
        """UI layer can subscribe to logs later (Stage 2+)."""

        self._log_callback = callback

    def _emit_log(self, level: str, message: str) -> None:
        if self._log_callback is not None:
            try:
                self._log_callback(level, message)
            except Exception:
                # Never let UI callback break core logic
                pass
        getattr(self._logger, level.lower(), self._logger.info)(message)

    def _random_user_agent(self) -> str:
        # Keep this list short and realistic; expand later if needed.
        user_agents: list[str] = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        ]
        return random.choice(user_agents)

    def build_ydl_options(self, options: YoutubeServiceOptions | None = None) -> dict[str, Any]:
        """Construct yt-dlp options with anti-blocking and auth."""

        options = options or YoutubeServiceOptions()

        # --- Global config (SettingsPage) ---
        download_dir = str(config_manager.get("download_dir"))
        if download_dir:
            try:
                Path(download_dir).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        anti = options.anti_blocking
        auth = options.auth
        net = options.network

        ydl_opts: dict[str, Any] = {
            # Base
            "quiet": True,
            "no_warnings": True,
            # For single-video parsing we must NOT ignore errors; otherwise yt-dlp may return None/False
            # and we lose the real failure reason (e.g. cookies required).
            "ignoreerrors": False,
            # Anti-blocking
                # Anti-blocking
                # NOTE: Do NOT force youtube "player_client" simulation via extractor_args.
                # Some videos may return an incomplete/empty format list under android/ios
                # simulation, causing "Requested format is not available".
                # Let yt-dlp choose the most stable default (web) extractor behavior.
            # Random delay for batch/playlist
            "sleep_interval": int(anti.sleep_interval_min),
            "max_sleep_interval": int(anti.sleep_interval_max),
            # Network
            "socket_timeout": int(net.socket_timeout),
            "retries": int(net.retries),
            "fragment_retries": int(net.fragment_retries),
            # Download output
            "outtmpl": str(Path(download_dir) / "%(title)s.%(ext)s") if download_dir else "%(title)s.%(ext)s",
        }

        self._maybe_configure_youtube_js_runtime(ydl_opts)

        if anti.rotate_user_agent:
            ydl_opts["user_agent"] = self._random_user_agent()

        # Proxy: options.network.proxy > SettingsPage proxy
        proxy_mode = str(config_manager.get("proxy_mode") or "off").lower().strip()
        proxy_url = str(config_manager.get("proxy_url") or "").strip()
        if net.proxy:
            ydl_opts["proxy"] = net.proxy
        elif proxy_mode == "off":
            # Important: On Windows, some environments may have system/ambient proxy settings.
            # If user selects OFF, explicitly disable proxies for yt-dlp.
            # Equivalent to CLI: --proxy ""
            ydl_opts["proxy"] = ""
        elif proxy_mode == "system":
            # system: do not override, allow ambient/system proxies
            pass
        else:
            # manual http/socks5
            if proxy_url:
                lower = proxy_url.lower()
                if lower.startswith("http://") or lower.startswith("https://") or lower.startswith("socks5://"):
                    ydl_opts["proxy"] = proxy_url
                else:
                    scheme = "socks5" if proxy_mode == "socks5" else "http"
                    ydl_opts["proxy"] = f"{scheme}://{proxy_url}"
            else:
                ydl_opts["proxy"] = ""

        # Cookies: options.auth overrides SettingsPage.
        # - cookie_mode=file: only load cookiefile if it exists AND looks like Netscape format
        # - cookie_mode=browser: use cookiesfrombrowser as a fallback (Windows DPAPI can be flaky)
        has_valid_cookie = False

        cookiefile = (auth.cookies_file or "").strip() or None
        cookies_from_browser = (auth.cookies_from_browser or "").strip() or None

        cookie_mode = "file" if cookiefile else ("browser" if cookies_from_browser else str(config_manager.get("cookie_mode") or "browser"))
        config_cookie_file = str(config_manager.get("cookie_file") or "").strip() or None
        config_cookie_browser = str(config_manager.get("cookie_browser") or "chrome").strip() or None

        if cookie_mode == "file" and not cookiefile:
            cookiefile = config_cookie_file
        if cookie_mode == "browser" and not cookies_from_browser:
            cookies_from_browser = config_cookie_browser

        cookie_exists = bool(cookiefile and os.path.exists(cookiefile))
        self._emit_log(
            "info",
            f"[DEBUG] CookieMode={cookie_mode}, CookieFile={cookiefile or ''}, Exists={cookie_exists}",
        )

        if cookie_mode == "file" and cookiefile:
            if os.path.exists(cookiefile):
                if self._is_probably_json_cookie_file(cookiefile):
                    self._emit_log(
                        "error",
                        "Cookies 文件疑似为 JSON 格式，yt-dlp 只支持 Netscape HTTP Cookie File 格式；已忽略该文件。",
                    )
                else:
                    yt_cookie_count = self._count_youtube_related_cookies(cookiefile)
                    if yt_cookie_count <= 0:
                        self._emit_log(
                            "warning",
                            "已读取 cookies.txt，但未发现 YouTube/Google 域相关 cookies。"
                            "请确认是在 youtube.com 登录后导出，且为 Netscape 格式。",
                        )
                    else:
                        ydl_opts["cookiefile"] = cookiefile
                        has_valid_cookie = True
                        self._emit_log(
                            "info",
                            f"✅ 已加载 Cookie 文件: {cookiefile} (YouTube/Google cookies: {yt_cookie_count})",
                        )
            else:
                self._emit_log("warning", f"Cookies 文件不存在: {cookiefile}")
        elif cookie_mode == "browser" and cookies_from_browser:
            # Note: this may fail on Windows with DPAPI errors depending on browser updates.
            ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)
            has_valid_cookie = True
            self._emit_log("warning", f"使用浏览器 Cookies（Windows 上可能不稳定）: {cookies_from_browser}")

        # --- Smart client switching ---
        # With Cookies: keep yt-dlp default (web) extractor behavior (best for 4K/Premium).
        # Without Cookies: enable android/ios simulation to reduce throttling, but quality/format
        # availability may be limited depending on video/account.
        if not has_valid_cookie:
            ydl_opts["extractor_args"] = {
                "youtube": {
                    # yt-dlp extractor args expect comma-separated values (same as CLI syntax)
                    "player_client": ["android,ios"],
                    "player_skip": ["js,configs,hls"],
                }
            }
            self._emit_log("warning", "未检测到有效 Cookies，启用 Android/iOS 模拟（可能缺失部分高画质）")
        else:
            self._emit_log("info", "🚀 Cookies 模式激活：使用 Web 默认客户端获取更完整的格式列表")

        # --- Optional: YouTube PO Token ---
        # Context: YouTube is rolling out PO Token enforcement. yt-dlp recommends using
        # the `mweb` client together with a PO Token when default clients fail.
        po_token = str(config_manager.get("youtube_po_token") or "").strip()
        if po_token:
            extractor_args = cast(dict[str, Any], ydl_opts.setdefault("extractor_args", {}))
            youtube_args = cast(dict[str, Any], extractor_args.setdefault("youtube", {}))

            # PO Token for mweb.gvs is typically session-bound; cookies are usually required.
            if not has_valid_cookie:
                self._emit_log(
                    "warning",
                    "已配置 PO Token，但当前未加载有效 Cookies。mweb.gvs PO Token 通常需要配合 cookies 使用。",
                )

            # Prefer adding mweb as a fallback client when token is present.
            # Use a single comma-separated value to match yt-dlp syntax.
            youtube_args["player_client"] = ["default,mweb"]
            youtube_args["po_token"] = [po_token]
            # Remove aggressive skips that are intended for no-cookie mobile simulation.
            # With PO Token, we want the most browser-like, complete extraction.
            youtube_args.pop("player_skip", None)
            self._emit_log("info", "🔐 已注入 YouTube PO Token：将优先尝试 mweb 客户端")

        # FFmpeg location
        ffmpeg_path = str(config_manager.get("ffmpeg_path") or "").strip()
        if ffmpeg_path:
            try:
                if Path(ffmpeg_path).exists():
                    ydl_opts["ffmpeg_location"] = ffmpeg_path
                else:
                    self._emit_log("warning", f"FFmpeg 自定义路径无效，已忽略并回退自动检测: {ffmpeg_path}")
            except Exception:
                self._emit_log("warning", f"FFmpeg 自定义路径无效，已忽略并回退自动检测: {ffmpeg_path}")
        elif is_frozen():
            bundled_ffmpeg = find_bundled_executable(
                # New layout (preferred): dist/_internal/ffmpeg/ffmpeg.exe
                "ffmpeg.exe",
                # Legacy layout(s): assets/bin/ffmpeg/ffmpeg.exe
                "ffmpeg/ffmpeg.exe",
            )
            if bundled_ffmpeg is not None:
                # yt-dlp accepts either the ffmpeg.exe path or its containing folder.
                ydl_opts["ffmpeg_location"] = str(bundled_ffmpeg)
                self._emit_log("info", f"已启用内置 FFmpeg: {bundled_ffmpeg}")

        return ydl_opts

    def _maybe_configure_youtube_js_runtime(self, ydl_opts: dict[str, Any]) -> None:
        """Configure yt-dlp external JS runtime (YouTube EJS).

        Context: yt-dlp issue #15012 — YouTube support without an external JS runtime
        is deprecated and may miss formats (especially for logged-in users).
        """

        preferred = str(config_manager.get("js_runtime") or "auto").strip().lower()
        runtime_path = str(config_manager.get("js_runtime_path") or "").strip() or None
        runtime_path_ok = None
        if runtime_path:
            try:
                if Path(runtime_path).exists():
                    runtime_path_ok = runtime_path
            except Exception:
                runtime_path_ok = None

        # yt-dlp uses these runtime ids; quickjs binary is usually "qjs"
        runtime_candidates: list[tuple[str, list[str]]] = [
            ("deno", ["deno"]),
            ("node", ["node"]),
            ("bun", ["bun"]),
            ("quickjs", ["qjs", "quickjs"]),
        ]

        def is_available(runtime_id: str) -> bool:
            if runtime_path_ok and preferred == runtime_id:
                return True

            # Frozen build: prefer bundled runtimes under assets/bin
            if is_frozen():
                if runtime_id == "deno":
                    return (
                        find_bundled_executable(
                            "deno.exe",
                            "js/deno.exe",
                            "deno/deno.exe",
                        )
                        is not None
                    )
                if runtime_id == "node":
                    return (
                        find_bundled_executable(
                            "node.exe",
                            "js/node.exe",
                            "node/node.exe",
                        )
                        is not None
                    )
                if runtime_id == "bun":
                    return (
                        find_bundled_executable(
                            "bun.exe",
                            "js/bun.exe",
                            "bun/bun.exe",
                        )
                        is not None
                    )
                if runtime_id == "quickjs":
                    return (
                        find_bundled_executable(
                            "qjs.exe",
                            "js/qjs.exe",
                            "quickjs/qjs.exe",
                        )
                        is not None
                    )

            for rid, names in runtime_candidates:
                if rid != runtime_id:
                    continue
                return any(shutil.which(n) for n in names)
            return False

        def bundled_runtime_path(runtime_id: str) -> str | None:
            if not is_frozen():
                return None
            if runtime_id == "deno":
                p = find_bundled_executable("deno.exe", "js/deno.exe", "deno/deno.exe")
                return str(p) if p is not None else None
            if runtime_id == "node":
                p = find_bundled_executable("node.exe", "js/node.exe", "node/node.exe")
                return str(p) if p is not None else None
            if runtime_id == "bun":
                p = find_bundled_executable("bun.exe", "js/bun.exe", "bun/bun.exe")
                return str(p) if p is not None else None
            if runtime_id == "quickjs":
                p = find_bundled_executable("qjs.exe", "js/qjs.exe", "quickjs/qjs.exe")
                return str(p) if p is not None else None
            return None

        # If user specifies a runtime explicitly, honor it.
        if preferred in {"deno", "node", "bun", "quickjs"}:
            if is_available(preferred):
                cfg: dict[str, Any] = {}
                cfg["path"] = runtime_path_ok or bundled_runtime_path(preferred) or ""
                if not cfg["path"]:
                    cfg.pop("path", None)
                ydl_opts["js_runtimes"] = {preferred: cfg}
                self._emit_log("info", f"已启用 JS runtime: {preferred}")
            else:
                self._emit_log(
                    "warning",
                    f"未找到 JS runtime: {preferred}。请安装并加入 PATH（推荐 deno），或在设置中填写可执行文件路径。",
                )
            return

        # Auto mode:
        # - If we ship a bundled deno, use it.
        if is_frozen():
            deno = bundled_runtime_path("deno")
            if deno:
                ydl_opts["js_runtimes"] = {"deno": {"path": deno}}
                self._emit_log("info", f"已启用内置 JS runtime: deno ({deno})")
                return

        # - If deno exists on PATH, do nothing (yt-dlp default enables deno).
        if any(shutil.which(n) for n in ["deno"]):
            return

        # - If deno is installed via winget but not on PATH, try to locate it.
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            try:
                winget_packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
                if winget_packages.exists():
                    matches = list(winget_packages.glob("DenoLand.Deno_*\\deno.exe"))
                    if matches:
                        deno_path = str(matches[0])
                        ydl_opts["js_runtimes"] = {"deno": {"path": deno_path}}
                        self._emit_log(
                            "warning",
                            f"检测到 winget 安装的 deno，但未在 PATH 中；已自动使用: {deno_path}",
                        )
                        return
            except Exception:
                pass

        # - Else, try other runtimes by order of recommendation.
        for runtime_id in ["node", "bun", "quickjs"]:
            if is_available(runtime_id):
                cfg: dict[str, Any] = {}
                # Auto 模式下不使用 js_runtime_path（避免用户填了 deno 路径却意外套到 node/bun 上）
                cfg["path"] = bundled_runtime_path(runtime_id) or ""
                if not cfg["path"]:
                    cfg.pop("path", None)
                ydl_opts["js_runtimes"] = {runtime_id: cfg}
                self._emit_log(
                    "warning",
                    f"未检测到 deno，已自动启用 {runtime_id} 作为 JS runtime（建议优先安装 deno）。",
                )
                return

        self._emit_log(
            "warning",
            "未检测到任何受支持的 JS runtime（deno/node/bun/quickjs）。YouTube 解析可能缺失大量格式。建议安装 deno 并加入 PATH。",
        )

    @staticmethod
    def _is_probably_json_cookie_file(path: str) -> bool:
        """Heuristic: exported cookies must be Netscape format (plain text), not JSON."""

        try:
            with open(path, "rb") as f:
                head = f.read(2048)
            text = head.decode("utf-8", errors="ignore").lstrip()
            if not text:
                return False
            # Common JSON exports start with '{' or '['
            if text[0] in "[{":
                return True
            # Netscape cookie file typically starts with a comment header.
            if text.startswith("# Netscape HTTP Cookie File"):
                return False
            return False
        except Exception:
            return False

    @staticmethod
    def _count_youtube_related_cookies(path: str) -> int:
        """Count YouTube/Google related cookies in a Netscape cookie file."""

        try:
            jar = http.cookiejar.MozillaCookieJar()
            jar.load(path, ignore_discard=True, ignore_expires=True)
            count = 0
            for c in jar:
                domain = (c.domain or "").lower()
                if "youtube" in domain or "google" in domain:
                    count += 1
            return count
        except Exception:
            return 0

    def extract_info_sync(
        self,
        url: str,
        options: YoutubeServiceOptions | None = None,
        *,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Blocking metadata extraction (call from worker thread)."""

        ydl_opts = self.build_ydl_options(options)

        try:
            _ = locate_runtime_tool("yt-dlp.exe", "yt-dlp/yt-dlp.exe", "yt_dlp/yt-dlp.exe")
        except FileNotFoundError:
            raise FileNotFoundError("未找到 yt-dlp.exe。请在设置页指定路径，或将 yt-dlp.exe 放入 _internal/yt-dlp/，或加入 PATH。")

        def _do_extract(opts: dict[str, Any]) -> dict[str, Any]:
            self._emit_log("info", f"[EXE] 开始解析 URL: {url}")
            info = run_dump_single_json(url, opts, extra_args=["--no-playlist"], cancel_event=cancel_event)
            if info is None or info is False:
                raise RuntimeError(
                    "解析失败：yt-dlp 未返回有效元数据（可能被要求登录/验证）。"
                    "请在弹窗中启用浏览器 Cookies 重试。"
                )
            if not isinstance(info, dict):
                raise RuntimeError(f"yt-dlp returned unexpected info type: {type(info)!r}")
            return cast(dict[str, Any], info)

        try:
            self._emit_log("info", f"开始解析 URL: {url}")
            return _do_extract(ydl_opts)
        except Exception as exc:
            if isinstance(exc, YtDlpCancelled):
                raise
            msg = str(exc)
            lower = msg.lower()

            # Auto fallback: cookiefile -> cookies-from-browser
            # Wiki context: YouTube rotates cookies frequently; reading directly from browser
            # can be fresher than a stale exported cookie file.
            if ("not a bot" in lower or "sign in" in lower) and "cookiefile" in ydl_opts and "cookiesfrombrowser" not in ydl_opts:
                browser = str(config_manager.get("cookie_browser") or "").strip() or None
                if browser:
                    try:
                        retry_opts = dict(ydl_opts)
                        retry_opts.pop("cookiefile", None)
                        retry_opts["cookiesfrombrowser"] = (browser,)
                        self._emit_log(
                            "warning",
                            f"检测到风控提示，自动改用浏览器 Cookies 重试: {browser}",
                        )
                        return _do_extract(retry_opts)
                    except Exception as retry_exc:
                        if isinstance(retry_exc, YtDlpCancelled):
                            raise
                        # Keep original error message, but append retry result for diagnosis.
                        retry_msg = str(retry_exc)
                        msg = msg + f"\n\n(已自动用 cookies-from-browser:{browser} 重试，但仍失败: {retry_msg})"
                        lower = msg.lower()

            if "not a bot" in lower or "sign in" in lower:
                proxy_mode = str(config_manager.get("proxy_mode") or "off").lower().strip()
                proxy_url = str(config_manager.get("proxy_url") or "").strip()
                if proxy_mode in {"http", "socks5"} and proxy_url:
                    msg = (
                        msg
                        + "\n\n提示: 检测到已启用代理，部分代理/出口 IP 会显著增加 YouTube 风控概率。"
                        + "建议在设置中临时关闭代理后重试解析。"
                    )
                msg = (
                    msg
                    + "\n\n提示: YouTube 会在浏览器标签页中频繁轮换账号 cookies。官方建议用无痕/隐私窗口登录后导出 youtube.com cookies，并立即关闭无痕窗口，以避免 cookies 被轮换。"
                    + "\n提示: YouTube 正在逐步强制 PO Token。若仅靠 cookies 仍触发验证，可在设置中填写 PO Token，并让 yt-dlp 走 mweb 客户端（官方推荐路径）。"
                )

            self._emit_log("error", f"解析失败: {msg}")
            raise RuntimeError(msg) from exc

    def extract_info_for_dialog_sync(
        self,
        url: str,
        options: YoutubeServiceOptions | None = None,
        *,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Metadata extraction tuned for UI dialogs.

        Goals:
        - single video: keep full formats list (for manual format selection)
        - playlist: enumerate entries fast without per-entry deep extraction
        """

        ydl_opts = self.build_ydl_options(options)
        tuned = dict(ydl_opts)

        tuned.update(
            {
                "skip_download": True,
                # yt-dlp supports string modes; "in_playlist" keeps single-video extraction intact
                "extract_flat": "in_playlist",
                "lazy_playlist": True,
                "ignoreerrors": False,
            }
        )

        if bool(config_manager.get("playlist_skip_authcheck") or False):
            tuned = self._with_youtubetab_skip_authcheck(tuned)

        self._emit_log("info", f"[DialogExtract] 开始解析: {url}")

        try:
            _ = locate_runtime_tool("yt-dlp.exe", "yt-dlp/yt-dlp.exe", "yt_dlp/yt-dlp.exe")
        except FileNotFoundError:
            raise FileNotFoundError("未找到 yt-dlp.exe。请在设置页指定路径，或将 yt-dlp.exe 放入 _internal/yt-dlp/，或加入 PATH。")

        try:
            info = run_dump_single_json(
                url,
                tuned,
                extra_args=["--flat-playlist", "--lazy-playlist"],
                cancel_event=cancel_event,
            )
            return cast(dict[str, Any], info)
        except Exception as exc:
            if isinstance(exc, YtDlpCancelled):
                raise
            msg = str(exc)
            if self._should_retry_with_youtubetab_skip_authcheck(msg):
                retry_opts = self._with_youtubetab_skip_authcheck(tuned)
                if retry_opts is not tuned:
                    self._emit_log(
                        "warning",
                        "检测到播放列表 authcheck 限制提示，按 yt-dlp 官方建议自动启用 youtubetab:skip=authcheck 并重试一次。",
                    )
                    info = run_dump_single_json(
                        url,
                        retry_opts,
                        extra_args=["--flat-playlist", "--lazy-playlist"],
                        cancel_event=cancel_event,
                    )
                    return cast(dict[str, Any], info)
            raise

    async def extract_info(self, url: str, options: YoutubeServiceOptions | None = None) -> dict[str, Any]:
        """Async metadata extraction (safe for UI thread)."""

        return await asyncio.to_thread(self.extract_info_sync, url, options)

    # --- Compatibility API (used by Phase 3 workers) ---
    def extract_video_info(
        self,
        url: str,
        options: YoutubeServiceOptions | None = None,
        *,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Compatibility wrapper for older naming."""

        return self.extract_info_sync(url, options, cancel_event=cancel_event)

    def extract_playlist_flat(
        self,
        url: str,
        options: YoutubeServiceOptions | None = None,
        *,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Extract playlist entries in a lightweight (flat) way.

        This is designed for UI listing:
        - avoid per-entry format extraction
        - return entries quickly to reduce request bursts
        """

        options = options or YoutubeServiceOptions()
        base_opts = self.build_ydl_options(options)
        ydl_opts = dict(base_opts)

        # Key knobs to reduce requests
        ydl_opts.update(
            {
                "skip_download": True,
                "extract_flat": True,
                # prefer lightweight playlist enumeration
                "lazy_playlist": True,
                # keep errors explicit (UI will show)
                "ignoreerrors": False,
            }
        )

        if bool(config_manager.get("playlist_skip_authcheck") or False):
            ydl_opts = self._with_youtubetab_skip_authcheck(ydl_opts)

        self._emit_log("info", f"[PlaylistFlat] extracting: {url}")
        try:
            try:
                _ = locate_runtime_tool("yt-dlp.exe", "yt-dlp/yt-dlp.exe", "yt_dlp/yt-dlp.exe")
            except FileNotFoundError:
                raise FileNotFoundError(
                    "未找到 yt-dlp.exe。请在设置页指定路径，或将 yt-dlp.exe 放入 _internal/yt-dlp/，或加入 PATH。"
                )

            try:
                info = run_dump_single_json(
                    url,
                    ydl_opts,
                    extra_args=["--flat-playlist", "--lazy-playlist"],
                    cancel_event=cancel_event,
                )
            except Exception as exc:
                if isinstance(exc, YtDlpCancelled):
                    raise
                msg = str(exc)
                if self._should_retry_with_youtubetab_skip_authcheck(msg):
                    retry_opts = self._with_youtubetab_skip_authcheck(ydl_opts)
                    if retry_opts is not ydl_opts:
                        self._emit_log(
                            "warning",
                            "检测到播放列表 authcheck 限制提示，按 yt-dlp 官方建议自动启用 youtubetab:skip=authcheck 并重试一次。",
                        )
                        info = run_dump_single_json(
                            url,
                            retry_opts,
                            extra_args=["--flat-playlist", "--lazy-playlist"],
                            cancel_event=cancel_event,
                        )
                    else:
                        raise
                else:
                    raise

            if not isinstance(info, dict):
                raise RuntimeError("播放列表解析失败：返回结果为空")
            return cast(dict[str, Any], info)
        except Exception as exc:
            msg = str(exc)
            self._emit_log("error", f"播放列表解析失败: {msg}")
            raise

    @staticmethod
    def _should_retry_with_youtubetab_skip_authcheck(error_text: str) -> bool:
        """Detect yt-dlp's official hint for playlist authcheck.

        yt-dlp error usually contains: "pass --extractor-args youtubetab:skip=authcheck".
        """

        lower = (error_text or "").lower()
        return "youtubetab:skip=authcheck" in lower or ("authcheck" in lower and "youtubetab" in lower)

    @staticmethod
    def _with_youtubetab_skip_authcheck(ydl_opts: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of ydl_opts with extractor-args youtubetab:skip=authcheck injected.

        If already present, returns the original dict (to avoid infinite retries).
        """

        extractor_args = ydl_opts.get("extractor_args")
        if extractor_args is None:
            new_opts = dict(ydl_opts)
            new_opts["extractor_args"] = {"youtubetab": {"skip": ["authcheck"]}}
            return new_opts

        if not isinstance(extractor_args, dict):
            # Unrecognized format; do not try to mutate.
            return ydl_opts

        youtubetab_args = extractor_args.get("youtubetab")
        if isinstance(youtubetab_args, dict):
            existing = youtubetab_args.get("skip")
            if isinstance(existing, (list, tuple)) and any(str(x).strip().lower() == "authcheck" for x in existing):
                return ydl_opts
            if isinstance(existing, str) and "authcheck" in existing.lower():
                return ydl_opts

        # Copy-on-write to avoid mutating callers unexpectedly.
        new_opts = dict(ydl_opts)
        new_extractor_args = dict(extractor_args)
        new_youtubetab_args: dict[str, Any] = {}
        if isinstance(youtubetab_args, dict):
            new_youtubetab_args.update(youtubetab_args)
        new_youtubetab_args["skip"] = ["authcheck"]
        new_extractor_args["youtubetab"] = new_youtubetab_args
        new_opts["extractor_args"] = new_extractor_args
        return new_opts

    def get_local_version(self) -> str:
        return run_version()


youtube_service = YoutubeService()
