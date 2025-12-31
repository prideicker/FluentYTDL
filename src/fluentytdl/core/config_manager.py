from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..utils.paths import config_path, legacy_config_path


class ConfigManager:
    """配置管理单例（JSON 持久化）。"""

    _instance: "ConfigManager | None" = None

    DEFAULT_CONFIG: dict[str, Any] = {
        "download_dir": str(Path.home() / "Downloads" / "FluentYTDL"),
        "ffmpeg_path": "",  # 空代表自动检测
        # Proxy mode:
        # - off: do NOT use system/ambient proxy
        # - system: follow system/ambient proxy settings
        # - http: manual HTTP proxy (proxy_url is host:port or URL)
        # - socks5: manual SOCKS5 proxy (proxy_url is host:port or URL)
        "proxy_mode": "system",  # off / system / http / socks5
        # Backward-compat key (older versions used a switch + url)
        "proxy_enabled": False,
        "proxy_url": "127.0.0.1:7890",
        "cookie_mode": "browser",  # browser / file
        "cookie_browser": "firefox",  # chrome / edge / firefox
        "cookie_file": "",
        # YouTube PO Token (optional). See yt-dlp wiki: PO-Token-Guide
        # Example value: "mweb.gvs+<TOKEN>" or "mweb.gvs+<TOKEN>,mweb.player+<TOKEN>"
        "youtube_po_token": "",
        # yt-dlp YouTube EJS/JS runtime (yt-dlp issue #15012)
        # auto: prefer deno if available (default), else try node/bun/quickjs
        "js_runtime": "auto",  # auto / deno / node / bun / quickjs
        "js_runtime_path": "",  # optional absolute path to runtime executable

        # Optional yt-dlp.exe override path
        # Empty means auto (prefer bundled _internal/yt-dlp/yt-dlp.exe, else PATH)
        "yt_dlp_exe_path": "",
        "max_concurrent_downloads": 3,

        # UI/behavior
        # Whether to auto-detect YouTube URLs from clipboard.
        "clipboard_auto_detect": False,

        # Download list behavior
        # Deletion Policy:
        # - KeepFiles: Only remove task from list, keep all files.
        # - DeleteFiles: Silently delete source/cache files based on task status.
        # - AlwaysAsk: Prompt user every time (Legacy behavior).
        "deletion_policy": "AlwaysAsk",

        # Legacy keys (kept for migration or fallback, but effectively deprecated by deletion_policy)
        "remove_task_ask_delete_source": False,
        "remove_task_ask_delete_cache": False,
        "remove_task_ask_enable_feature": True,

        # yt-dlp / playlist parsing
        # yt-dlp sometimes refuses to enumerate some public playlists unless you skip authcheck.
        # Official suggestion: --extractor-args youtubetab:skip=authcheck
        # Default OFF to avoid surprising behavior changes.
        "playlist_skip_authcheck": False,
        
        # Dependency update source
        # github: official github api/releases
        # ghproxy: use ghproxy mirror
        "update_source": "github",

        # Whether to check for component updates (yt-dlp, ffmpeg, etc.) on startup
        # If true, checks once every 24 hours.
        "check_updates_on_startup": True,
        
        # Timestamp of last automatic update check
        "last_update_check": 0,
        
        # Whether the user has seen the welcome guide (wizard)
        "has_shown_welcome_guide": False,
        # Version when user last saw the welcome guide (for version-aware re-trigger)
        "welcome_guide_shown_for_version": "",
    }

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        # Dev: repo root config.json; Frozen: user-writable Documents/FluentYTDL/config.json
        self.config_file = config_path()
        self.config: dict[str, Any] = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        # Backward-compat: if new location doesn't exist but legacy exists, load legacy.
        # If we are running frozen, also migrate the legacy file into the new location.
        candidates = [self.config_file]
        legacy = legacy_config_path()
        if legacy != self.config_file:
            candidates.append(legacy)

        existing = next((p for p in candidates if p.exists()), None)
        if existing is None:
            return self.DEFAULT_CONFIG.copy()

        # Migration: legacy -> new
        if existing == legacy and legacy != self.config_file:
            try:
                self.config_file.parent.mkdir(parents=True, exist_ok=True)
                self.config_file.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")
                existing = self.config_file
            except Exception:
                # If migration fails, continue using legacy in this session.
                existing = legacy

        try:
            data = json.loads(existing.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return self.DEFAULT_CONFIG.copy()
            # 合并默认配置，防止新版本缺字段
            merged = {**self.DEFAULT_CONFIG, **data}

            # Migration: proxy_enabled/proxy_url -> proxy_mode
            if "proxy_mode" not in data:
                if bool(data.get("proxy_enabled")):
                    # default to http unless the url suggests socks5
                    proxy_url = str(data.get("proxy_url") or "").lower()
                    merged["proxy_mode"] = "socks5" if "socks" in proxy_url else "http"
                else:
                    merged["proxy_mode"] = "off"

            # Legacy value mapping
            if str(merged.get("proxy_mode") or "").lower().strip() == "custom":
                proxy_url = str(merged.get("proxy_url") or "").lower()
                merged["proxy_mode"] = "socks5" if "socks" in proxy_url else "http"

            # Normalize
            pm = str(merged.get("proxy_mode") or "off").lower().strip()
            if pm not in {"off", "system", "http", "socks5"}:
                pm = "off"
            merged["proxy_mode"] = pm

            # Normalize tool paths: if a user keeps an old absolute path that no longer
            # exists (common after packaging/moving folders), fall back to auto-detect.
            for key in ("ffmpeg_path", "yt_dlp_exe_path", "js_runtime_path"):
                try:
                    raw = str(merged.get(key) or "").strip()
                    if raw and not Path(raw).exists():
                        merged[key] = ""
                except Exception:
                    merged[key] = ""

            return merged
        except Exception:
            return self.DEFAULT_CONFIG.copy()

    def save(self) -> None:
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text(
                json.dumps(self.config, indent=4, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            # Avoid crashing UI if disk is read-only / permission issues.
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.config[key] = value
        self.save()


config_manager = ConfigManager()
