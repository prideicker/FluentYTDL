"""
POT (Proof of Origin Token) Provider Manager

管理 bgutil-ytdlp-pot-provider 服务的生命周期，为 yt-dlp 提供 PO Token 以绕过 YouTube 的机器人检测。

核心功能：
- 动态端口分配
- 健康检查
- 僵尸进程管理
- Windows Job Objects 支持
"""
from __future__ import annotations

import atexit
import socket
import subprocess
import sys
import time
import threading
from pathlib import Path
from typing import Optional

from loguru import logger

from ..utils.paths import find_bundled_executable, frozen_app_dir


class POTManager:
    """PO Token 服务管理器（单例）"""
    
    _instance: Optional["POTManager"] = None
    
    # 端口范围
    DEFAULT_PORT = 4416
    PORT_RANGE = 10
    
    def __new__(cls) -> "POTManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self._process: Optional[subprocess.Popen] = None
        self._active_port: int = 0
        self._is_running: bool = False
        self._job_handle = None  # Windows Job Object
        self._lock = threading.Lock()
        
        # 注册退出清理
        atexit.register(self.stop_server)
        
        # Windows: 设置 Job Object
        if sys.platform == "win32":
            self._setup_job_object()
    
    def _setup_job_object(self):
        """创建 Windows Job Object，确保子进程随父进程终止"""
        try:
            import win32job
            
            self._job_handle = win32job.CreateJobObject(None, "FluentYTDL_POT_Job")
            info = win32job.QueryInformationJobObject(
                self._job_handle, 
                win32job.JobObjectExtendedLimitInformation
            )
            info['BasicLimitInformation']['LimitFlags'] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(
                self._job_handle, 
                win32job.JobObjectExtendedLimitInformation, 
                info
            )
            logger.debug("POT Manager: Windows Job Object 已创建")
        except Exception as e:
            logger.warning(f"POT Manager: 创建 Job Object 失败: {e}")
            self._job_handle = None
    
    def _find_available_port(self) -> int:
        """查找可用端口"""
        for offset in range(self.PORT_RANGE):
            port = self.DEFAULT_PORT + offset
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                if s.connect_ex(('127.0.0.1', port)) != 0:
                    return port
        
        # 兜底：让 OS 分配
        with socket.socket() as s:
            s.bind(('', 0))
            return s.getsockname()[1]
    
    def _find_pot_executable(self) -> Optional[Path]:
        """查找 POT Provider 可执行文件"""
        candidates = [
            "pot-provider/bgutil-pot-provider.exe",
            "bgutil-pot-provider.exe",
            "pot-provider/bgutil-ytdlp-pot-provider.exe",
            "bgutil-ytdlp-pot-provider.exe",
        ]
        
        for candidate in candidates:
            exe = find_bundled_executable(candidate)
            if exe and exe.exists():
                return exe
        
        # 尝试 frozen_app_dir 下的 bin 目录
        app_dir = frozen_app_dir()
        for subdir in ["bin/pot-provider", "pot-provider", "bin"]:
            for name in ["bgutil-pot-provider.exe", "bgutil-ytdlp-pot-provider.exe"]:
                p = app_dir / subdir / name
                if p.exists():
                    return p
        
        return None
    
    def _cleanup_orphan_servers(self):
        """清理残留的 POT 服务进程"""
        import urllib.request
        
        for port in range(self.DEFAULT_PORT, self.DEFAULT_PORT + self.PORT_RANGE):
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/shutdown",
                    method='POST'
                )
                urllib.request.urlopen(req, timeout=0.3)
                logger.info(f"POT Manager: 已关闭残留服务 (端口 {port})")
            except Exception:
                pass
    
    def _health_check(self, timeout: float = 3.0) -> bool:
        """健康检查：确认服务端口已就绪"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                # 使用 socket 检测端口是否在监听
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.5)
                    result = s.connect_ex(('127.0.0.1', self._active_port))
                    if result == 0:
                        # 端口已在监听
                        logger.debug(f"POT Manager: 端口 {self._active_port} 已就绪")
                        return True
            except Exception:
                pass
            time.sleep(0.2)
        return False
    
    def start_server(self) -> bool:
        """启动 POT 服务"""
        with self._lock:
            if self._is_running and self._process and self._process.poll() is None:
                logger.debug("POT Manager: 服务已在运行")
                return True
            
            # 查找可执行文件
            exe = self._find_pot_executable()
            if not exe:
                logger.warning("POT Manager: 未找到 POT Provider 可执行文件")
                return False
            
            # 清理残留
            self._cleanup_orphan_servers()
            
            # 查找可用端口
            self._active_port = self._find_available_port()
            logger.info(f"POT Manager: 使用端口 {self._active_port}")
            
            try:
                # bgutil-pot-provider 的命令行参数格式
                # 显式指定 --host 127.0.0.1 以确保监听 IPv4
                cmd = [str(exe), "server", "--host", "127.0.0.1", "--port", str(self._active_port), "--verbose"]
                
                creation_flags = 0
                if sys.platform == "win32":
                    creation_flags = subprocess.CREATE_NO_WINDOW
                
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=creation_flags,
                )
                
                # Windows: 关联到 Job Object
                if self._job_handle and sys.platform == "win32":
                    try:
                        import win32job
                        import win32api
                        import win32con
                        
                        handle = win32api.OpenProcess(
                            win32con.PROCESS_ALL_ACCESS, 
                            False, 
                            self._process.pid
                        )
                        win32job.AssignProcessToJobObject(self._job_handle, handle)
                    except Exception as e:
                        logger.warning(f"POT Manager: 关联 Job Object 失败: {e}")
                
                # 健康检查（增加超时到 10 秒）
                logger.debug(f"POT Manager: 开始健康检查 (PID: {self._process.pid})")
                if self._health_check(timeout=10.0):
                    self._is_running = True
                    logger.info(f"POT Manager: 服务已启动 (PID: {self._process.pid}, 端口: {self._active_port})")
                    return True
                else:
                    # 检查进程是否还在运行
                    if self._process.poll() is None:
                        # 进程还在运行，可能只是健康检查未通过
                        logger.warning("POT Manager: 健康检查未通过，但进程仍在运行，标记为已启动")
                        self._is_running = True
                        return True
                    else:
                        # 进程已退出，获取输出以便调试
                        stdout, stderr = self._process.communicate(timeout=1)
                        if stderr:
                            logger.error(f"POT Manager 进程 stderr: {stderr.decode('utf-8', errors='ignore')[:500]}")
                        if stdout:
                            logger.debug(f"POT Manager 进程 stdout: {stdout.decode('utf-8', errors='ignore')[:500]}")
                        logger.error(f"POT Manager: 进程已退出 (返回码: {self._process.returncode})")
                        return False
                    
            except Exception as e:
                logger.error(f"POT Manager: 启动服务失败: {e}")
                return False
    
    def stop_server(self):
        """停止 POT 服务"""
        with self._lock:
            # 防止重复停止（如果进程已经不存在了）
            if not self._is_running and self._process is None:
                logger.debug("POT Manager: 服务未运行，跳过停止操作")
                return
            
            if self._process:
                try:
                    # 检查进程是否已经终止
                    if self._process.poll() is not None:
                        logger.debug("POT Manager: 进程已终止，跳过停止操作")
                        self._process = None
                        self._is_running = False
                        self._active_port = 0
                        return
                    
                    self._process.terminate()
                    self._process.wait(timeout=2)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
                finally:
                    self._process = None
            
            self._is_running = False
            self._active_port = 0
            logger.info("POT Manager: 服务已停止")
    
    def is_running(self) -> bool:
        """检查服务是否运行中"""
        if not self._is_running:
            return False
        if self._process and self._process.poll() is not None:
            self._is_running = False
            return False
        return True
    
    def get_extractor_args(self) -> Optional[str]:
        """获取 yt-dlp 的 extractor-args 参数"""
        if not self.is_running():
            return None
        return f"youtubepot-bgutilhttp:base_url=http://127.0.0.1:{self._active_port}"
    
    @property
    def active_port(self) -> int:
        return self._active_port


# 单例实例
pot_manager = POTManager()
