"""
FluentYTDL Cookie Sentinel (Cookie 卫士)

统一管理 bin/cookies.txt 的完整生命周期：
1. 启动阶段：静默预提取 (Best-Effort，无 UAC)
2. 下载阶段：yt-dlp 始终使用统一文件
3. 容错阶段：检测 403/登录错误，提示用户授权修复
4. 来源追踪：记录 Cookie 提取来源，切换浏览器时自动清理

设计原则：
- 单例模式，全局唯一
- 启动时不干扰用户体验（无弹窗）
- 失败时提供明确的修复引导
- 严格的来源追踪，避免混用不同浏览器的 Cookie
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from ..utils.logger import logger
from .auth_service import AuthSourceType, auth_service


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
        
        # 元数据文件路径（记录 Cookie 来源）
        self.meta_path = self.cookie_path.with_suffix(".txt.meta")
        
        # 确保目录存在
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 状态追踪
        self._last_update: datetime | None = None
        self._is_updating = False
        self._update_lock = threading.Lock()
        
        # 回退状态追踪（当提取失败但有旧 Cookie 可用时）
        self._using_fallback = False
        self._fallback_warning: str | None = None
        
        logger.info(f"Cookie Sentinel 初始化: {self.cookie_path}")
    
    # ==================== 元数据管理 ====================
    
    def _load_meta(self) -> dict | None:
        """
        加载 Cookie 元数据
        
        Returns:
            元数据字典，或 None 如果不存在/无效
        """
        if not self.meta_path.exists():
            return None
        try:
            import json
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[CookieSentinel] 读取元数据失败: {e}")
            return None
    
    def _save_meta(self, source: str, cookie_count: int = 0) -> None:
        """
        保存 Cookie 元数据
        
        Args:
            source: 来源标识（如 "edge", "firefox", "file"）
            cookie_count: Cookie 数量
        """
        meta = {
            "source": source,
            "extracted_at": datetime.now().isoformat(),
            "cookie_count": cookie_count,
        }
        try:
            self.meta_path.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            logger.debug(f"[CookieSentinel] 元数据已保存: {source}, {cookie_count} cookies")
        except Exception as e:
            logger.warning(f"[CookieSentinel] 保存元数据失败: {e}")
    
    def _clear_cookie_and_meta(self) -> None:
        """清除 Cookie 文件和元数据"""
        try:
            if self.cookie_path.exists():
                self.cookie_path.unlink()
                logger.info(f"[CookieSentinel] 已删除旧 Cookie 文件: {self.cookie_path}")
            if self.meta_path.exists():
                self.meta_path.unlink()
                logger.info(f"[CookieSentinel] 已删除旧元数据文件: {self.meta_path}")
        except Exception as e:
            logger.warning(f"[CookieSentinel] 清除文件失败: {e}")
    
    def get_cookie_source(self) -> str | None:
        """
        获取当前 Cookie 文件的实际来源
        
        Returns:
            来源标识（如 "edge", "firefox"），或 None 如果无记录
        """
        meta = self._load_meta()
        return meta.get("source") if meta else None
    
    def validate_source_consistency(self, expected_source: str) -> tuple[bool, str | None]:
        """
        验证 Cookie 来源是否与期望一致
        
        Args:
            expected_source: 期望的来源（当前配置的浏览器）
            
        Returns:
            (是否一致, 实际来源) - 不再强制清理，只返回状态
        """
        if not self.exists:
            return True, None  # 没有 Cookie 文件，视为一致
        
        actual_source = self.get_cookie_source()
        if actual_source is None:
            # 旧版本的 Cookie 文件没有元数据
            logger.debug("[CookieSentinel] Cookie 文件缺少来源元数据")
            return False, None
        
        if actual_source != expected_source:
            logger.debug(
                f"[CookieSentinel] Cookie 来源不匹配: 现有={actual_source}, 期望={expected_source}"
            )
            return False, actual_source
        
        return True, actual_source
    
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
        - 失败静默处理，保留旧文件作为回退
        - 提取成功后才覆盖旧文件
        """
        def _refresh_worker():
            try:
                logger.info("[CookieSentinel] 启动时静默刷新开始...")
                
                # 重置回退状态
                self._using_fallback = False
                self._fallback_warning = None
                
                # 检查 AuthService 当前配置
                current_source = auth_service.current_source
                
                if current_source == AuthSourceType.NONE:
                    logger.info("[CookieSentinel] 未启用验证源，跳过静默刷新")
                    return
                
                # 获取期望的来源标识
                expected_source = current_source.value  # 如 "edge", "firefox", "file"
                
                # 检查来源一致性（只检查，不清理）
                is_consistent, actual_source = self.validate_source_consistency(expected_source)
                
                if current_source == AuthSourceType.FILE:
                    # 手动导入文件，直接复制
                    success = self._copy_from_auth_service()
                    if success:
                        self._save_meta("file", auth_service.last_status.cookie_count)
                        logger.info("[CookieSentinel] 已复制手动导入的Cookie文件")
                    else:
                        logger.warning("[CookieSentinel] 手动导入的Cookie文件不存在或无效")
                    return
                
                # 浏览器来源：尝试提取
                success = self._update_from_browser(silent=True)
                
                if success:
                    # 提取成功，保存元数据
                    self._save_meta(current_source.value, auth_service.last_status.cookie_count)
                    self._using_fallback = False
                    self._fallback_warning = None
                    logger.info(f"[CookieSentinel] 启动时静默刷新成功：{auth_service.current_source_display}")
                    logger.info(f"[CookieSentinel] 提取了 {auth_service.last_status.cookie_count} 个 Cookie")
                else:
                    # 提取失败，检查是否有旧 Cookie 可用作回退
                    if self.exists and actual_source:
                        # 有旧 Cookie，标记为回退状态
                        self._using_fallback = True
                        self._fallback_warning = (
                            f"配置为 {auth_service.current_source_display}，"
                            f"但提取失败，当前使用 {self._get_source_display(actual_source)} 的 Cookie"
                        )
                        logger.warning(f"[CookieSentinel] {self._fallback_warning}")
                    else:
                        logger.warning(
                            f"[CookieSentinel] 启动时静默刷新失败: "
                            f"{auth_service.last_status.message}"
                        )
                    logger.info("[CookieSentinel] 用户可在设置页点击'手动刷新'重试")
                
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
        采用延迟清理策略：只有成功提取后才覆盖旧文件。
        
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
            
            # 获取当前来源状态（只检查，不清理）
            expected_source = current_source.value
            is_consistent, actual_source = self.validate_source_consistency(expected_source)
            
            if current_source == AuthSourceType.FILE:
                success = self._copy_from_auth_service()
                if success:
                    self._save_meta("file", auth_service.last_status.cookie_count)
                    self._using_fallback = False
                    self._fallback_warning = None
                    return True, "已更新为手动导入的 Cookie 文件"
                else:
                    # 失败时保留旧文件
                    if self.exists and actual_source:
                        self._using_fallback = True
                        self._fallback_warning = f"导入失败，继续使用 {self._get_source_display(actual_source)} 的 Cookie"
                        return False, "导入失败（保留旧 Cookie）"
                    return False, "手动导入的 Cookie 文件不存在或无效"
            
            # 浏览器来源：强制刷新（允许 UAC）
            success = self._update_from_browser(silent=False, force=True)
            
            if success:
                # 提取成功，保存元数据，清除回退状态
                self._save_meta(current_source.value, auth_service.last_status.cookie_count)
                self._using_fallback = False
                self._fallback_warning = None
                msg = f"✅ Cookie 已更新（{auth_service.current_source_display}）"
                if auth_service.last_status.cookie_count > 0:
                    msg += f"\n提取了 {auth_service.last_status.cookie_count} 个 Cookie"
                return True, msg
            else:
                # 提取失败，检查是否有旧 Cookie 可用作回退
                if self.exists and actual_source:
                    self._using_fallback = True
                    self._fallback_warning = (
                        f"从 {auth_service.current_source_display} 提取失败，"
                        f"继续使用 {self._get_source_display(actual_source)} 的 Cookie"
                    )
                    return False, f"更新失败: {auth_service.last_status.message}\n（保留旧 Cookie 可用）"
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
            状态字典，包含来源信息和回退状态
        """
        actual_source = self.get_cookie_source()
        configured_source = auth_service.current_source.value if auth_service.current_source != AuthSourceType.NONE else None
        
        # 检测来源不匹配
        source_mismatch = False
        if self.exists and actual_source and configured_source:
            source_mismatch = actual_source != configured_source
        
        return {
            "exists": self.exists,
            "age_minutes": self.age_minutes,
            "is_stale": self.is_stale,
            "path": str(self.cookie_path),
            "source": auth_service.current_source_display,  # 配置的来源（显示名）
            "source_id": configured_source,  # 配置的来源 ID
            "actual_source": actual_source,  # Cookie 文件实际来源
            "actual_source_display": self._get_source_display(actual_source) if actual_source else None,
            "source_mismatch": source_mismatch,  # 是否来源不匹配
            "using_fallback": self._using_fallback,  # 是否正在使用回退
            "fallback_warning": self._fallback_warning,  # 回退警告信息
            "cookie_count": auth_service.last_status.cookie_count,
            "last_updated": self._last_update.isoformat() if self._last_update else None,
        }
    
    def _get_source_display(self, source_id: str | None) -> str:
        """获取来源的显示名称"""
        if not source_id:
            return "未知"
        display_names = {
            "edge": "Edge",
            "chrome": "Chrome",
            "chromium": "Chromium",
            "brave": "Brave",
            "opera": "Opera",
            "opera_gx": "Opera GX",
            "vivaldi": "Vivaldi",
            "arc": "Arc",
            "firefox": "Firefox",
            "librewolf": "LibreWolf",
            "file": "手动导入",
        }
        return display_names.get(source_id, source_id)
    
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
