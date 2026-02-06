"""
FluentYTDL YouTube 服务域

包含 YouTube 视频信息提取、yt-dlp 封装、PO Token 管理等功能。
"""

from .youtube_service import YoutubeService, YoutubeServiceOptions, youtube_service
from .yt_dlp_cli import (
    YtDlpCancelled,
    prepare_yt_dlp_env,
    resolve_yt_dlp_exe,
    ydl_opts_to_cli_args,
)
from .pot_manager import POTManager, pot_manager

__all__ = [
    # YouTube 服务
    "YoutubeService",
    "YoutubeServiceOptions",
    "youtube_service",
    # yt-dlp CLI
    "YtDlpCancelled",
    "prepare_yt_dlp_env",
    "resolve_yt_dlp_exe",
    "ydl_opts_to_cli_args",
    # PO Token 管理
    "POTManager",
    "pot_manager",
]
