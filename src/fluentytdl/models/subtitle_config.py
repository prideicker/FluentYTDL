"""
FluentYTDL 字幕配置数据模型

定义字幕下载和处理的配置选项。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class SubtitleConfig:
    """
    字幕配置
    
    控制字幕下载、嵌入、格式转换等行为。
    """
    
    # ========== 基础配置 ==========
    
    enabled: bool = False
    """是否启用字幕下载（全局开关）"""
    
    default_languages: list[str] = field(default_factory=lambda: ["zh-Hans", "en"])
    """默认字幕语言优先级列表（按优先级排序）"""
    
    enable_auto_captions: bool = True
    """是否启用自动生成字幕（当手动字幕不可用时）"""
    
    # ========== 嵌入配置 ==========
    
    embed_mode: Literal["always", "never", "ask"] = "always"
    """
    字幕嵌入模式：
    - always: 总是嵌入到视频文件
    - never: 总是保存为单独文件
    - ask: 每次下载时询问
    """
    
    write_separate_file: bool = True
    """是否同时保存单独的字幕文件（即使嵌入到视频）"""
    
    # ========== 格式配置 ==========
    
    format: Literal["srt", "ass", "vtt", "lrc"] = "srt"
    """字幕格式偏好"""
    
    # ========== 双语字幕配置 ==========
    
    enable_bilingual: bool = False
    """是否启用双语字幕合成"""
    
    bilingual_primary: str = "zh-Hans"
    """双语字幕主语言（显示在上方）"""
    
    bilingual_secondary: str = "en"
    """双语字幕副语言（显示在下方）"""
    
    bilingual_style: Literal["top-bottom", "inline"] = "top-bottom"
    """
    双语字幕排列样式：
    - top-bottom: 上下排列
    - inline: 行内排列（主/副）
    """
    
    # ========== 质量与后处理 ==========
    
    quality_check: bool = True
    """是否启用字幕质量检查（检测空文件、损坏文件）"""
    
    remove_ads: bool = False
    """是否自动移除字幕中的广告内容（实验性功能）"""
    
    # ========== 高级选项 ==========
    
    fallback_to_english: bool = True
    """当首选语言不可用时，是否自动回退到英语"""
    
    max_languages: int = 2
    """最多下载字幕语言数量（防止过多字幕文件）"""
    
    def to_dict(self) -> dict:
        """转换为字典格式（用于保存到 JSON）"""
        return {
            "enabled": self.enabled,
            "default_languages": self.default_languages,
            "enable_auto_captions": self.enable_auto_captions,
            "embed_mode": self.embed_mode,
            "write_separate_file": self.write_separate_file,
            "format": self.format,
            "enable_bilingual": self.enable_bilingual,
            "bilingual_primary": self.bilingual_primary,
            "bilingual_secondary": self.bilingual_secondary,
            "bilingual_style": self.bilingual_style,
            "quality_check": self.quality_check,
            "remove_ads": self.remove_ads,
            "fallback_to_english": self.fallback_to_english,
            "max_languages": self.max_languages,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> SubtitleConfig:
        """从字典创建配置对象"""
        return cls(
            enabled=data.get("enabled", False),
            default_languages=data.get("default_languages", ["zh-Hans", "en"]),
            enable_auto_captions=data.get("enable_auto_captions", True),
            embed_mode=data.get("embed_mode", "always"),
            write_separate_file=data.get("write_separate_file", True),
            format=data.get("format", "srt"),
            enable_bilingual=data.get("enable_bilingual", False),
            bilingual_primary=data.get("bilingual_primary", "zh-Hans"),
            bilingual_secondary=data.get("bilingual_secondary", "en"),
            bilingual_style=data.get("bilingual_style", "top-bottom"),
            quality_check=data.get("quality_check", True),
            remove_ads=data.get("remove_ads", False),
            fallback_to_english=data.get("fallback_to_english", True),
            max_languages=data.get("max_languages", 2),
        )
    
    def get_yt_dlp_opts(self) -> dict:
        """
        生成 yt-dlp 选项字典
        
        根据配置自动生成 yt-dlp 需要的参数。
        """
        if not self.enabled:
            return {}
        
        opts = {
            "writesubtitles": True,
            "writeautomaticsub": self.enable_auto_captions,
            "subtitleslangs": self.default_languages[:self.max_languages],
        }
        
        # 嵌入字幕
        if self.embed_mode == "always":
            opts["embedsubtitles"] = True
        
        # 格式转换
        if self.format in ["srt", "ass", "vtt"]:
            opts["convertsubtitles"] = self.format
        
        return opts
