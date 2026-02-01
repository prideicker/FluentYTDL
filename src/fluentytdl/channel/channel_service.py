"""
FluentYTDL 频道服务模块

提供频道信息获取和视频列表分页加载功能:
- 频道 URL 验证
- 频道信息提取
- 视频列表分页
- 防封策略
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QThread

from ..core.youtube_service import YoutubeService
from ..core.config_manager import config_manager
from ..utils.logger import logger


# 频道 URL 模式
CHANNEL_URL_PATTERNS = [
    # @handle 格式
    r'https?://(?:www\.)?youtube\.com/@([a-zA-Z0-9_\-\.]+)',
    # /channel/UC... 格式
    r'https?://(?:www\.)?youtube\.com/channel/(UC[a-zA-Z0-9_\-]+)',
    # /c/CustomName 格式
    r'https?://(?:www\.)?youtube\.com/c/([a-zA-Z0-9_\-]+)',
    # /user/Username 格式
    r'https?://(?:www\.)?youtube\.com/user/([a-zA-Z0-9_\-]+)',
]


@dataclass
class ChannelInfo:
    """频道信息"""
    channel_id: str
    name: str
    handle: str = ""
    description: str = ""
    subscriber_count: int = 0
    video_count: int = 0
    thumbnail: str = ""
    banner: str = ""
    url: str = ""
    
    @property
    def subscriber_text(self) -> str:
        """格式化订阅数"""
        if self.subscriber_count >= 1_000_000:
            return f"{self.subscriber_count / 1_000_000:.1f}M"
        elif self.subscriber_count >= 1_000:
            return f"{self.subscriber_count / 1_000:.1f}K"
        return str(self.subscriber_count)


@dataclass
class VideoItem:
    """视频项"""
    video_id: str
    title: str
    thumbnail: str = ""
    duration: int = 0
    upload_date: str = ""
    view_count: int = 0
    is_live: bool = False
    is_downloaded: bool = False
    
    @property
    def duration_text(self) -> str:
        """格式化时长"""
        if self.duration <= 0:
            return "直播" if self.is_live else "-"
        m, s = divmod(self.duration, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
    
    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


@dataclass
class VideoListResult:
    """视频列表结果"""
    videos: list[VideoItem] = field(default_factory=list)
    continuation: str | None = None  # 分页 token
    total_count: int = 0
    has_more: bool = False


def validate_channel_url(url: str) -> tuple[bool, str]:
    """
    验证频道 URL 并提取标识符
    
    Returns:
        (is_valid, channel_identifier)
    """
    url = url.strip()
    
    for pattern in CHANNEL_URL_PATTERNS:
        match = re.match(pattern, url, re.IGNORECASE)
        if match:
            return True, match.group(1)
    
    # 尝试直接作为 @handle 处理
    if url.startswith("@"):
        return True, url
    
    return False, ""


def normalize_channel_url(url_or_handle: str) -> str:
    """
    标准化频道 URL
    
    Args:
        url_or_handle: 频道 URL 或 @handle
        
    Returns:
        完整的频道 URL
    """
    url = url_or_handle.strip()
    
    # 已经是完整 URL
    if url.startswith("http"):
        return url
    
    # @handle 格式
    if url.startswith("@"):
        return f"https://www.youtube.com/{url}"
    
    # 假设是 handle
    return f"https://www.youtube.com/@{url}"


class ChannelInfoWorker(QThread):
    """频道信息获取线程"""
    
    finished = Signal(object)  # ChannelInfo | None
    error = Signal(str)
    
    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = normalize_channel_url(url)
        self._cancelled = False
    
    def run(self):
        try:
            service = YoutubeService()
            
            # 获取频道信息
            info = service.extract_info_sync(self.url)
            
            if self._cancelled:
                return
            
            if not info:
                self.error.emit("无法获取频道信息")
                return
            
            channel = ChannelInfo(
                channel_id=info.get("channel_id") or info.get("uploader_id", ""),
                name=info.get("channel") or info.get("uploader", "未知频道"),
                handle=info.get("uploader_id", ""),
                description=info.get("description", "")[:500],
                subscriber_count=info.get("channel_follower_count", 0) or 0,
                video_count=info.get("playlist_count", 0) or 0,
                thumbnail=self._get_thumbnail(info),
                url=self.url,
            )
            
            self.finished.emit(channel)
            
        except Exception as e:
            if not self._cancelled:
                logger.error(f"获取频道信息失败: {e}")
                self.error.emit(str(e))
    
    def _get_thumbnail(self, info: dict) -> str:
        """提取频道头像"""
        # 尝试多种来源
        thumbnails = info.get("thumbnails") or []
        if thumbnails:
            # 选择中等尺寸
            for t in thumbnails:
                if t.get("width", 0) >= 88:
                    return t.get("url", "")
            return thumbnails[0].get("url", "")
        return info.get("thumbnail", "")
    
    def cancel(self):
        self._cancelled = True


class VideoListWorker(QThread):
    """视频列表获取线程"""
    
    finished = Signal(object)  # VideoListResult
    error = Signal(str)
    progress = Signal(int, int)  # current, total
    
    def __init__(
        self, 
        channel_url: str, 
        continuation: str | None = None,
        page_size: int = 30,
        parent=None
    ):
        super().__init__(parent)
        self.channel_url = normalize_channel_url(channel_url)
        self.continuation = continuation
        self.page_size = page_size
        self._cancelled = False
    
    def run(self):
        try:
            # 请求间隔 (防封)
            delay = config_manager.get("channel_request_delay", 2)
            time.sleep(delay)
            
            if self._cancelled:
                return
            
            service = YoutubeService()
            
            # 构建视频列表 URL
            videos_url = self.channel_url
            if "/videos" not in videos_url:
                videos_url = videos_url.rstrip("/") + "/videos"
            
            # 获取视频列表
            info = service.extract_info_sync(videos_url)
            
            if self._cancelled:
                return
            
            if not info:
                self.error.emit("无法获取视频列表")
                return
            
            entries = info.get("entries") or []
            videos = []
            
            for i, entry in enumerate(entries[:self.page_size]):
                if self._cancelled:
                    return
                
                video = VideoItem(
                    video_id=entry.get("id", ""),
                    title=entry.get("title", "未知视频"),
                    thumbnail=entry.get("thumbnail", ""),
                    duration=entry.get("duration", 0) or 0,
                    upload_date=entry.get("upload_date", ""),
                    view_count=entry.get("view_count", 0) or 0,
                    is_live=entry.get("is_live", False),
                )
                videos.append(video)
                self.progress.emit(i + 1, len(entries))
            
            result = VideoListResult(
                videos=videos,
                continuation=None,  # yt-dlp 不直接支持分页，需要额外处理
                total_count=len(entries),
                has_more=len(entries) > self.page_size,
            )
            
            self.finished.emit(result)
            
        except Exception as e:
            if not self._cancelled:
                logger.error(f"获取视频列表失败: {e}")
                self.error.emit(str(e))
    
    def cancel(self):
        self._cancelled = True


class ChannelService(QObject):
    """
    频道服务
    
    管理频道信息获取和视频列表加载。
    """
    
    channel_loaded = Signal(object)  # ChannelInfo
    videos_loaded = Signal(object)   # VideoListResult
    error = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._info_worker: ChannelInfoWorker | None = None
        self._list_worker: VideoListWorker | None = None
    
    def load_channel(self, url: str):
        """加载频道信息"""
        # 取消之前的请求
        if self._info_worker:
            self._info_worker.cancel()
            self._info_worker.deleteLater()
        
        self._info_worker = ChannelInfoWorker(url, self)
        self._info_worker.finished.connect(self.channel_loaded)
        self._info_worker.error.connect(self.error)
        self._info_worker.start()
    
    def load_videos(self, channel_url: str, continuation: str | None = None):
        """加载视频列表"""
        if self._list_worker:
            self._list_worker.cancel()
            self._list_worker.deleteLater()
        
        self._list_worker = VideoListWorker(channel_url, continuation, parent=self)
        self._list_worker.finished.connect(self.videos_loaded)
        self._list_worker.error.connect(self.error)
        self._list_worker.start()
    
    def cancel_all(self):
        """取消所有请求"""
        if self._info_worker:
            self._info_worker.cancel()
        if self._list_worker:
            self._list_worker.cancel()


# 全局服务实例
channel_service = ChannelService()
