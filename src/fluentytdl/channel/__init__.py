"""
FluentYTDL 频道功能域

包含频道信息获取、视频列表、归档管理等功能。
"""

from .channel_service import (
    ChannelService,
    ChannelInfo,
    VideoItem,
    ChannelInfoWorker,
    VideoListWorker,
    channel_service,
)
from .archive_manager import ArchiveManager, archive_manager

__all__ = [
    "ChannelService",
    "ChannelInfo",
    "VideoItem",
    "ChannelInfoWorker",
    "VideoListWorker",
    "channel_service",
    "ArchiveManager",
    "archive_manager",
]
