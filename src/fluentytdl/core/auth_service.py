"""
FluentYTDL 统一身份验证服务

重构后的核心设计:
- 所有 Cookie 处理统一走此服务
- 用户在 UI 选择"来源"，底层全部转为文件路径
- 彻底避免 yt-dlp --cookies-from-browser 的文件锁问题

架构:
  UI (选浏览器/文件) -> AuthService -> rookiepy/文件读取 -> 临时 cookies.txt -> yt-dlp --cookies
"""

from __future__ import annotations

import ctypes
import json
import sys
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ..utils.logger import logger

# 尝试导入 rookiepy
try:
    import rookiepy
    HAS_ROOKIEPY = True
except ImportError:
    HAS_ROOKIEPY = False
    logger.warning("rookiepy 未安装，浏览器 Cookie 自动提取功能不可用")


# ==================== Windows 管理员权限检查 ====================

def is_admin() -> bool:
    """检查当前是否为管理员权限"""
    if sys.platform != "win32":
        return True  # 非 Windows 假设无需提权
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _is_appbound_error(error: Exception) -> bool:
    """检测是否为 Chromium App-Bound 加密错误（需要管理员权限）"""
    err_str = str(error).lower()
    return (
        "admin" in err_str
        or "appbound" in err_str
        or "v130" in err_str
        or "decrypted only when running as admin" in err_str
    )


# 注意：已移除子进程 UAC 提权逻辑 (_run_elevated_extractor)
# 现在改为由 UI 层检测权限需求，然后调用 restart_as_admin() 重启整个程序
# 参见 admin_utils.py 中的 restart_as_admin() 函数


class AuthSourceType(str, Enum):
    """验证源类型"""
    NONE = "none"           # 不使用身份验证
    # Chromium 内核浏览器（v130+ 需要管理员权限）
    EDGE = "edge"           # Microsoft Edge
    CHROME = "chrome"       # Google Chrome
    CHROMIUM = "chromium"   # Chromium
    BRAVE = "brave"         # Brave
    OPERA = "opera"         # Opera
    OPERA_GX = "opera_gx"   # Opera GX
    VIVALDI = "vivaldi"     # Vivaldi
    ARC = "arc"             # Arc
    # Firefox 内核浏览器（无需管理员权限）
    FIREFOX = "firefox"     # Firefox
    LIBREWOLF = "librewolf" # LibreWolf
    # 其他
    FILE = "file"           # 手动导入的 cookies.txt


# 浏览器类型列表（用于 UI 展示和逻辑判断）
# Chromium 内核 v130+ 都需要管理员权限提取 Cookie
BROWSER_SOURCES = [
    AuthSourceType.EDGE, AuthSourceType.CHROME, AuthSourceType.CHROMIUM,
    AuthSourceType.BRAVE, AuthSourceType.OPERA, AuthSourceType.OPERA_GX,
    AuthSourceType.VIVALDI, AuthSourceType.ARC,
    AuthSourceType.FIREFOX, AuthSourceType.LIBREWOLF,
]

# 需要管理员权限的浏览器（Chromium 内核 v130+）
ADMIN_REQUIRED_BROWSERS = [
    AuthSourceType.EDGE, AuthSourceType.CHROME, AuthSourceType.CHROMIUM,
    AuthSourceType.BRAVE, AuthSourceType.OPERA, AuthSourceType.OPERA_GX,
    AuthSourceType.VIVALDI, AuthSourceType.ARC,
]

# 各平台需要的 Cookie 域名
PLATFORM_DOMAINS = {
    "youtube": [".youtube.com", ".google.com"],
    "bilibili": [".bilibili.com"],
    "twitter": [".twitter.com", ".x.com"],
}

# YouTube 登录验证所需的关键 Cookie
YOUTUBE_REQUIRED_COOKIES = {"SID", "HSID", "SSID", "SAPISID", "APISID"}


@dataclass
class AuthStatus:
    """验证状态"""
    valid: bool = False
    message: str = "未验证"
    cookie_count: int = 0
    last_updated: str | None = None
    account_hint: str | None = None  # 账户提示 (如 "YouTube Premium")


@dataclass  
class AuthProfile:
    """
    认证配置（用于高级多账户管理）
    """
    name: str                              # 显示名称
    platform: str = "youtube"              # 平台标识
    source_type: AuthSourceType = AuthSourceType.EDGE
    file_path: str | None = None           # 当 FILE 类型使用
    cached_cookie_path: str | None = None  # 缓存的 cookie 文件路径
    enabled: bool = True
    last_updated: str | None = None
    cookie_count: int = 0
    is_valid: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source_type"] = self.source_type.value
        return d
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthProfile:
        if "source_type" in data:
            data["source_type"] = AuthSourceType(data["source_type"])
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


