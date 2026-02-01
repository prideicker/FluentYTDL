"""
FluentYTDL Cookie Sentinel (Cookie 卫士)

统一管理 bin/cookies.txt 的完整生命周期：
1. 启动阶段：静默预提取 (Best-Effort，无 UAC)
2. 下载阶段：yt-dlp 始终使用统一文件
3. 容错阶段：检测 403/登录错误，提示用户授权修复

设计原则：
- 单例模式，全局唯一
- 启动时不干扰用户体验（无弹窗）
- 失败时提供明确的修复引导
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from ..utils.logger import logger
from .auth_service import auth_service, AuthSourceType


class CookieSentinel:
    """
    Cookie 卫士 - 统一 Cookie 生命周期管理
    
    核心职责：
    1. 维护唯一的 bin/cookies.txt 文件
    2. 启动时静默尝试更新（Best-Effort）
    3. 提供错误检测与修复接口
    """
    
    _instance: CookieSentinel | None = None
    _lock = threading.Lock()
    
    def __new__(cls, cookie_path: Path | None = None) -> CookieSentinel:
        if cls._instance is not None:
            return cls._instance
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, cookie_path: Path | None = None):
        """
        初始化 Cookie 卫士
        
        Args:
            cookie_path: cookies.txt 文件路径，默认 bin/cookies.txt
        """
        if getattr(self, "_initialized", False):
            return
        
        self._initialized = True
        
        # 统一的 Cookie 文件路径
        if cookie_path is None:
            # 默认路径：应用目录/bin/cookies.txt
            try:
                from ..utils.paths import frozen_app_dir, is_frozen
                if is_frozen():
                    # 打包环境：使用可执行文件所在目录
                    root = frozen_app_dir()
                else:
                    # 开发环境：使用项目根目录
                    from ..utils.paths import project_root
                    root = project_root()
                self.cookie_path = root / "bin" / "cookies.txt"
            except Exception:
                # Fallback: 使用临时目录
                import tempfile
                self.cookie_path = Path(tempfile.gettempdir()) / "fluentytdl_cookies.txt"
        else:
            self.cookie_path = cookie_path
        
        # 确保目录存在
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 状态追踪
        self._last_update: datetime | None = None
        self._is_updating = False
        self._update_lock = threading.Lock()
        
        logger.info(f"Cookie Sentinel 初始化: {self.cookie_path}")
    
    # ==================== 公共接口 ====================
    
    @property
    def exists(self) -> bool:
        """Cookie 文件是否存在"""
        return self.cookie_path.exists()
    
    @property
    def age_minutes(self) -> float | None:
        """Cookie 文件年龄（分钟），不存在返回 None"""
        if not self.exists:
            return None
        try:
            mtime = datetime.fromtimestamp(self.cookie_path.stat().st_mtime)
            return (datetime.now() - mtime).total_seconds() / 60
        except Exception:
            return None
    
    @property
    def is_stale(self) -> bool:
        """Cookie 文件是否过期（超过 30 分钟）"""
        age = self.age_minutes
        return age is None or age > 30
    
    def get_cookie_file_path(self) -> str:
        """
        获取 Cookie 文件路径（供 yt-dlp 使用）
        
        Returns:
            cookies.txt 的绝对路径字符串
        """
        return str(self.cookie_path.absolute())
    
    def silent_refresh_on_startup(self) -> None:
        """
        启动时静默刷新 Cookie（Best-Effort）
        
        特点：
        - 非阻塞（后台线程）
        - 不请求 UAC（只尝试普通权限浏览器）
        - 失败静默处理，保留旧文件
        """
        def _refresh_worker():
            try:
                logger.info("[CookieSentinel] 启动时静默刷新开始...")
                
                # 检查 AuthService 当前配置
                current_source = auth_service.current_source
                
                if current_source == AuthSourceType.NONE:
                    logger.info("[CookieSentinel] 未启用验证源，跳过静默刷新")
                    return
                
                if current_source == AuthSourceType.FILE:
                    # 手动导入文件，直接复制
                    success = self._copy_from_auth_service()
                    if success:
                        logger.info("[CookieSentinel] 已复制手动导入的Cookie文件")
                    else:
                        logger.warning("[CookieSentinel] 手动导入的Cookie文件不存在或无效")
                    return
                
                # 浏览器来源：尝试提取
                # 注意：这里不使用 force_refresh，让 AuthService 决定是否需要更新
                success = self._update_from_browser(silent=True)
                
                if success:
                    logger.info(f"[CookieSentinel] 启动时静默刷新成功：{auth_service.current_source_display}")
                    logger.info(f"[CookieSentinel] 提取了 {auth_service.last_status.cookie_count} 个 Cookie")
                else:
                    # 静默失败，记录日志但不影响启动
                    logger.warning(
                        f"[CookieSentinel] 启动时静默刷新失败（预期行为）: "
                        f"{auth_service.last_status.message}"
                    )
                    logger.info(
                        "[CookieSentinel] 用户可在设置页点击'手动刷新'重试"
                    )
                
            except Exception as e:
                # 静默失败，不影响启动
                logger.warning(f"[CookieSentinel] 启动时静默刷新异常（预期行为）: {e}")
        
        # 在后台线程执行，不阻塞主线程
        thread = threading.Thread(target=_refresh_worker, daemon=True, name="CookieSentinel-SilentRefresh")
        thread.start()
    
    def force_refresh_with_uac(self) -> tuple[bool, str]:
        """
        强制刷新 Cookie（允许 UAC 提权）
        
        用于用户手动触发修复或下载失败后的重试。
        
        Returns:
            (成功标志, 状态消息)
        """
        with self._update_lock:
            if self._is_updating:
                return False, "正在更新中，请稍候..."
            
            self._is_updating = True
        
        try:
            logger.info("[CookieSentinel] 用户触发强制刷新（允许 UAC）")
            
            current_source = auth_service.current_source
            
            if current_source == AuthSourceType.NONE:
                return False, "未配置验证源，请先在设置中选择浏览器或导入 Cookie 文件"
            
            if current_source == AuthSourceType.FILE:
                success = self._copy_from_auth_service()
                if success:
                    return True, "已更新为手动导入的 Cookie 文件"
                else:
                    return False, "手动导入的 Cookie 文件不存在或无效"
            
            # 浏览器来源：强制刷新（允许 UAC）
            success = self._update_from_browser(silent=False, force=True)
            
            if success:
                msg = f"✅ Cookie 已更新（{auth_service.current_source_display}）"
                if auth_service.last_status.cookie_count > 0:
                    msg += f"\n提取了 {auth_service.last_status.cookie_count} 个 Cookie"
                return True, msg
            else:
                return False, f"更新失败: {auth_service.last_status.message}"
        
        except Exception as e:
            logger.error(f"[CookieSentinel] 强制刷新异常: {e}", exc_info=True)
            return False, f"更新异常: {e}"
        
        finally:
            self._is_updating = False
    
    def detect_cookie_error(self, ytdlp_stderr: str) -> bool:
        """
        检测 yt-dlp 错误是否由 Cookie 失效引起
        
        Args:
            ytdlp_stderr: yt-dlp 的标准错误输出
            
        Returns:
            True 表示疑似 Cookie 问题
        """
        if not ytdlp_stderr:
            return False
        
        err_lower = ytdlp_stderr.lower()
        
        # Cookie 相关错误特征
        cookie_keywords = [
            "sign in to confirm your age",
            "sign in to confirm you're not a bot",
            "http error 403",
            " 403 ",
            "forbidden",
            "private video",
            "members-only",
            "this video is unavailable",
            "requires authentication",
            "login required",
        ]
        
        return any(keyword in err_lower for keyword in cookie_keywords)
    
    def get_status_info(self) -> dict:
        """
        获取当前状态信息（供 UI 显示）
        
        Returns:
            状态字典，包含：exists, age_minutes, is_stale, path, source
        """
        return {
            "exists": self.exists,
            "age_minutes": self.age_minutes,
            "is_stale": self.is_stale,
            "path": str(self.cookie_path),
            "source": auth_service.current_source_display,
            "cookie_count": auth_service.last_status.cookie_count,
            "last_updated": self._last_update.isoformat() if self._last_update else None,
        }
    
    # ==================== 内部方法 ====================
    
    def _update_from_browser(self, silent: bool = False, force: bool = False) -> bool:
        """
        从浏览器更新 Cookie
        
        Args:
            silent: 静默模式（失败不抛出异常）
            force: 强制刷新（允许 UAC）
            
        Returns:
            更新是否成功
        """
        try:
            # 通过 AuthService 获取 Cookie 文件
            # force=True 时会触发 UAC（如果需要）
            auth_cookie_file = auth_service.get_cookie_file_for_ytdlp(
                platform="youtube",
                force_refresh=force
            )
            
            if not auth_cookie_file or not Path(auth_cookie_file).exists():
                if not silent:
                    raise RuntimeError("AuthService 未能生成 Cookie 文件")
                return False
            
            # 复制到统一路径
            import shutil
            shutil.copy2(auth_cookie_file, self.cookie_path)
            
            self._last_update = datetime.now()
            logger.info(f"[CookieSentinel] Cookie 已更新: {self.cookie_path}")
            
            return True
            
        except Exception as e:
            if silent:
                logger.debug(f"[CookieSentinel] 静默更新失败: {e}")
                return False
            else:
                logger.error(f"[CookieSentinel] 更新失败: {e}")
                raise
    
    def _copy_from_auth_service(self) -> bool:
        """
        从 AuthService 当前文件复制到 bin/cookies.txt
        
        Returns:
            复制是否成功
        """
        try:
            auth_cookie_file = auth_service.get_cookie_file_for_ytdlp(platform="youtube")
            
            if not auth_cookie_file:
                return False
            
            source_path = Path(auth_cookie_file)
            if not source_path.exists():
                return False
            
            import shutil
            shutil.copy2(source_path, self.cookie_path)
            
            self._last_update = datetime.now()
            logger.info(f"[CookieSentinel] 已从 AuthService 复制 Cookie: {self.cookie_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"[CookieSentinel] 复制失败: {e}")
            return False


# 全局单例
cookie_sentinel = CookieSentinel()
