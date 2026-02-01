"""
FluentYTDL 字幕管理模块

提供字幕下载、格式转换、双语合成等功能:
- 多语言字幕选择
- 格式转换 (SRT, ASS, VTT)
- 双语字幕合成
- 字幕嵌入
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..utils.logger import logger


# 常见字幕语言代码映射
LANGUAGE_NAMES = {
    "zh-Hans": "中文(简体)",
    "zh-Hant": "中文(繁体)",
    "zh": "中文",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "es": "西班牙语",
    "fr": "法语",
    "de": "德语",
    "ru": "俄语",
    "pt": "葡萄牙语",
    "it": "意大利语",
    "ar": "阿拉伯语",
    "hi": "印地语",
    "th": "泰语",
    "vi": "越南语",
    "id": "印尼语",
    "auto": "自动生成",
}

# 支持的字幕格式
SUBTITLE_FORMATS = ["srt", "ass", "vtt", "lrc"]


@dataclass
class SubtitleTrack:
    """字幕轨道信息"""
    lang_code: str           # 语言代码 (如 "en", "zh-Hans")
    lang_name: str           # 语言名称 (如 "English", "中文")
    is_auto: bool            # 是否自动生成
    ext: str                 # 格式 (srt, vtt, ass)
    url: str | None = None   # 下载 URL
    name: str | None = None  # 显示名称
    
    @property
    def display_name(self) -> str:
        """获取显示名称"""
        name = LANGUAGE_NAMES.get(self.lang_code, self.lang_name or self.lang_code)
        if self.is_auto:
            name += " [自动]"
        return name


def extract_subtitle_tracks(info: dict[str, Any]) -> list[SubtitleTrack]:
    """
    从视频信息中提取可用字幕轨道
    
    Args:
        info: yt-dlp 返回的视频信息
        
    Returns:
        字幕轨道列表
    """
    tracks = []
    
    # 手动字幕
    subtitles = info.get("subtitles") or {}
    for lang_code, sub_list in subtitles.items():
        if not sub_list:
            continue
        # 取第一个格式
        sub = sub_list[0] if isinstance(sub_list, list) else sub_list
        tracks.append(SubtitleTrack(
            lang_code=lang_code,
            lang_name=sub.get("name", ""),
            is_auto=False,
            ext=sub.get("ext", "vtt"),
            url=sub.get("url"),
        ))
    
    # 自动生成字幕
    auto_subs = info.get("automatic_captions") or {}
    for lang_code, sub_list in auto_subs.items():
        if not sub_list:
            continue
        sub = sub_list[0] if isinstance(sub_list, list) else sub_list
        tracks.append(SubtitleTrack(
            lang_code=lang_code,
            lang_name=sub.get("name", ""),
            is_auto=True,
            ext=sub.get("ext", "vtt"),
            url=sub.get("url"),
        ))
    
    return tracks


def get_subtitle_languages(info: dict[str, Any]) -> list[dict[str, Any]]:
    """
    获取可用字幕语言列表（用于 UI 显示）
    
    Args:
        info: 视频信息
        
    Returns:
        [{"code": "en", "name": "英语", "auto": False}, ...]
    """
    tracks = extract_subtitle_tracks(info)
    
    # 去重：同一语言优先手动字幕
    seen = {}
    for t in tracks:
        key = t.lang_code
        if key not in seen or (not t.is_auto and seen[key]["auto"]):
            seen[key] = {
                "code": t.lang_code,
                "name": t.display_name,
                "auto": t.is_auto,
                "ext": t.ext,
            }
    
    # 排序：中文 > 英语 > 日语 > 其他
    priority = ["zh-Hans", "zh-Hant", "zh", "en", "ja", "ko"]
    
    def sort_key(item):
        code = item["code"]
        try:
            return (0, priority.index(code))
        except ValueError:
            return (1, code)
    
    return sorted(seen.values(), key=sort_key)


def build_subtitle_opts(
    languages: list[str],
    embed: bool = True,
    convert_to: str | None = "srt",
    write_sub: bool = False,
) -> dict[str, Any]:
    """
    构建字幕下载的 yt-dlp 选项
    
    Args:
        languages: 语言代码列表 ["zh-Hans", "en"]
        embed: 是否嵌入到视频
        convert_to: 转换格式 (srt, ass, vtt)
        write_sub: 是否写入单独文件
        
    Returns:
        yt-dlp 选项字典
    """
    opts: dict[str, Any] = {}
    
    if not languages:
        return opts
    
    # 设置字幕语言
    opts["subtitleslangs"] = languages
    opts["writesubtitles"] = True
    
    # 也下载自动字幕
    opts["writeautomaticsub"] = True
    
    # 嵌入字幕
    if embed:
        opts["embedsubtitles"] = True
        # 需要添加后处理器
        if "postprocessors" not in opts:
            opts["postprocessors"] = []
        opts["postprocessors"].append({"key": "FFmpegEmbedSubtitle"})
    
    # 格式转换
    if convert_to and convert_to in SUBTITLE_FORMATS:
        opts["convertsubtitles"] = convert_to
    
    # 写入单独文件
    if write_sub:
        opts["writesubtitles"] = True
    elif not embed:
        # 如果既不嵌入也不写文件，则不处理
        return {}
    
    return opts


def convert_subtitle(
    input_path: str | Path,
    output_format: str,
    output_path: str | Path | None = None,
    ffmpeg_path: str | None = None,
) -> Path:
    """
    转换字幕格式
    
    Args:
        input_path: 输入字幕文件
        output_format: 目标格式 (srt, ass, vtt)
        output_path: 输出路径，None 则自动生成
        ffmpeg_path: ffmpeg 路径
        
    Returns:
        输出文件路径
    """
    input_path = Path(input_path)
    
    if output_format not in SUBTITLE_FORMATS:
        raise ValueError(f"不支持的字幕格式: {output_format}")
    
    if output_path is None:
        output_path = input_path.with_suffix(f".{output_format}")
    else:
        output_path = Path(output_path)
    
    # 使用 ffmpeg 转换
    ffmpeg = ffmpeg_path or "ffmpeg"
    cmd = [
        ffmpeg,
        "-y",  # 覆盖输出
        "-i", str(input_path),
        str(output_path),
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 转换失败: {result.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("字幕转换超时")
    
    return output_path


def merge_subtitles(
    primary_path: str | Path,
    secondary_path: str | Path,
    output_path: str | Path | None = None,
    style: str = "top-bottom",
) -> Path:
    """
    合成双语字幕
    
    Args:
        primary_path: 主字幕路径 (显示在上方)
        secondary_path: 副字幕路径 (显示在下方)
        output_path: 输出路径
        style: 样式 ("top-bottom", "inline")
        
    Returns:
        输出文件路径
    """
    primary_path = Path(primary_path)
    secondary_path = Path(secondary_path)
    
    if output_path is None:
        stem = primary_path.stem
        output_path = primary_path.parent / f"{stem}_bilingual.srt"
    else:
        output_path = Path(output_path)
    
    # 解析两个 SRT 文件
    primary_subs = _parse_srt(primary_path)
    secondary_subs = _parse_srt(secondary_path)
    
    # 合并：按时间对齐
    merged = _align_and_merge(primary_subs, secondary_subs, style)
    
    # 写入输出
    _write_srt(merged, output_path)
    
    return output_path


@dataclass
class SrtEntry:
    """SRT 字幕条目"""
    index: int
    start: str  # 时间码 "00:00:00,000"
    end: str
    text: str
    
    @property
    def start_ms(self) -> int:
        return _timestr_to_ms(self.start)
    
    @property
    def end_ms(self) -> int:
        return _timestr_to_ms(self.end)


def _timestr_to_ms(timestr: str) -> int:
    """将 SRT 时间码转换为毫秒"""
    # 00:00:00,000
    match = re.match(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})", timestr)
    if not match:
        return 0
    h, m, s, ms = map(int, match.groups())
    return h * 3600000 + m * 60000 + s * 1000 + ms


def _ms_to_timestr(ms: int) -> str:
    """将毫秒转换为 SRT 时间码"""
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms_part = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms_part:03d}"


def _parse_srt(path: Path) -> list[SrtEntry]:
    """解析 SRT 文件"""
    content = path.read_text(encoding="utf-8", errors="replace")
    entries = []
    
    # 按空行分割
    blocks = re.split(r"\n\s*\n", content.strip())
    
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        
        try:
            index = int(lines[0])
            times = lines[1]
            match = re.match(r"(.+?)\s*-->\s*(.+)", times)
            if not match:
                continue
            start, end = match.groups()
            text = "\n".join(lines[2:])
            
            entries.append(SrtEntry(index, start.strip(), end.strip(), text))
        except (ValueError, IndexError):
            continue
    
    return entries


def _write_srt(entries: list[SrtEntry], path: Path) -> None:
    """写入 SRT 文件"""
    lines = []
    for i, entry in enumerate(entries, 1):
        lines.append(str(i))
        lines.append(f"{entry.start} --> {entry.end}")
        lines.append(entry.text)
        lines.append("")
    
    path.write_text("\n".join(lines), encoding="utf-8")


def _align_and_merge(
    primary: list[SrtEntry],
    secondary: list[SrtEntry],
    style: str,
) -> list[SrtEntry]:
    """对齐并合并字幕"""
    merged = []
    s_idx = 0
    
    for p in primary:
        # 找到时间重叠的副字幕
        matching_secondary = []
        for s in secondary[s_idx:]:
            # 检查时间重叠
            if s.end_ms < p.start_ms:
                s_idx += 1
                continue
            if s.start_ms > p.end_ms:
                break
            matching_secondary.append(s)
        
        # 合并文本
        if matching_secondary:
            secondary_text = "\n".join(s.text for s in matching_secondary)
            if style == "inline":
                merged_text = f"{p.text} / {secondary_text}"
            else:  # top-bottom
                merged_text = f"{p.text}\n{secondary_text}"
        else:
            merged_text = p.text
        
        merged.append(SrtEntry(
            index=len(merged) + 1,
            start=p.start,
            end=p.end,
            text=merged_text,
        ))
    
    return merged