class AuthService:
    """
    统一身份验证服务
    
    核心职责:
    1. 管理当前激活的验证源
    2. 按需提取/读取 Cookie 并生成临时文件
    3. 向 yt-dlp 提供统一的 cookie 文件路径
    """
    
    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "fluentytdl_auth"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self._config_path = self.cache_dir / "auth_config.json"
        self._profiles_path = self.cache_dir / "profiles.json"
        
        # 当前配置
        self._current_source: AuthSourceType = AuthSourceType.NONE
        self._current_file_path: str | None = None
        self._auto_refresh: bool = True
        self._last_status: AuthStatus = AuthStatus()
        
        # 高级：多账户配置
        self._profiles: dict[str, AuthProfile] = {}
        
        self._load_config()
    
    # ==================== 属性 ====================
    
    @property
    def available(self) -> bool:
        """rookiepy 是否可用"""
        return HAS_ROOKIEPY
    
    @property
    def current_source(self) -> AuthSourceType:
        """当前验证源"""
        return self._current_source
    
    @property
    def current_source_display(self) -> str:
        """当前验证源的显示名称"""
        names = {
            AuthSourceType.NONE: "未启用",
            AuthSourceType.EDGE: "Edge 浏览器",
            AuthSourceType.CHROME: "Chrome 浏览器",
            AuthSourceType.CHROMIUM: "Chromium 浏览器",
            AuthSourceType.BRAVE: "Brave 浏览器",
            AuthSourceType.OPERA: "Opera 浏览器",
            AuthSourceType.OPERA_GX: "Opera GX 浏览器",
            AuthSourceType.VIVALDI: "Vivaldi 浏览器",
            AuthSourceType.ARC: "Arc 浏览器",
            AuthSourceType.FIREFOX: "Firefox 浏览器",
            AuthSourceType.LIBREWOLF: "LibreWolf 浏览器",
            AuthSourceType.FILE: "手动导入文件",
        }
        return names.get(self._current_source, "未知")
    
    @property
    def auto_refresh(self) -> bool:
        """是否自动刷新 Cookie"""
        return self._auto_refresh
    
    @property
    def last_status(self) -> AuthStatus:
        """最近一次验证状态"""
        return self._last_status
    
    # ==================== 核心方法 ====================
    
    def set_source(
        self,
        source: AuthSourceType,
        file_path: str | None = None,
        auto_refresh: bool = True,
    ) -> None:
        """
        设置验证源
        
        Args:
            source: 验证源类型
            file_path: 当 FILE 类型需要
            auto_refresh: 是否自动刷新
        """
        self._current_source = source
        self._current_file_path = file_path if source == AuthSourceType.FILE else None
        self._auto_refresh = auto_refresh
        self._save_config()
        
        logger.info(f"验证源已设置: {self.current_source_display}")
    
    def get_cookie_file_for_ytdlp(
        self,
        platform: str = "youtube",
        force_refresh: bool = False,
    ) -> str | None:
        """
        获取 yt-dlp 可用的 cookie 文件路径
        
        这是被 yt_dlp_cli.py 调用的核心方法。
        
        Args:
            platform: 平台标识
            force_refresh: 强制刷新（忽略缓存）
            
        Returns:
            cookie 文件的绝对路径，或 None（未启用验证）
        """
        if self._current_source == AuthSourceType.NONE:
            return None
        
        try:
            if self._current_source == AuthSourceType.FILE:
                # 手动导入的文件：直接返回路径
                if self._current_file_path and Path(self._current_file_path).exists():
                    self._update_status_from_file(self._current_file_path)
                    return self._current_file_path
                else:
                    self._last_status = AuthStatus(
                        valid=False,
                        message="Cookie 文件不存在",
                    )
                    return None
            
            elif self._current_source in BROWSER_SOURCES:
                # 浏览器来源：使用 rookiepy 提取
                return self._extract_and_cache(
                    browser=self._current_source.value,
                    platform=platform,
                    force_refresh=force_refresh or self._auto_refresh,
                )
            
        except Exception as e:
            logger.error(f"获取 Cookie 失败: {e}")
            self._last_status = AuthStatus(
                valid=False,
                message=f"获取失败: {e}",
            )
        
        return None
    
    def refresh_now(self, platform: str = "youtube") -> AuthStatus:
        """
        立即刷新 Cookie
        
        Returns:
            刷新后的状态
        """
        if self._current_source == AuthSourceType.NONE:
            self._last_status = AuthStatus(valid=False, message="未启用验证")
            return self._last_status
        
        try:
            cookie_path = self.get_cookie_file_for_ytdlp(platform, force_refresh=True)
            if cookie_path:
                return self._last_status
        except Exception as e:
            self._last_status = AuthStatus(valid=False, message=f"刷新失败: {e}")
        
        return self._last_status
    
    def validate_file(self, file_path: str) -> AuthStatus:
        """
        验证 Cookie 文件
        
        Args:
            file_path: cookies.txt 路径
            
        Returns:
            验证结果
        """
        try:
            path = Path(file_path)
            if not path.exists():
                return AuthStatus(valid=False, message="文件不存在")
            
            content = path.read_text(encoding="utf-8", errors="replace")
            cookies = self._parse_netscape_cookies(content)
            
            if not cookies:
                return AuthStatus(valid=False, message="文件为空或格式无效")
            
            validation = self._validate_cookies(cookies, "youtube")
            
            return AuthStatus(
                valid=validation["valid"],
                message=validation["message"],
                cookie_count=len(cookies),
                last_updated=datetime.now().isoformat(),
            )
            
        except Exception as e:
            return AuthStatus(valid=False, message=f"验证失败: {e}")
    
    # ==================== 内部方法 ====================
    
    def _extract_and_cache(
        self,
        browser: str,
        platform: str,
        force_refresh: bool = False,
    ) -> str | None:
        """
        从浏览器提取 Cookie 并缓存
        
        支持 Chrome v130+ App-Bound 加密的自动提权处理
        """
        if not HAS_ROOKIEPY:
            raise RuntimeError("rookiepy 未安装，无法从浏览器提取 Cookie")
        
        # 缓存文件路径
        cache_file = self.cache_dir / f"cached_{browser}_{platform}.txt"
        
        # 检查缓存是否足够新（5 分钟内）
        if not force_refresh and cache_file.exists():
            mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            age_minutes = (datetime.now() - mtime).total_seconds() / 60
            if age_minutes < 5:
                logger.debug(f"使用缓存的 Cookie 文件: {cache_file}")
                self._update_status_from_file(str(cache_file))
                return str(cache_file)
        
        # 提取 Cookie
        domains = PLATFORM_DOMAINS.get(platform, [".youtube.com", ".google.com"])
        cookies = None
        
        try:
            # 首先尝试直接提取
            extractor = getattr(rookiepy, browser, None)
            if extractor is None:
                raise RuntimeError(f"rookiepy 不支持 {browser}")
            
            cookies = extractor(domains)
            logger.info(f"从 {browser} 提取到 {len(cookies)} 个 Cookie")
            
        except Exception as e:
            logger.warning(f"直接提取失败: {e}")
            
            # 检测是否为 App-Bound 加密错误（Chrome v130+）
            if _is_appbound_error(e) and sys.platform == "win32":
                logger.info("检测到 Chrome v130+ App-Bound 加密，需要管理员权限")
                
                # 直接抛出 PermissionError，由 UI 层调用 restart_as_admin() 重启程序
                browser_display = BROWSER_SOURCES.get(browser, browser.capitalize())
                self._last_status = AuthStatus(
                    valid=False,
                    message=f"{browser_display} 需要管理员权限才能提取 Cookie（App-Bound 加密）",
                )
                raise PermissionError(
                    f"{browser_display} v130+ 使用了 App-Bound 加密。\n"
                    "需要以管理员身份重新启动程序才能提取 Cookie。\n\n"
                    "建议：使用 Edge 浏览器可避免此问题。"
                )
            else:
                # 非 App-Bound 错误，直接抛出
                raise
        
        if not cookies:
            browser_display = BROWSER_SOURCES.get(browser, browser.capitalize())
            self._last_status = AuthStatus(
                valid=False,
                message=(
                    f"无法从 {browser_display} 提取 Cookie\n\n"
                    "可能的原因：\n"
                    f"1. {browser_display} 未安装\n"
                    f"2. 未在 {browser_display} 中登录 YouTube\n"
                    f"3. {browser_display} 正在运行（Cookie 数据库被锁定）\n\n"
                    "建议：\n"
                    "• 确保已在浏览器中登录 YouTube\n"
                    "• 完全关闭浏览器后重试\n"
                    "• 尝试使用其他浏览器（如 Edge）"
                ),
            )
            return None
        
        # 写入缓存文件
        self._write_netscape_file(cookies, cache_file)
        
        # 验证并更新状态
        validation = self._validate_cookies(cookies, platform)
        
        self._last_status = AuthStatus(
            valid=validation["valid"],
            message=validation["message"],
            cookie_count=len(cookies),
            last_updated=datetime.now().isoformat(),
            account_hint=self._detect_account_hint(cookies),
        )
        
        return str(cache_file)
    
    def _write_netscape_file(self, cookies: list[dict], output_path: Path) -> None:
        """将 Cookie 写入 Netscape 格式文件"""
        lines = [
            "# Netscape HTTP Cookie File",
            "# Generated by FluentYTDL AuthService",
            f"# {datetime.now().isoformat()}",
            "",
        ]
        
        for c in cookies:
            domain = c.get("domain", "")
            flag = "TRUE" if domain.startswith(".") else "FALSE"
            path = c.get("path", "/")
            secure = "TRUE" if c.get("secure", False) else "FALSE"
            expiry = str(int(c.get("expires", 0) or 0))
            name = c.get("name", "")
            value = c.get("value", "")
            
            lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")
        
        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.debug(f"已生成 Cookie 文件: {output_path}")
    
    def _parse_netscape_cookies(self, content: str) -> list[dict]:
        """解析 Netscape 格式的 Cookie 文件"""
        cookies = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies.append({
                    "domain": parts[0],
                    "path": parts[2],
                    "secure": parts[3].upper() == "TRUE",
                    "expires": int(parts[4]) if parts[4].isdigit() else 0,
                    "name": parts[5],
                    "value": parts[6],
                })
        return cookies
    
    def _validate_cookies(self, cookies: list[dict], platform: str) -> dict:
        """验证 Cookie"""
        found = {c.get("name", "") for c in cookies}
        
        if platform == "youtube":
            required = YOUTUBE_REQUIRED_COOKIES
            missing = required - found
            
            if missing:
                return {
                    "valid": False,
                    "message": f"Cookie 不完整，缺少: {', '.join(missing)}",
                }
            return {
                "valid": True,
                "message": "已验证 (检测到 YouTube 登录)",
            }
        else:
            if cookies:
                return {"valid": True, "message": f"找到 {len(cookies)} 个 Cookie"}
            return {"valid": False, "message": "未找到 Cookie"}
    
    def _detect_account_hint(self, cookies: list[dict]) -> str | None:
        """尝试检测账户信息"""
        # 检查是否有 Premium 相关标识
        for c in cookies:
            name = c.get("name", "").lower()
            value = c.get("value", "").lower()
            if "premium" in name or "premium" in value:
                return "YouTube Premium"
        return None
    
    def _update_status_from_file(self, file_path: str) -> None:
        """从文件更新状态"""
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")
            cookies = self._parse_netscape_cookies(content)
            validation = self._validate_cookies(cookies, "youtube")
            
            self._last_status = AuthStatus(
                valid=validation["valid"],
                message=validation["message"],
                cookie_count=len(cookies),
                last_updated=datetime.fromtimestamp(
                    Path(file_path).stat().st_mtime
                ).isoformat(),
            )
        except Exception as e:
            self._last_status = AuthStatus(valid=False, message=f"读取失败: {e}")
    
    # ==================== 配置持久化 ====================
    
    def _save_config(self) -> None:
        """保存配置"""
        data = {
            "version": 2,
            "source": self._current_source.value,
            "file_path": self._current_file_path,
            "auto_refresh": self._auto_refresh,
            "updated_at": datetime.now().isoformat(),
        }
        with open(self._config_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2))
    
    def _load_config(self) -> None:
        """加载配置"""
        if not self._config_path.exists():
            # 默认使用 Edge 浏览器
            self._current_source = AuthSourceType.EDGE
            self._auto_refresh = True
            logger.info("首次启动，默认使用 Edge 浏览器验证")
            self._save_config()
            return
        
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            source_value = data.get("source", "edge")  # 默认 edge
            # 如果是 none，自动切换为 edge
            if source_value == "none":
                source_value = "edge"
            self._current_source = AuthSourceType(source_value)
            self._current_file_path = data.get("file_path")
            self._auto_refresh = data.get("auto_refresh", True)
            logger.info(f"已加载验证配置: {self.current_source_display}")
            
            # 尝试恢复上次的验证状态
            self._restore_last_status()
        except Exception as e:
            logger.error(f"加载验证配置失败: {e}")
            # 加载失败时使用默认的 Edge
            self._current_source = AuthSourceType.EDGE
    
    def _restore_last_status(self) -> None:
        """恢复上次的验证状态（从缓存文件）"""
        if self._current_source == AuthSourceType.NONE:
            return
        
        try:
            if self._current_source == AuthSourceType.FILE:
                # 文件模式：检查文件是否存在
                if self._current_file_path and Path(self._current_file_path).exists():
                    self._update_status_from_file(self._current_file_path)
            elif self._current_source in BROWSER_SOURCES:
                # 浏览器模式：检查缓存文件
                cache_file = self.cache_dir / f"cached_{self._current_source.value}_youtube.txt"
                if cache_file.exists():
                    self._update_status_from_file(str(cache_file))
                    # 检查缓存是否过期（超过 1 小时标记为需要刷新）
                    mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
                    age_hours = (datetime.now() - mtime).total_seconds() / 3600
                    if age_hours > 1:
                        self._last_status.message += " (缓存可能过期)"
        except Exception as e:
            logger.debug(f"恢复状态失败: {e}")
    
    def startup_refresh(self) -> AuthStatus:
        """
        启动时自动刷新 Cookie
        
        在应用启动时调用，自动获取 Cookie 并验证有效性。
        
        Returns:
            刷新后的状态
        """
        if self._current_source == AuthSourceType.NONE:
            # 如果当前是 NONE，切换到默认的 Edge
            self._current_source = AuthSourceType.EDGE
            self._save_config()
        
        if self._current_source == AuthSourceType.FILE:
            # 文件模式不自动刷新，只检查文件
            if self._current_file_path and Path(self._current_file_path).exists():
                self._update_status_from_file(self._current_file_path)
            else:
                self._last_status = AuthStatus(
                    valid=False,
                    message="Cookie 文件不存在，请重新选择"
                )
            return self._last_status
        
        # 浏览器模式：自动刷新
        logger.info(f"启动时自动刷新 Cookie ({self.current_source_display})...")
        try:
            cookie_path = self.get_cookie_file_for_ytdlp("youtube", force_refresh=True)
            if cookie_path:
                logger.info(f"Cookie 刷新成功: {self._last_status.message}")
            else:
                logger.warning(f"Cookie 刷新失败: {self._last_status.message}")
        except Exception as e:
            logger.error(f"启动刷新失败: {e}")
            self._last_status = AuthStatus(valid=False, message=f"刷新失败: {e}")
        
        return self._last_status
    
    # ==================== 高级：多账户管理 ====================
    
    def get_profiles(self) -> list[AuthProfile]:
        """获取所有配置文件"""
        self._load_profiles()
        return list(self._profiles.values())
    
    def add_profile(self, profile: AuthProfile) -> None:
        """添加配置"""
        key = f"{profile.platform}_{profile.name}"
        self._profiles[key] = profile
        self._save_profiles()
    
    def remove_profile(self, name: str, platform: str = "youtube") -> bool:
        """移除配置"""
        key = f"{platform}_{name}"
        if key in self._profiles:
            del self._profiles[key]
            self._save_profiles()
            return True
        return False
    
    def _save_profiles(self) -> None:
        """保存配置文件"""
        data = {
            "version": 1,
            "profiles": [p.to_dict() for p in self._profiles.values()],
        }
        with open(self._profiles_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2))
    
    def _load_profiles(self) -> None:
        """加载配置文件"""
        if not self._profiles_path.exists():
            return
        try:
            with open(self._profiles_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for p_data in data.get("profiles", []):
                profile = AuthProfile.from_dict(p_data)
                key = f"{profile.platform}_{profile.name}"
                self._profiles[key] = profile
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
    
    def cleanup_cache(self, max_age_hours: int = 24) -> int:
        """清理过期缓存"""
        cleaned = 0
        now = datetime.now()
        
        for f in self.cache_dir.glob("cached_*.txt"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                age_hours = (now - mtime).total_seconds() / 3600
                if age_hours > max_age_hours:
                    f.unlink()
                    cleaned += 1
            except Exception:
                pass
        
        return cleaned


# 全局单例
auth_service = AuthService()
