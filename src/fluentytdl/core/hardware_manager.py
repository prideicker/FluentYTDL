"""
硬件资源管理与风险评估模块

负责:
1. 获取系统硬件信息 (内存, GPU)
2. 评估高负载任务 (如 VR 转码) 的风险等级
3. 提供进程优先级控制工具
"""

from __future__ import annotations

import os
import subprocess
from enum import Enum

import psutil

from .environment_checker import EnvironmentChecker


class RiskLevel(Enum):
    SAFE = "safe"
    WARNING = "warning"
    CRITICAL = "critical"

class HardwareManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._env_checker = EnvironmentChecker()
        self._initialized = True

    def refresh_hardware_status(self) -> None:
        """刷新硬件检测状态"""
        self._env_checker.refresh()

    def get_system_memory_gb(self) -> float:
        """获取系统物理内存 (GB)"""
        try:
            mem = psutil.virtual_memory()
            return round(mem.total / (1024**3), 1)
        except Exception:
            return 0.0

    def has_dedicated_gpu(self) -> bool:
        """
        粗略检测是否有独立显卡
        
        依赖 environment_checker 的编码器检测结果作为代理指标。
        如果有 h264_nvenc (NVIDIA) 或 h264_amf (AMD)，通常意味着有独显。
        h264_qsv 通常是 Intel 核显，但也可能在 Arc 独显上。
        """
        encoders = self._env_checker.check_gpu_encoders()
        # 只要有硬件编码器，我们暂时都认为"有加速能力"，不管是不是独显
        # 但为了区分风险，我们可以认为 NVENC/AMF 比 QSV 更"强" (在旧设备上)
        # 这里简化处理：只要有硬件编码器列表非空，就返回 True
        return len(encoders) > 0

    def get_gpu_encoders(self) -> list[str]:
        return self._env_checker.check_gpu_encoders()

    def assess_transcode_risk(self, video_height: int) -> RiskLevel:
        """
        评估转码风险
        
        Args:
            video_height: 视频高度 (如 2160, 4320)
            
        Returns:
            RiskLevel
        """
        mem_gb = self.get_system_memory_gb()
        has_hw = self.has_dedicated_gpu()
        
        # 8K (4320p) 及以上
        if video_height >= 3840:
            if not has_hw:
                # 8K + 纯 CPU = 必死
                return RiskLevel.CRITICAL
            if mem_gb < 16:
                # 8K + 内存不足 = 容易崩溃
                return RiskLevel.CRITICAL
            return RiskLevel.WARNING # 8K 即使有显卡也可能很慢
            
        # 5K/6K (2880p ~ 3840p)
        elif video_height >= 2880:
            if not has_hw:
                return RiskLevel.WARNING
            if mem_gb < 8:
                return RiskLevel.WARNING
            return RiskLevel.SAFE
            
        # 4K (2160p) 及以下
        else:
            if not has_hw and video_height >= 1440:
                 # CPU 转 2K/4K 会卡，但不至于死机
                return RiskLevel.WARNING
            return RiskLevel.SAFE

    def get_ffmpeg_creation_flags(self) -> int:
        """获取低优先级的进程创建标志"""
        if os.name == "nt":
            # IDLE_PRIORITY_CLASS = 0x00000040
            # CREATE_NO_WINDOW = 0x08000000
            return subprocess.CREATE_NO_WINDOW | 0x00000040
        return 0

    def get_optimal_ffmpeg_threads(self, is_cpu_mode: bool) -> int:
        """
        获取建议的 FFmpeg 线程数
        
        Args:
            is_cpu_mode: 是否为纯 CPU 转码
            
        Returns:
            建议的线程数 (int)
        """
        try:
            cpu_count = os.cpu_count() or 4
            if not is_cpu_mode:
                # GPU 模式下，CPU 主要是解封装和音频处理，不需要太多线程
                return min(4, cpu_count)
            else:
                # CPU 模式下，留 2 个核给系统，最少 1 个
                return max(1, cpu_count - 2)
        except Exception:
            return 2

hardware_manager = HardwareManager()
