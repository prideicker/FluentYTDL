"""
FluentYTDL 字幕服务层

提供字幕下载和处理的统一服务接口，使用策略模式支持多种字幕下载方案。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..core.config_manager import config_manager
from ..models.subtitle_config import SubtitleConfig
from .subtitle_manager import (
    extract_subtitle_tracks,
    get_subtitle_languages,
    SubtitleTrack,
)


@dataclass
class SubtitleRequest:
    """
    字幕下载请求
    
    封装一次字幕下载所需的所有信息。
    """
    video_id: str
    """视频 ID"""
    
    video_info: dict[str, Any]
    """yt-dlp 返回的视频信息"""
    
    user_config: SubtitleConfig | None = None
    """用户指定的配置（None 表示使用全局配置）"""
    
    override_languages: list[str] | None = None
    """临时覆盖语言列表（None 表示使用配置中的语言）"""


class SubtitleStrategy(ABC):
    """
    字幕下载策略接口
    
    不同的策略实现不同的字幕下载方案（单语、双语、智能选择等）。
    """
    
    @abstractmethod
    def apply(self, request: SubtitleRequest) -> dict[str, Any]:
        """
        应用策略生成 yt-dlp 选项
        
        Args:
            request: 字幕下载请求
            
        Returns:
            yt-dlp 选项字典
        """
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """获取策略描述（用于日志和 UI 显示）"""
        pass


class NoneStrategy(SubtitleStrategy):
    """不下载字幕策略"""
    
    def apply(self, request: SubtitleRequest) -> dict[str, Any]:
        return {}
    
    def get_description(self) -> str:
        return "不下载字幕"


class SingleLanguageStrategy(SubtitleStrategy):
    """
    单语言字幕策略
    
    下载单个语言的字幕（优先手动字幕，回退自动字幕）。
    """
    
    def __init__(self, language: str, enable_auto: bool = True):
        self.language = language
        self.enable_auto = enable_auto
    
    def apply(self, request: SubtitleRequest) -> dict[str, Any]:
        tracks = extract_subtitle_tracks(request.video_info)
        
        # 检查字幕是否可用
        available = [t for t in tracks if t.lang_code == self.language]
        if not available:
            return {}
        
        config = request.user_config or config_manager.get_subtitle_config()
        
        return {
            "writesubtitles": True,
            "writeautomaticsub": self.enable_auto,
            "subtitleslangs": [self.language],
            "embedsubtitles": config.embed_mode == "always",
            "convertsubtitles": config.format if config.format in ["srt", "ass", "vtt"] else None,
        }
    
    def get_description(self) -> str:
        return f"单语言字幕: {self.language}"


class MultiLanguageStrategy(SubtitleStrategy):
    """
    多语言字幕策略
    
    下载多个语言的字幕，按优先级列表顺序尝试。
    """
    
    def __init__(self, languages: list[str], max_languages: int = 2):
        self.languages = languages
        self.max_languages = max_languages
    
    def apply(self, request: SubtitleRequest) -> dict[str, Any]:
        tracks = extract_subtitle_tracks(request.video_info)
        available_codes = {t.lang_code for t in tracks}
        
        # 按优先级筛选可用语言
        selected = []
        for lang in self.languages:
            if lang in available_codes:
                selected.append(lang)
                if len(selected) >= self.max_languages:
                    break
        
        if not selected:
            return {}
        
        config = request.user_config or config_manager.get_subtitle_config()
        
        return {
            "writesubtitles": True,
            "writeautomaticsub": config.enable_auto_captions,
            "subtitleslangs": selected,
            "embedsubtitles": config.embed_mode == "always",
            "convertsubtitles": config.format if config.format in ["srt", "ass", "vtt"] else None,
        }
    
    def get_description(self) -> str:
        return f"多语言字幕: {', '.join(self.languages[:3])}{'...' if len(self.languages) > 3 else ''}"


class SmartStrategy(SubtitleStrategy):
    """
    智能字幕策略
    
    根据视频可用字幕自动选择最佳语言：
    1. 优先中文（简体/繁体/通用）
    2. 回退英语
    3. 回退日语
    4. 如果以上都没有，选择第一个可用字幕
    """
    
    def apply(self, request: SubtitleRequest) -> dict[str, Any]:
        tracks = extract_subtitle_tracks(request.video_info)
        if not tracks:
            return {}
        
        available_codes = {t.lang_code for t in tracks}
        
        # 智能选择逻辑
        selected = []
        
        # 1. 中文优先
        for zh_variant in ["zh-Hans", "zh-Hant", "zh", "zh-CN", "zh-TW"]:
            if zh_variant in available_codes:
                selected.append(zh_variant)
                break
        
        # 2. 英语作为第二语言
        if "en" in available_codes and len(selected) < 2:
            selected.append("en")
        
        # 3. 日语作为第三选择
        if not selected and "ja" in available_codes:
            selected.append("ja")
        
        # 4. 如果还是空，使用第一个可用字幕
        if not selected and tracks:
            selected.append(tracks[0].lang_code)
        
        if not selected:
            return {}
        
        config = request.user_config or config_manager.get_subtitle_config()
        
        return {
            "writesubtitles": True,
            "writeautomaticsub": config.enable_auto_captions,
            "subtitleslangs": selected,
            "embedsubtitles": config.embed_mode == "always",
            "convertsubtitles": config.format if config.format in ["srt", "ass", "vtt"] else None,
        }
    
    def get_description(self) -> str:
        return "智能选择字幕（中文→英语→日语）"


class BilingualStrategy(SubtitleStrategy):
    """
    双语字幕策略
    
    下载两种语言并后处理合并为双语字幕文件。
    注意：合并操作在下载完成后由 SubtitleProcessor 执行。
    """
    
    def __init__(self, primary: str, secondary: str):
        self.primary = primary
        self.secondary = secondary
    
    def apply(self, request: SubtitleRequest) -> dict[str, Any]:
        tracks = extract_subtitle_tracks(request.video_info)
        available_codes = {t.lang_code for t in tracks}
        
        # 检查两种语言是否都可用
        has_primary = self.primary in available_codes
        has_secondary = self.secondary in available_codes
        
        if not (has_primary and has_secondary):
            # 回退到单语言
            if has_primary:
                return SingleLanguageStrategy(self.primary).apply(request)
            elif has_secondary:
                return SingleLanguageStrategy(self.secondary).apply(request)
            return {}
        
        config = request.user_config or config_manager.get_subtitle_config()
        
        # 下载两种语言，但不嵌入（因为需要先合并）
        return {
            "writesubtitles": True,
            "writeautomaticsub": config.enable_auto_captions,
            "subtitleslangs": [self.primary, self.secondary],
            "embedsubtitles": False,  # 双语合并后再嵌入
            "convertsubtitles": "srt",  # 强制 SRT 格式便于合并
            # 添加标记用于后处理识别
            "_bilingual_merge": True,
            "_bilingual_primary": self.primary,
            "_bilingual_secondary": self.secondary,
            "_bilingual_style": config.bilingual_style,
        }
    
    def get_description(self) -> str:
        return f"双语字幕: {self.primary} + {self.secondary}"


class SubtitleService:
    """
    字幕服务单例
    
    提供字幕下载的统一入口，管理配置和策略选择。
    """
    
    _instance: "SubtitleService | None" = None
    
    def __new__(cls) -> "SubtitleService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_config(self) -> SubtitleConfig:
        """获取当前字幕配置"""
        return config_manager.get_subtitle_config()
    
    def save_config(self, config: SubtitleConfig) -> None:
        """保存字幕配置"""
        config_manager.set_subtitle_config(config)
    
    def resolve_strategy(
        self,
        video_info: dict[str, Any],
        config: SubtitleConfig | None = None,
    ) -> SubtitleStrategy:
        """
        根据配置和视频信息解析出合适的策略
        
        Args:
            video_info: 视频信息
            config: 字幕配置（None 表示使用全局配置）
            
        Returns:
            字幕下载策略
        """
        if config is None:
            config = self.get_config()
        
        # 全局禁用
        if not config.enabled:
            return NoneStrategy()
        
        # 双语模式
        if config.enable_bilingual:
            return BilingualStrategy(
                config.bilingual_primary,
                config.bilingual_secondary,
            )
        
        # 多语言模式
        if len(config.default_languages) > 1:
            return MultiLanguageStrategy(
                config.default_languages,
                config.max_languages,
            )
        
        # 单语言模式
        if len(config.default_languages) == 1:
            return SingleLanguageStrategy(
                config.default_languages[0],
                config.enable_auto_captions,
            )
        
        # 无配置语言，使用智能策略
        return SmartStrategy()
    
    def apply(
        self,
        video_id: str,
        video_info: dict[str, Any],
        user_config: SubtitleConfig | None = None,
        override_languages: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        应用字幕策略，生成 yt-dlp 选项
        
        Args:
            video_id: 视频 ID
            video_info: 视频信息
            user_config: 用户临时配置
            override_languages: 临时覆盖语言列表
            
        Returns:
            yt-dlp 选项字典
        """
        request = SubtitleRequest(
            video_id=video_id,
            video_info=video_info,
            user_config=user_config,
            override_languages=override_languages,
        )
        
        # 如果有语言覆盖，使用多语言策略
        if override_languages:
            strategy = MultiLanguageStrategy(override_languages)
        else:
            strategy = self.resolve_strategy(video_info, user_config)
        
        return strategy.apply(request)
    
    def get_available_languages(self, video_info: dict[str, Any]) -> list[dict[str, Any]]:
        """获取视频可用字幕语言列表（用于 UI 显示）"""
        return get_subtitle_languages(video_info)


# 全局单例
subtitle_service = SubtitleService()
