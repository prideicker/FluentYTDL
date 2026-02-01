"""
aria2c 集成管理模块

负责:
- aria2c 可执行文件的检测和管理
- aria2c 下载参数的构建
- 断点续传的状态管理
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..core.config_manager import config_manager
from ..utils.paths import locate_runtime_tool, is_frozen, find_bundled_executable
from ..utils.logger import logger


class Aria2cManager:
    """aria2c 集成管理器
    
    提供 aria2c 下载器的检测、配置和参数构建功能。
    支持多线程加速、断点续传等高级特性。
    """
    
    _instance: "Aria2cManager | None" = None
    
    # aria2c 默认参数
    DEFAULT_CONNECTIONS = 16  # 单文件连接数
    DEFAULT_SPLIT = 16        # 文件分片数
    DEFAULT_MIN_SPLIT_SIZE = "1M"  # 最小分片大小
    
    def __new__(cls) -> "Aria2cManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self) -> None:
        self._exe_path: Path | None = None
        self._version: str | None = None
    
    def is_available(self) -> bool:
        """检查 aria2c 是否可用"""
        return self.get_exe_path() is not None
    
    def get_exe_path(self) -> Path | None:
        """获取 aria2c 可执行文件路径
        
        优先级:
        1. 配置文件中指定的路径
        2. 项目 bin 目录下的 aria2c
        3. 系统 PATH 中的 aria2c
        """
        if self._exe_path and self._exe_path.exists():
            return self._exe_path
            
        # 1. 配置文件路径
        cfg_path = str(config_manager.get("aria2c_path") or "").strip()
        if cfg_path:
            p = Path(cfg_path)
            if p.exists():
                self._exe_path = p
                return p
        
        # 2. 项目 bin 目录
        try:
            p = locate_runtime_tool("aria2c.exe", "aria2c/aria2c.exe")
            self._exe_path = p
            return p
        except FileNotFoundError:
            pass
        
        # 2.1 冻结模式下的 bundled 搜索
        if is_frozen():
            p = find_bundled_executable("aria2c.exe", "aria2c/aria2c.exe")
            if p:
                self._exe_path = p
                return p
        
        # 3. 系统 PATH
        which = shutil.which("aria2c") or shutil.which("aria2c.exe")
        if which:
            self._exe_path = Path(which)
            return self._exe_path
        
        return None
    
    def get_version(self) -> str:
        """获取 aria2c 版本号"""
        if self._version:
            return self._version
            
        exe = self.get_exe_path()
        if not exe:
            return "未安装"
        
        try:
            kwargs: dict[str, Any] = {}
            if os.name == "nt":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0
                kwargs["startupinfo"] = si
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            
            result = subprocess.run(
                [str(exe), "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                **kwargs
            )
            
            if result.returncode == 0:
                # aria2 version 1.37.0
                first_line = result.stdout.strip().split("\n")[0]
                if "aria2 version" in first_line:
                    self._version = first_line.replace("aria2 version", "").strip()
                else:
                    self._version = first_line
                return self._version
        except Exception as e:
            logger.warning(f"获取 aria2c 版本失败: {e}")
        
        return "未知版本"
    
    def build_downloader_args(self, opts: dict[str, Any] | None = None) -> list[str]:
        """构建 aria2c 下载参数
        
        Args:
            opts: 可选的配置覆盖
            
        Returns:
            aria2c 参数列表
        """
        opts = opts or {}
        args: list[str] = []
        
        # 连接数 (单服务器)
        connections = opts.get("aria2c_connections") or config_manager.get("aria2c_connections", self.DEFAULT_CONNECTIONS)
        args.extend(["-x", str(connections)])
        
        # 分片数
        split = opts.get("aria2c_split") or config_manager.get("aria2c_split", self.DEFAULT_SPLIT)
        args.extend(["-s", str(split)])
        
        # 最小分片大小
        min_split = opts.get("aria2c_min_split_size") or config_manager.get("aria2c_min_split_size", self.DEFAULT_MIN_SPLIT_SIZE)
        args.extend(["-k", str(min_split)])
        
        # 断点续传 (默认启用)
        if config_manager.get("aria2c_continue", True):
            args.append("-c")
        
        # 允许覆盖文件
        args.append("--allow-overwrite=true")
        
        # 下载限速 (如果设置)
        rate_limit = opts.get("rate_limit") or config_manager.get("rate_limit", "")
        if rate_limit:
            args.extend(["--max-download-limit", str(rate_limit)])
        
        # 文件分配方式 (预分配可加速大文件)
        file_allocation = config_manager.get("aria2c_file_allocation", "falloc")
        if file_allocation:
            args.extend(["--file-allocation", file_allocation])
        
        # 禁用证书验证 (某些情况下需要)
        if config_manager.get("aria2c_check_certificate", True) is False:
            args.append("--check-certificate=false")
        
        # 重试次数
        retries = config_manager.get("aria2c_max_tries", 5)
        args.extend(["--max-tries", str(retries)])
        
        # 重试等待时间
        retry_wait = config_manager.get("aria2c_retry_wait", 3)
        args.extend(["--retry-wait", str(retry_wait)])
        
        # 连接超时
        connect_timeout = config_manager.get("aria2c_connect_timeout", 60)
        args.extend(["--connect-timeout", str(connect_timeout)])
        
        # 超时时间
        timeout = config_manager.get("aria2c_timeout", 60)
        args.extend(["--timeout", str(timeout)])
        
        # 启用 HTTP Keep-Alive
        args.append("--enable-http-keep-alive=true")
        
        # 启用 HTTP Pipelining
        args.append("--enable-http-pipelining=true")
        
        # 用户代理 (可选)
        user_agent = opts.get("user_agent") or config_manager.get("aria2c_user_agent", "")
        if user_agent:
            args.extend(["--user-agent", user_agent])
        
        return args
    
    def get_yt_dlp_options(self, opts: dict[str, Any] | None = None) -> dict[str, Any]:
        """获取 yt-dlp 的外部下载器配置
        
        Args:
            opts: 可选的配置覆盖
            
        Returns:
            yt-dlp 格式的配置字典
        """
        if not config_manager.get("use_aria2c", False):
            return {}
        
        if not self.is_available():
            logger.warning("aria2c 已启用但未找到可执行文件，回退到内置下载器")
            return {}
        
        aria2c_args = self.build_downloader_args(opts)
        
        ydl_opts: dict[str, Any] = {
            "external_downloader": "aria2c",
            "external_downloader_args": {
                "aria2c": aria2c_args
            }
        }
        
        # 如果配置了 aria2c 路径，添加到 PATH
        exe_path = self.get_exe_path()
        if exe_path:
            ydl_opts["__aria2c_exe_dir"] = str(exe_path.parent)
        
        return ydl_opts
    
    def is_enabled(self) -> bool:
        """检查 aria2c 是否已启用"""
        return config_manager.get("use_aria2c", False) and self.is_available()


# 全局单例
aria2c_manager = Aria2cManager()
