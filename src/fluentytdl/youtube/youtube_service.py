from __future__ import annotations

import asyncio
import http.cookiejar
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, cast

from fluentytdl.utils.logger import get_logger
from fluentytdl.utils.paths import find_bundled_executable, is_frozen, locate_runtime_tool
from ..core.config_manager import config_manager
from .yt_dlp_cli import YtDlpCancelled, run_dump_single_json, run_version


LogCallback = Callable[[str, str], None]


@dataclass(slots=True)
class YtDlpAuthOptions:
    """Authentication inputs.

    Priority: cookies_file (直接指定) > AuthService (统一管理).
    
    Note: cookies_from_browser 已废弃，所有浏览器 Cookie 通过 AuthService 处理。
    """

    cookies_file: str | None = None
    cookies_from_browser: str | None = None  # 废弃，保留兼容性


@dataclass(slots=True)
class AntiBlockingOptions:
    """Anti-blocking / anti-bot options."""

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

        # User-Agent: 不再自定义，让 yt-dlp 根据客户端类型自动处理
        # yt-dlp 会根据 extractor_args 中的 player_client 自动匹配合适的 UA

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

        # Cookies: 统一通过 Cookie Sentinel 管理
        # 新架构：所有 Cookie 统一写入 bin/cookies.txt，yt-dlp 始终读取该文件
        # 优先级: options.auth.cookies_file (直接指定) > Cookie Sentinel
        has_valid_cookie = False
        cookiefile = None

        # 1. 检查 auth options 中是否直接指定了 cookie 文件（向后兼容）
        direct_cookiefile = (auth.cookies_file or "").strip() or None
        
        if direct_cookiefile and os.path.exists(direct_cookiefile):
            # 直接指定的 cookie 文件优先
            if self._is_probably_json_cookie_file(direct_cookiefile):
                self._emit_log(
                    "error",
                    "Cookies 文件疑似为 JSON 格式，yt-dlp 只支持 Netscape HTTP Cookie File 格式；已忽略该文件。",
                )
            else:
                yt_cookie_count = self._count_youtube_related_cookies(direct_cookiefile)
                if yt_cookie_count <= 0:
                    self._emit_log(
                        "warning",
                        "已读取 cookies.txt，但未发现 YouTube/Google 域相关 cookies。"
                        "请确认是在 youtube.com 登录后导出，且为 Netscape 格式。",
                    )
                else:
                    cookiefile = direct_cookiefile
                    has_valid_cookie = True
                    self._emit_log(
                        "info",
                        f"✅ 已加载 Cookie 文件: {cookiefile} (YouTube/Google cookies: {yt_cookie_count})",
                    )
        else:
            # 2. 通过 Cookie Sentinel 获取统一的 bin/cookies.txt
            try:
                from ..auth.cookie_sentinel import cookie_sentinel
                
                sentinel_cookie_file = cookie_sentinel.get_cookie_file_path()
                
                if cookie_sentinel.exists:
                    yt_cookie_count = self._count_youtube_related_cookies(sentinel_cookie_file)
                    if yt_cookie_count > 0:
                        cookiefile = sentinel_cookie_file
                        has_valid_cookie = True
                        
                        # 显示状态信息
                        age = cookie_sentinel.age_minutes
                        age_str = f"{int(age)}分钟前" if age is not None else "未知"
                        status_emoji = "⚠️" if cookie_sentinel.is_stale else "✅"
                        
                        self._emit_log(
                            "info",
                            f"{status_emoji} Cookie Sentinel: {cookie_sentinel.get_status_info()['source']} "
                            f"(更新于 {age_str}, {yt_cookie_count} 个 YouTube Cookie)",
                        )
                    else:
                        self._emit_log(
                            "warning",
                            "Cookie Sentinel 文件存在但未发现 YouTube 相关 Cookie",
                        )
                else:
                    self._emit_log(
                        "info",
                        "Cookie Sentinel 文件不存在，将使用无 Cookie 模式下载（可能受限）",
                    )
                    
            except Exception as e:
                self._emit_log("warning", f"Cookie Sentinel 获取失败: {e}")
        
        # 设置 cookiefile 到 ydl_opts
        if cookiefile:
            ydl_opts["cookiefile"] = cookiefile
        
        self._emit_log(
            "debug",
            f"[Cookie] Path={cookiefile or 'None'}, Valid={has_valid_cookie}",
        )

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

        # --- POT Provider 服务集成 ---
        # POT (Proof of Origin Token) Provider 提供动态 PO Token 生成服务
        # 类似 Cookie Sentinel 的策略：检测服务状态，自动注入 extractor_args
        pot_injected = False
        if config_manager.get("pot_provider_enabled", True):
            try:
                from .pot_manager import pot_manager
                
                if pot_manager.is_running():
                    pot_extractor_args = pot_manager.get_extractor_args()
                    if pot_extractor_args:
                        # pot_extractor_args 格式: "youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416"
                        # 需要解析并注入到 extractor_args
                        extractor_args = cast(dict[str, Any], ydl_opts.setdefault("extractor_args", {}))
                        
                        # 解析 "youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416"
                        if ":" in pot_extractor_args:
                            ie_key, args_str = pot_extractor_args.split(":", 1)
                            pot_args: dict[str, Any] = extractor_args.setdefault(ie_key, {})
                            
                            # 解析 "base_url=http://127.0.0.1:4416"
                            for part in args_str.split(";"):
                                if "=" in part:
                                    k, v = part.split("=", 1)
                                    pot_args[k] = [v]
                            
                            pot_injected = True
                            self._emit_log(
                                "info",
                                f"🛡️ POT Provider 已激活: 端口 {pot_manager.active_port} (自动绕过机器人检测)",
                            )
                else:
                    self._emit_log(
                        "warning",
                        "⚠️ POT Provider 服务未运行，本次下载将不使用 PO Token（可能触发限速）",
                    )
            except Exception as e:
                self._emit_log("debug", f"POT Provider 检测失败: {e}")

        # --- Optional: 手动 YouTube PO Token (备用方案) ---
        # 如果 POT Provider 未启用或未运行，用户可以手动配置静态 PO Token
        # Context: YouTube is rolling out PO Token enforcement. yt-dlp recommends using
        # the `mweb` client together with a PO Token when default clients fail.
        if not pot_injected:
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
                self._emit_log("info", "🔐 已注入手动 PO Token：将优先尝试 mweb 客户端")

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

        # === Phase 2: 核心下载层集成 ===
        
        # 并发分片数
        concurrent_fragments = config_manager.get("concurrent_fragments", 4)
        if concurrent_fragments and concurrent_fragments > 1:
            ydl_opts["concurrent_fragment_downloads"] = int(concurrent_fragments)
        
        # 下载限速
        rate_limit = str(config_manager.get("rate_limit") or "").strip()
        if rate_limit:
            ydl_opts["ratelimit"] = rate_limit


        # === 后处理：封面嵌入 & 元数据嵌入 ===
        embed_thumbnail = config_manager.get("embed_thumbnail", True)
        embed_metadata = config_manager.get("embed_metadata", True)
        
        if embed_thumbnail or embed_metadata:
            postprocessors = ydl_opts.setdefault("postprocessors", [])
            
            # 封面嵌入：只下载缩略图，不让 yt-dlp 嵌入（由我们的后处理器处理）
            if embed_thumbnail:
                ydl_opts["writethumbnail"] = True
                # 转换缩略图格式为 jpg（兼容性最佳）
                ydl_opts["convert_thumbnail"] = "jpg"
                # 注意：不再添加 EmbedThumbnail 后处理器，由外部 thumbnail_embedder 处理
            
            # 元数据嵌入
            if embed_metadata:
                postprocessors.append({"key": "FFmpegMetadata"})

        # === SponsorBlock 广告跳过 ===
        sponsorblock_enabled = config_manager.get("sponsorblock_enabled", False)
        if sponsorblock_enabled:
            categories = config_manager.get("sponsorblock_categories", ["sponsor", "selfpromo", "interaction"])
            action = config_manager.get("sponsorblock_action", "remove")
            
            if categories:  # 确保有选中的类别
                if action == "mark":
                    ydl_opts["sponsorblock_mark"] = categories
                    self._emit_log("info", f"🚫 SponsorBlock 已启用: 将标记以下类别为章节: {', '.join(categories)}")
                else:
                    # 默认为 remove
                    ydl_opts["sponsorblock_remove"] = categories
                    self._emit_log("info", f"🚫 SponsorBlock 已启用: 将移除以下类别: {', '.join(categories)}")

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

    # ========== VR 视频智能检测与二次解析 ==========

    # VR 相关关键词 (用于标题/描述检测)
    _VR_KEYWORDS = (
        "vr180", "vr360", "vr 180", "vr 360",
        "180°", "360°", "180vr", "360vr",
        "3d vr", "vr video", "vr体验", "vr视频",
        "sbs", "side by side", "over under", "ou3d",
        "stereoscopic", "immersive",
    )

    def _is_vr_video(self, info: dict[str, Any]) -> bool:
        """检测视频是否为 VR180/VR360 内容。

        检测条件:
        1. 标题/描述含 VR 相关关键词
        2. 格式列表中包含 'mesh' 标记 (VR 投影格式特征)
        3. 标题声称 8K 但最高格式 < 4320p (格式异常)
        """
        title = str(info.get("title") or "").lower()
        description = str(info.get("description") or "").lower()
        text = f"{title} {description}"

        # 检查 VR 关键词
        for kw in self._VR_KEYWORDS:
            if kw in text:
                self._emit_log("info", f"🥽 检测到 VR 关键词: '{kw}'")
                return True

        # 检查格式是否包含 mesh 标记 (VR 投影)
        formats = info.get("formats") or []
        for fmt in formats:
            format_note = str(fmt.get("format_note") or "").lower()
            format_id = str(fmt.get("format") or "").lower()
            if "mesh" in format_note or "mesh" in format_id:
                self._emit_log("info", "🥽 检测到 VR 投影格式 (mesh)")
                return True

        # 检查分辨率异常: 标题含 8K 但格式列表最高 < 4320p
        if "8k" in title:
            max_height = 0
            for fmt in formats:
                h = fmt.get("height") or 0
                if isinstance(h, int) and h > max_height:
                    max_height = h
            if max_height > 0 and max_height < 4320:
                self._emit_log(
                    "warning",
                    f"⚠️ 标题声称 8K 但最高格式仅 {max_height}p，可能是 VR 视频",
                )
                return True

        return False

    def _get_max_resolution(self, info: dict[str, Any]) -> int:
        """获取格式列表中的最高分辨率 (height)"""
        formats = info.get("formats") or []
        max_height = 0
        for fmt in formats:
            h = fmt.get("height") or 0
            if isinstance(h, int) and h > max_height:
                max_height = h
        return max_height

    def _extract_vr_formats(
        self,
        url: str,
        cancel_event: threading.Event | None = None,
    ) -> list[dict[str, Any]]:
        """使用 android_vr 客户端获取 VR 高分辨率格式。

        注意: android_vr 不支持 cookies，因此无法用于年龄验证。
        此方法仅用于补充 VR 高分辨率格式。
        """
        self._emit_log("info", "🔄 使用 android_vr 客户端获取 VR 高分辨率格式...")

        # 构建无 cookies 的 android_vr 解析选项
        vr_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "skip_download": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android_vr"],
                }
            },
        }

        # FFmpeg location (复用主配置)
        ffmpeg_path = str(config_manager.get("ffmpeg_path") or "").strip()
        if ffmpeg_path and Path(ffmpeg_path).exists():
            vr_opts["ffmpeg_location"] = ffmpeg_path
        elif is_frozen():
            bundled_ffmpeg = find_bundled_executable("ffmpeg.exe", "ffmpeg/ffmpeg.exe")
            if bundled_ffmpeg is not None:
                vr_opts["ffmpeg_location"] = str(bundled_ffmpeg)

        # JS runtime (复用主配置逻辑)
        self._maybe_configure_youtube_js_runtime(vr_opts)

        try:
            info = run_dump_single_json(
                url,
                vr_opts,
                extra_args=["--no-playlist"],
                cancel_event=cancel_event,
            )
            if isinstance(info, dict):
                formats = info.get("formats") or []
                self._emit_log(
                    "info",
                    f"✅ android_vr 客户端获取到 {len(formats)} 个格式",
                )
                return list(formats)
        except Exception as e:
            self._emit_log("warning", f"android_vr 解析失败: {e}")

        return []

    def _merge_formats(
        self,
        info: dict[str, Any],
        vr_formats: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """合并首次解析和 VR 解析的格式列表。

        合并策略:
        - 使用 format_id 去重
        - VR 格式优先 (通常包含更高分辨率)
        - 记录 VR 专属格式 ID (仅 android_vr 有，web 没有)
        - 记录所有 android_vr 可用格式 ID (用于兼容性检查)
        """
        if not vr_formats:
            return info

        existing_formats = info.get("formats") or []
        existing_ids = {str(f.get("format_id") or "") for f in existing_formats}

        # 记录所有 android_vr 可用的格式 ID (用于下载时兼容性检查)
        all_vr_format_ids: list[str] = []
        for vr_fmt in vr_formats:
            fmt_id = str(vr_fmt.get("format_id") or "")
            if fmt_id:
                all_vr_format_ids.append(fmt_id)

        # 添加不重复的 VR 格式，并记录 VR 专属格式 ID
        added_count = 0
        vr_only_format_ids: list[str] = []
        for vr_fmt in vr_formats:
            fmt_id = str(vr_fmt.get("format_id") or "")
            if fmt_id and fmt_id not in existing_ids:
                existing_formats.append(vr_fmt)
                existing_ids.add(fmt_id)
                vr_only_format_ids.append(fmt_id)
                added_count += 1

        if added_count > 0:
            # 按分辨率排序
            existing_formats.sort(
                key=lambda f: (f.get("height") or 0, f.get("width") or 0)
            )
            info["formats"] = existing_formats

            # 记录 VR 专属格式 ID (仅 android_vr 有，web 没有)
            info["__vr_only_format_ids"] = vr_only_format_ids
            # 记录所有 android_vr 可用格式 ID (用于下载时兼容性检查)
            info["__android_vr_format_ids"] = all_vr_format_ids
            self._emit_log(
                "info",
                f"✅ 已合并 {added_count} 个 VR 高分辨率格式 (IDs: {', '.join(vr_only_format_ids)})",
            )

            # 更新最高分辨率信息
            max_height = self._get_max_resolution(info)
            if max_height >= 4320:
                self._emit_log("info", f"🎉 最高可用分辨率: {max_height}p (8K)")
            elif max_height >= 2160:
                self._emit_log("info", f"📺 最高可用分辨率: {max_height}p (4K)")

        return info

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
            info = _do_extract(ydl_opts)

            # ========== VR 视频智能检测与二次解析 ==========
            # 检测是否为 VR 视频，如果是则使用 android_vr 客户端补充高分辨率格式
            try:
                if self._is_vr_video(info):
                    vr_formats = self._extract_vr_formats(url, cancel_event)
                    info = self._merge_formats(info, vr_formats)
            except Exception as vr_exc:
                # VR 二次解析失败不影响主流程
                self._emit_log("warning", f"VR 二次解析过程出错: {vr_exc}")

            return info
        except Exception as exc:
            if isinstance(exc, YtDlpCancelled):
                raise
            msg = str(exc)
            lower = msg.lower()

            # 注意: 已移除 cookies-from-browser fallback
            # 所有 Cookie 统一通过 Cookie Sentinel 管理，使用 bin/cookies.txt
            # 这样可以避免 DPAPI 文件锁和权限问题

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
            info = cast(dict[str, Any], info)

            # VR 视频智能检测 (仅对单视频生效)
            if info.get("_type") != "playlist" and self._is_vr_video(info):
                try:
                    vr_formats = self._extract_vr_formats(url, cancel_event)
                    info = self._merge_formats(info, vr_formats)
                except Exception as vr_exc:
                    self._emit_log("warning", f"VR 二次解析过程出错: {vr_exc}")

            return info
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
