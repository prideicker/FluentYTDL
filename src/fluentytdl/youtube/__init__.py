"""
FluentYTDL YouTube 服务域

包含 YouTube 视频信息提取、yt-dlp 封装等功能。
"""

from .youtube_service import YoutubeService, YoutubeServiceOptions, youtube_service
from .yt_dlp_cli import (
    YtDlpCancelled,
    prepare_yt_dlp_env,
    resolve_yt_dlp_exe,
    ydl_opts_to_cli_args,
)

__all__ = [
    "YoutubeService",
    "YoutubeServiceOptions",
    "youtube_service",
    "YtDlpCancelled",
    "prepare_yt_dlp_env",
    "resolve_yt_dlp_exe",
    "ydl_opts_to_cli_args",
]
