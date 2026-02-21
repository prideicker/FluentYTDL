"""
字幕后处理器

负责下载完成后的字幕质量检查和双语合并：
- 字幕文件存在性验证
- 字幕文件完整性检查
- 双语字幕自动合并
- 后处理结果通知
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..utils.logger import logger


@dataclass
class SubtitleProcessResult:
    """字幕后处理结果"""

    success: bool
    message: str
    processed_files: list[str]  # 处理的字幕文件路径
    merged_file: str | None = None  # 双语合并后的文件路径


class SubtitleProcessor:
    """字幕后处理器 - 单例"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def process(
        self,
        output_path: str | None,
        opts: dict[str, Any],
        status_callback: Callable[[str], None] | None = None,
    ) -> SubtitleProcessResult:
        """
        执行字幕后处理

        Args:
            output_path: 视频输出路径
            opts: yt-dlp 选项字典 (包含字幕配置)
            status_callback: 状态回调函数 (用于发送状态消息)

        Returns:
            SubtitleProcessResult: 处理结果
        """
        logger.info("字幕后处理开始 - output_path={}", output_path)

        # 检查是否启用了字幕下载
        if not opts.get("writesubtitles") and not opts.get("writeautomaticsub"):
            logger.debug("字幕下载未启用，跳过后处理")
            return SubtitleProcessResult(success=True, message="字幕下载未启用", processed_files=[])

        if not output_path or not os.path.exists(output_path):
            logger.warning("视频文件不存在，无法进行字幕后处理: {}", output_path)
            return SubtitleProcessResult(
                success=False, message="视频文件不存在", processed_files=[]
            )

        video_path = Path(output_path)
        processed_files = []

        # 1. 查找并验证字幕文件
        subtitle_files = self._find_subtitle_files(video_path)

        if not subtitle_files:
            logger.warning("未找到字幕文件: {}", video_path)
            return SubtitleProcessResult(success=True, message="未找到字幕文件", processed_files=[])

        logger.info("找到 {} 个字幕文件", len(subtitle_files))

        # 2. 验证字幕文件完整性
        for sub_file in subtitle_files:
            is_valid, reason = self._validate_subtitle_file(sub_file)
            if is_valid:
                processed_files.append(str(sub_file))
                logger.info("✓ 字幕文件有效: {}", sub_file.name)
            else:
                logger.warning("✗ 字幕文件无效: {} - {}", sub_file.name, reason)

        # 3. 返回处理结果
        return SubtitleProcessResult(
            success=True,
            message=f"成功处理 {len(processed_files)} 个字幕文件",
            processed_files=processed_files,
            merged_file=None,
        )

    def _find_subtitle_files(self, video_path: Path) -> list[Path]:
        """
        查找与视频文件关联的字幕文件

        支持格式: .srt, .ass, .vtt
        命名模式: video.zh-Hans.srt, video.en.srt 等
        """
        subtitle_extensions = [".srt", ".ass", ".vtt"]
        parent_dir = video_path.parent
        stem = video_path.stem

        subtitle_files = []

        # 查找模式: {stem}.{lang}.{ext}
        for file in parent_dir.glob(f"{stem}.*"):
            if file.suffix.lower() in subtitle_extensions:
                subtitle_files.append(file)

        return subtitle_files

    def _validate_subtitle_file(self, subtitle_path: Path) -> tuple[bool, str]:
        """
        验证字幕文件完整性

        Returns:
            (is_valid, reason)
        """
        if not subtitle_path.exists():
            return False, "文件不存在"

        if subtitle_path.stat().st_size == 0:
            return False, "文件大小为 0"

        try:
            # 尝试读取文件内容（检查编码和基本格式）
            content = subtitle_path.read_text(encoding="utf-8")

            if len(content.strip()) == 0:
                return False, "文件内容为空"

            # 基本格式检查 (SRT 格式应该包含时间码)
            if subtitle_path.suffix.lower() == ".srt":
                if "-->" not in content:
                    return False, "SRT 格式缺少时间码"

            return True, "文件有效"

        except UnicodeDecodeError:
            return False, "编码错误"
        except Exception as e:
            return False, f"读取失败: {str(e)}"


# 单例实例
subtitle_processor = SubtitleProcessor()
