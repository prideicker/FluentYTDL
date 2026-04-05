from dataclasses import dataclass


@dataclass
class PlaylistGlobalFormatOverride:
    """播放列表级别的全局格式覆盖配置"""
    download_type: str = "video_audio"  # video_audio, video_only, audio_only
    preset_id: str | None = None
    preset_intent: dict | None = None
    container_override: str | None = None
    audio_format_override: str | None = None
