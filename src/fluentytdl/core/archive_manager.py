"""
FluentYTDL 归档管理模块

提供已下载视频的持久化记录和增量更新检查:
- 归档记录存储
- 下载状态检查
- 增量更新逻辑
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from .config_manager import config_manager
from ..utils.logger import logger


@dataclass
class ArchiveEntry:
    """归档条目"""
    video_id: str
    title: str
    channel_id: str = ""
    channel_name: str = ""
    download_time: str = ""
    file_path: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> ArchiveEntry:
        return cls(
            video_id=data.get("video_id", ""),
            title=data.get("title", ""),
            channel_id=data.get("channel_id", ""),
            channel_name=data.get("channel_name", ""),
            download_time=data.get("download_time", ""),
            file_path=data.get("file_path", ""),
        )


class ArchiveManager:
    """
    归档管理器
    
    管理已下载视频的记录，支持:
    - 标记视频为已下载
    - 检查视频是否已下载
    - 获取频道的下载历史
    - 持久化到 JSON 文件
    """
    
    def __init__(self, archive_file: Path | str | None = None):
        if archive_file:
            self._archive_path = Path(archive_file)
        else:
            # 默认路径
            self._archive_path = self._get_default_path()
        
        self._entries: dict[str, ArchiveEntry] = {}  # video_id -> entry
        self._channel_index: dict[str, set[str]] = {}  # channel_id -> {video_ids}
        self._dirty = False
        
        self._load()
    
    def _get_default_path(self) -> Path:
        """获取默认归档文件路径"""
        archive_path = config_manager.get("archive_file")
        if archive_path:
            return Path(archive_path)
        
        # 使用配置目录
        config_dir = Path.home() / ".fluentytdl"
        config_dir.mkdir(exist_ok=True)
        return config_dir / "archive.json"
    
    def _load(self):
        """加载归档记录"""
        if not self._archive_path.exists():
            return
        
        try:
            with open(self._archive_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            entries = data.get("entries", [])
            for entry_data in entries:
                entry = ArchiveEntry.from_dict(entry_data)
                self._entries[entry.video_id] = entry
                
                # 建立频道索引
                if entry.channel_id:
                    if entry.channel_id not in self._channel_index:
                        self._channel_index[entry.channel_id] = set()
                    self._channel_index[entry.channel_id].add(entry.video_id)
            
            logger.info(f"已加载 {len(self._entries)} 条归档记录")
            
        except Exception as e:
            logger.error(f"加载归档记录失败: {e}")
    
    def save(self):
        """保存归档记录"""
        if not self._dirty:
            return
        
        try:
            self._archive_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "version": 1,
                "updated": datetime.now().isoformat(),
                "entries": [e.to_dict() for e in self._entries.values()],
            }
            
            with open(self._archive_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self._dirty = False
            logger.info(f"已保存 {len(self._entries)} 条归档记录")
            
        except Exception as e:
            logger.error(f"保存归档记录失败: {e}")
    
    def is_downloaded(self, video_id: str) -> bool:
        """检查视频是否已下载"""
        return video_id in self._entries
    
    def mark_downloaded(
        self,
        video_id: str,
        title: str = "",
        channel_id: str = "",
        channel_name: str = "",
        file_path: str = "",
    ):
        """标记视频为已下载"""
        entry = ArchiveEntry(
            video_id=video_id,
            title=title,
            channel_id=channel_id,
            channel_name=channel_name,
            download_time=datetime.now().isoformat(),
            file_path=file_path,
        )
        
        self._entries[video_id] = entry
        
        if channel_id:
            if channel_id not in self._channel_index:
                self._channel_index[channel_id] = set()
            self._channel_index[channel_id].add(video_id)
        
        self._dirty = True
        self.save()
    
    def unmark(self, video_id: str):
        """取消标记"""
        if video_id in self._entries:
            entry = self._entries.pop(video_id)
            
            if entry.channel_id and entry.channel_id in self._channel_index:
                self._channel_index[entry.channel_id].discard(video_id)
            
            self._dirty = True
            self.save()
    
    def get_entry(self, video_id: str) -> ArchiveEntry | None:
        """获取归档条目"""
        return self._entries.get(video_id)
    
    def get_channel_downloads(self, channel_id: str) -> list[ArchiveEntry]:
        """获取频道的所有下载记录"""
        video_ids = self._channel_index.get(channel_id, set())
        return [self._entries[vid] for vid in video_ids if vid in self._entries]
    
    def get_channel_download_count(self, channel_id: str) -> int:
        """获取频道的下载数量"""
        return len(self._channel_index.get(channel_id, set()))
    
    def filter_new_videos(self, video_ids: list[str]) -> list[str]:
        """过滤出未下载的视频"""
        return [vid for vid in video_ids if vid not in self._entries]
    
    def get_all_entries(self) -> list[ArchiveEntry]:
        """获取所有归档条目"""
        return list(self._entries.values())
    
    def get_recent_entries(self, limit: int = 50) -> list[ArchiveEntry]:
        """获取最近的归档条目"""
        entries = sorted(
            self._entries.values(),
            key=lambda e: e.download_time,
            reverse=True
        )
        return entries[:limit]
    
    def count(self) -> int:
        """归档条目总数"""
        return len(self._entries)
    
    def clear(self):
        """清空所有记录"""
        self._entries.clear()
        self._channel_index.clear()
        self._dirty = True
        self.save()
    
    def export_to_txt(self, output_path: Path | str) -> int:
        """
        导出为 yt-dlp 兼容的 archive.txt 格式
        
        Returns:
            导出的条目数
        """
        output = Path(output_path)
        count = 0
        
        with open(output, "w", encoding="utf-8") as f:
            for entry in self._entries.values():
                # yt-dlp 格式: youtube VIDEO_ID
                f.write(f"youtube {entry.video_id}\n")
                count += 1
        
        return count
    
    def import_from_txt(self, txt_path: Path | str) -> int:
        """
        从 yt-dlp archive.txt 导入
        
        Returns:
            导入的条目数
        """
        txt = Path(txt_path)
        if not txt.exists():
            return 0
        
        count = 0
        with open(txt, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                
                parts = line.split()
                if len(parts) >= 2:
                    # youtube VIDEO_ID 格式
                    video_id = parts[1]
                    if video_id not in self._entries:
                        self.mark_downloaded(video_id, title="(imported)")
                        count += 1
        
        return count


# 全局归档管理器
archive_manager = ArchiveManager()
