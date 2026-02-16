"""Cookies 同步管理器 - 负责从浏览器提取 Cookies 并存储为托管文件

核心功能:
1. 从浏览器提取 Cookies 并保存为 Netscape 格式文件
2. 检测浏览器进程是否运行 (避免文件锁冲突)
3. 启动时静默同步 (Best-Effort)
4. 报错时自动修复 (Self-Healing)
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

from ..utils.logger import logger
from ..youtube.yt_dlp_cli import _win_hide_console_kwargs, prepare_yt_dlp_env, resolve_yt_dlp_exe
from .config_manager import config_manager

if TYPE_CHECKING:
    pass


class BrowserRunningError(Exception):
    """浏览器运行中导致无法自动修复的错误"""
    pass


class CookieSyncManager:
    """Cookies 同步管理器单例
    
    负责:
    - 从浏览器提取 Cookies 到托管文件
    - 检测浏览器进程状态
    - 实现启动时自动同步和报错时自愈逻辑
    """
    
    _instance: CookieSyncManager | None = None
    _lock = Lock()

    # 浏览器进程名映射
    BROWSER_PROCESS_MAP = {
        "chrome": ["chrome.exe", "googlechrome.exe"],
        "edge": ["msedge.exe"],
        "firefox": ["firefox.exe"],
        "brave": ["brave.exe"],
        "opera": ["opera.exe"],
        "vivaldi": ["vivaldi.exe"],
    }

    def __new__(cls) -> CookieSyncManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._syncing = False  # 防止并发同步

    @staticmethod
    def get_managed_cookie_path() -> Path:
        """获取托管 Cookie 文件的路径
        
        Returns:
            Path: %APPDATA%/FluentYTDL/cookies/auto_synced.txt
        """
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "FluentYTDL" / "cookies"
        try:
            base.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return base / "auto_synced.txt"

    def is_browser_running(self, browser: str) -> bool:
        """检测目标浏览器是否正在运行
        
        Args:
            browser: 浏览器标识 (chrome/edge/firefox 等)
            
        Returns:
            bool: True 表示浏览器正在运行
        """
        targets = self.BROWSER_PROCESS_MAP.get(browser.lower(), [f"{browser}.exe"])
        
        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                **_win_hide_console_kwargs()
            )
            output_lower = result.stdout.lower()
            for proc in targets:
                if proc.lower() in output_lower:
                    return True
        except subprocess.TimeoutExpired:
            logger.warning("检测浏览器进程超时")
        except Exception as e:
            logger.warning(f"检测浏览器进程失败: {e}")
        return False

    def sync_now(self, browser: str | None = None) -> tuple[bool, str]:
        """执行 Cookies 同步操作
        
        使用 yt-dlp 从浏览器提取 Cookies 并保存到托管文件。
        
        Args:
            browser: 浏览器标识，默认从配置读取
            
        Returns:
            (success: bool, message: str) 元组
        """
        if self._syncing:
            return False, "同步正在进行中，请稍候"
        
        self._syncing = True
        try:
            browser = browser or str(config_manager.get("cookie_browser") or "edge").strip()
            target_path = self.get_managed_cookie_path()
            
            exe = resolve_yt_dlp_exe()
            if exe is None:
                return False, "未找到 yt-dlp.exe，请检查安装"

            # 构建命令
            # --cookies-from-browser 提取，--cookies 保存到文件
            # --skip-download 跳过实际下载
            # 使用 robots.txt 作为轻量级 URL（避免触发复杂解析）
            cmd = [
                str(exe),
                "--cookies-from-browser", browser,
                "--cookies", str(target_path),
                "--skip-download",
                "--no-warnings",
                "--no-progress",
                "https://www.youtube.com/robots.txt"
            ]

            logger.info(f"开始同步 Cookies: browser={browser}, target={target_path}")
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=prepare_yt_dlp_env(),
                    timeout=60,  # 给足够时间
                    **_win_hide_console_kwargs()
                )
                
                stderr = (result.stderr or "").strip()
                (result.stdout or "").strip()
                
                if result.returncode != 0:
                    # 分析错误类型
                    error_lower = stderr.lower()
                    if "could not copy" in error_lower or "permission" in error_lower:
                        return False, f"提取失败：{browser.title()} 浏览器可能正在运行。请完全关闭后重试。"
                    if "no cookies" in error_lower:
                        return False, f"未能从 {browser.title()} 提取到 Cookies。请确认已登录 YouTube。"
                    return False, f"yt-dlp 错误 (code={result.returncode}): {stderr[:300]}"
                
                # 验证文件是否成功创建
                if not target_path.exists():
                    return False, "Cookie 文件未创建"
                
                file_size = target_path.stat().st_size
                if file_size < 100:
                    return False, f"Cookie 文件过小 ({file_size} bytes)，可能为空"
                
                # 验证文件格式 (简单检查)
                try:
                    with open(target_path, encoding="utf-8", errors="ignore") as f:
                        header = f.read(100)
                    if not header.startswith("#") and "youtube" not in header.lower():
                        logger.warning("Cookie 文件格式可能不标准，但仍尝试使用")
                except Exception:
                    pass
                
                # 更新配置
                config_manager.set("cookie_managed_path", str(target_path))
                config_manager.set("cookie_last_sync_time", time.time())
                
                logger.info(f"Cookies 同步成功: {target_path} ({file_size} bytes)")
                return True, f"已从 {browser.title()} 同步 Cookies"

            except subprocess.TimeoutExpired:
                return False, "同步超时 (60秒)，请检查网络或重试"
            except Exception as e:
                logger.exception("Cookies 同步异常")
                return False, f"同步异常: {e}"
                
        finally:
            self._syncing = False

    def try_startup_sync(self) -> None:
        """启动时静默尝试同步 (Best-Effort)
        
        仅在以下条件满足时执行:
        1. cookie_auto_sync_enabled 配置为 True
        2. 目标浏览器未运行
        
        静默执行，不会弹窗打扰用户。
        """
        try:
            if not config_manager.get("cookie_auto_sync_enabled", True):
                logger.debug("自动同步已禁用，跳过启动同步")
                return
            
            # 检查上次同步时间，避免频繁同步
            last_sync = float(config_manager.get("cookie_last_sync_time") or 0)
            now = time.time()
            hours_since_sync = (now - last_sync) / 3600
            
            if hours_since_sync < 1:  # 1小时内同步过
                logger.debug(f"上次同步仅 {hours_since_sync:.1f} 小时前，跳过")
                return
            
            browser = str(config_manager.get("cookie_browser") or "edge").strip()
            
            if self.is_browser_running(browser):
                logger.info(f"浏览器 {browser} 正在运行，跳过启动同步")
                return
            
            success, msg = self.sync_now(browser)
            if success:
                logger.info(f"启动同步成功: {msg}")
            else:
                logger.warning(f"启动同步失败: {msg}")
                
        except Exception as e:
            logger.warning(f"启动同步异常: {e}")

    def try_error_recovery(self) -> bool:
        """报错时尝试自动修复
        
        当下载/解析遇到认证错误时调用此方法尝试自愈。
        
        Returns:
            True: 修复成功，调用者应重试操作
            
        Raises:
            BrowserRunningError: 浏览器运行中，需要用户介入
        """
        browser = str(config_manager.get("cookie_browser") or "edge").strip()
        
        if self.is_browser_running(browser):
            # 无法自动修复，需要用户介入
            raise BrowserRunningError(
                f"认证失败：Cookies 可能已过期。\n"
                f"检测到 {browser.title()} 浏览器正在运行，无法自动更新。\n"
                f"请关闭浏览器后重试。"
            )
        
        logger.info("尝试自动修复：重新同步 Cookies")
        success, msg = self.sync_now(browser)
        
        if success:
            logger.info(f"自愈成功: {msg}")
            return True
        else:
            logger.warning(f"自愈失败: {msg}")
            return False

    def get_sync_status(self) -> dict:
        """获取当前同步状态信息
        
        Returns:
            dict: {
                "has_managed_file": bool,
                "managed_path": str,
                "last_sync_time": float,
                "last_sync_ago_hours": float,
                "browser": str,
            }
        """
        managed_path = str(config_manager.get("cookie_managed_path") or "")
        last_sync = float(config_manager.get("cookie_last_sync_time") or 0)
        now = time.time()
        
        return {
            "has_managed_file": bool(managed_path) and Path(managed_path).exists(),
            "managed_path": managed_path,
            "last_sync_time": last_sync,
            "last_sync_ago_hours": (now - last_sync) / 3600 if last_sync > 0 else -1,
            "browser": str(config_manager.get("cookie_browser") or "edge"),
        }


# 单例实例
cookie_sync_manager = CookieSyncManager()
