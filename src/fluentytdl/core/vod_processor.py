"""
FluentYTDL HLS/VOD 处理模块 (M8)

提供 HLS 协议识别、VOD 处理功能:
- HLS 流检测
- VOD 格式识别
- 自动转码修复
- 断流恢复
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QThread

from .config_manager import config_manager
from ..utils.logger import logger


@dataclass
class StreamInfo:
    """流信息"""
    url: str
    format_id: str = ""
    protocol: str = ""  # https, m3u8, m3u8_native, http_dash_segments
    ext: str = ""
    resolution: str = ""
    fps: int = 0
    vcodec: str = ""
    acodec: str = ""
    filesize: int = 0
    is_hls: bool = False
    is_dash: bool = False
    is_live: bool = False
    
    @property
    def is_streaming_protocol(self) -> bool:
        """是否为流媒体协议"""
        return self.is_hls or self.is_dash
    
    @property
    def needs_remux(self) -> bool:
        """是否需要重新封装"""
        # HLS 通常需要转封装为 MP4
        return self.is_hls or self.protocol in ("m3u8", "m3u8_native")


def detect_protocol(format_info: dict) -> str:
    """检测流协议类型"""
    protocol = format_info.get("protocol", "")
    
    if not protocol:
        url = format_info.get("url", "")
        if ".m3u8" in url:
            return "m3u8"
        elif ".mpd" in url:
            return "dash"
    
    return protocol


def is_hls_stream(format_info: dict) -> bool:
    """检查是否为 HLS 流"""
    protocol = detect_protocol(format_info)
    return protocol in ("m3u8", "m3u8_native", "hls")


def is_dash_stream(format_info: dict) -> bool:
    """检查是否为 DASH 流"""
    protocol = detect_protocol(format_info)
    return protocol in ("http_dash_segments", "dash")


def get_best_format_for_hls(info: dict) -> str:
    """从 HLS 流获取最佳格式"""
    formats = info.get("formats", [])
    
    # 过滤 HLS 格式
    hls_formats = [f for f in formats if is_hls_stream(f)]
    
    if not hls_formats:
        return "best"
    
    # 按分辨率排序
    def resolution_key(f):
        height = f.get("height", 0) or 0
        return height
    
    hls_formats.sort(key=resolution_key, reverse=True)
    
    best = hls_formats[0]
    return best.get("format_id", "best")


def get_remux_options(output_path: Path, target_format: str = "mp4") -> dict:
    """
    获取转封装选项
    
    用于将 HLS/DASH 流转封装为标准容器格式。
    """
    opts = {
        "merge_output_format": target_format,
        "postprocessors": [
            {
                "key": "FFmpegVideoRemuxer",
                "preferedformat": target_format,
            }
        ],
    }
    
    # 如果需要修复时间戳
    fix_timestamps = config_manager.get("hls_fix_timestamps", True)
    if fix_timestamps:
        opts["postprocessor_args"] = {
            "ffmpeg": ["-avoid_negative_ts", "make_zero"]
        }
    
    return opts


def get_vod_options(info: dict) -> dict:
    """
    获取 VOD 处理选项
    
    根据视频信息返回最佳下载选项。
    """
    opts = {}
    
    # 检测是否为直播回放
    info.get("is_live", False)
    was_live = info.get("live_status") == "was_live"
    
    if was_live:
        # 直播回放可能需要特殊处理
        opts["live_from_start"] = False  # 确保从头下载
        
    # 检查格式
    formats = info.get("formats", [])
    has_hls = any(is_hls_stream(f) for f in formats)
    has_dash = any(is_dash_stream(f) for f in formats)
    
    if has_hls:
        # HLS 优先选择分段下载
        opts["hls_prefer_native"] = False
        opts["hls_use_mpegts"] = True
        
    if has_dash:
        # DASH 使用原生解析
        pass
    
    return opts


class StreamAnalyzer(QThread):
    """流分析线程"""
    
    analyzed = Signal(object)  # StreamInfo
    error = Signal(str)
    
    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self._cancelled = False
    
    def run(self):
        try:
            from .youtube_service import YoutubeService
            
            service = YoutubeService()
            info = service.extract_info_sync(self.url)
            
            if self._cancelled:
                return
            
            if not info:
                self.error.emit("无法获取视频信息")
                return
            
            # 分析格式
            formats = info.get("formats", [])
            requested = info.get("requested_formats", [])
            
            # 使用请求的格式或最佳格式
            target = requested[0] if requested else (formats[-1] if formats else {})
            
            stream_info = StreamInfo(
                url=self.url,
                format_id=target.get("format_id", ""),
                protocol=detect_protocol(target),
                ext=target.get("ext", info.get("ext", "")),
                resolution=target.get("resolution", ""),
                fps=target.get("fps", 0) or 0,
                vcodec=target.get("vcodec", ""),
                acodec=target.get("acodec", ""),
                filesize=target.get("filesize", 0) or 0,
                is_hls=is_hls_stream(target),
                is_dash=is_dash_stream(target),
                is_live=info.get("is_live", False),
            )
            
            self.analyzed.emit(stream_info)
            
        except Exception as e:
            if not self._cancelled:
                logger.error(f"分析流失败: {e}")
                self.error.emit(str(e))
    
    def cancel(self):
        self._cancelled = True


class RemuxWorker(QThread):
    """转封装线程"""
    
    progress = Signal(int)  # 0-100
    finished = Signal(str)  # output_path
    error = Signal(str)
    
    def __init__(
        self,
        input_path: Path,
        output_path: Path,
        target_format: str = "mp4",
        parent=None
    ):
        super().__init__(parent)
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.target_format = target_format
        self._cancelled = False
    
    def run(self):
        try:
            from ..utils.paths import find_bundled_executable
            
            # 查找 ffmpeg
            ffmpeg = find_bundled_executable("ffmpeg")
            if not ffmpeg:
                self.error.emit("未找到 ffmpeg")
                return
            
            # 构建命令
            cmd = [
                str(ffmpeg),
                "-i", str(self.input_path),
                "-c", "copy",  # 无损复制
                "-avoid_negative_ts", "make_zero",
                "-y",  # 覆盖
                str(self.output_path)
            ]
            
            # 执行
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            # 监控进度
            while process.poll() is None:
                if self._cancelled:
                    process.terminate()
                    return
                self.msleep(500)
            
            if process.returncode == 0:
                self.finished.emit(str(self.output_path))
            else:
                stderr = process.stderr.read().decode("utf-8", errors="ignore")
                self.error.emit(f"转封装失败: {stderr[:200]}")
                
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
    
    def cancel(self):
        self._cancelled = True


class VODProcessor(QObject):
    """
    VOD 处理器
    
    提供 VOD/HLS 视频的分析和转码功能。
    """
    
    stream_analyzed = Signal(object)  # StreamInfo
    remux_completed = Signal(str)     # output_path
    error = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._analyzer: StreamAnalyzer | None = None
        self._remuxer: RemuxWorker | None = None
    
    def analyze_stream(self, url: str):
        """分析流"""
        if self._analyzer:
            self._analyzer.cancel()
        
        self._analyzer = StreamAnalyzer(url, self)
        self._analyzer.analyzed.connect(self.stream_analyzed)
        self._analyzer.error.connect(self.error)
        self._analyzer.start()
    
    def remux_file(self, input_path: str, output_path: str = None, target_format: str = "mp4"):
        """转封装文件"""
        input_p = Path(input_path)
        
        if not output_path:
            output_path = input_p.with_suffix(f".{target_format}")
        
        if self._remuxer:
            self._remuxer.cancel()
        
        self._remuxer = RemuxWorker(input_p, Path(output_path), target_format, self)
        self._remuxer.finished.connect(self.remux_completed)
        self._remuxer.error.connect(self.error)
        self._remuxer.start()
    
    def get_download_options(self, url: str, stream_info: StreamInfo = None) -> dict:
        """
        获取下载选项
        
        根据流信息返回最佳下载配置。
        """
        opts = {}
        
        if stream_info:
            if stream_info.is_hls:
                opts.update({
                    "hls_prefer_native": False,
                    "merge_output_format": "mp4",
                })
            
            if stream_info.needs_remux:
                opts["postprocessors"] = [
                    {
                        "key": "FFmpegVideoRemuxer",
                        "preferedformat": "mp4",
                    }
                ]
        
        return opts
    
    def cancel_all(self):
        """取消所有操作"""
        if self._analyzer:
            self._analyzer.cancel()
        if self._remuxer:
            self._remuxer.cancel()


# 全局处理器
vod_processor = VODProcessor()
