"""
FluentYTDL 后处理功能域

包含音频处理、字幕管理、片段下载、广告跳过等功能。
"""

from .audio_processor import AudioProcessor, audio_processor
from .subtitle_manager import (
    extract_subtitle_tracks,
    get_subtitle_languages,
    build_subtitle_opts,
    SubtitleTrack,
)
from .subtitle_service import (
    SubtitleService,
    subtitle_service,
    SubtitleStrategy,
    SmartStrategy,
    SingleLanguageStrategy,
    MultiLanguageStrategy,
)
from .subtitle_processor import (
    SubtitleProcessor,
    subtitle_processor,
    SubtitleProcessResult,
)
from .section_download import (
    TimeRange,
    parse_time_input,
    parse_time_range,
    build_section_opts,
    lossless_cut,
)
from .sponsorblock import (
    SponsorBlockConfig,
    sponsorblock_config,
    build_sponsorblock_opts,
    extract_chapters,
    get_available_categories,
)

__all__ = [
    "AudioProcessor",
    "audio_processor",
    "extract_subtitle_tracks",
    "get_subtitle_languages",
    "build_subtitle_opts",
    "SubtitleTrack",
    "SubtitleService",
    "subtitle_service",
    "SubtitleStrategy",
    "SmartStrategy",
    "SingleLanguageStrategy",
    "MultiLanguageStrategy",
    "SubtitleProcessor",
    "subtitle_processor",
    "SubtitleProcessResult",
    "TimeRange",
    "parse_time_input",
    "parse_time_range",
    "build_section_opts",
    "lossless_cut",
    "SponsorBlockConfig",
    "sponsorblock_config",
    "build_sponsorblock_opts",
    "extract_chapters",
    "get_available_categories",
]
