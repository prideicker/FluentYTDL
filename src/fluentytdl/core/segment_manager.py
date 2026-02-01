"""
Segment manager for handling recorded segments.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List

from PySide6.QtCore import QObject, Signal

from ..models.live_models import RecordedSegment, TimeSegment
from ..utils.logger import logger


class SegmentManager(QObject):
    """
    分段管理器
    
    管理录制的片段，支持持久化和时间轴数据生成。
    """
    
    METADATA_FILE = ".segments.json"
    
    # 信号
    segment_added = Signal(RecordedSegment)
    segment_updated = Signal(RecordedSegment)
    
    def __init__(self, output_dir: Path, parent=None):
        super().__init__(parent)
        
        self._output_dir = output_dir
        self._segments: List[RecordedSegment] = []
        self._current_segment: RecordedSegment | None = None
        
        # 尝试加载已有元数据
        self._load_metadata()
        
    @property
    def segments(self) -> List[RecordedSegment]:
        """获取所有片段"""
        return self._segments.copy()
        
    @property
    def current_segment(self) -> RecordedSegment | None:
        """获取当前正在录制的片段"""
        return self._current_segment
        
    @property
    def total_size_bytes(self) -> int:
        """获取总大小"""
        return sum(s.size_bytes for s in self._segments)
        
    @property
    def total_fragments(self) -> int:
        """获取总片段数"""
        return sum(s.fragment_end - s.fragment_start for s in self._segments)
        
    def start_new_segment(self, file_path: Path, start_time: datetime | None = None):
        """开始新片段"""
        self._current_segment = RecordedSegment(
            start_time=start_time or datetime.now(),
            end_time=datetime.now(),
            file_path=file_path,
            size_bytes=0,
            fragment_start=0,
            fragment_end=0,
        )
        logger.info(f"开始新片段: {file_path.name}")
        
    def update_current_segment(
        self,
        size_bytes: int = 0,
        fragment_end: int = 0,
        end_time: datetime | None = None,
    ):
        """更新当前片段"""
        if not self._current_segment:
            return
            
        if size_bytes > 0:
            self._current_segment.size_bytes = size_bytes
        if fragment_end > 0:
            self._current_segment.fragment_end = fragment_end
        if end_time:
            self._current_segment.end_time = end_time
        else:
            self._current_segment.end_time = datetime.now()
            
        self.segment_updated.emit(self._current_segment)
        
    def finalize_current_segment(self):
        """完成当前片段"""
        if not self._current_segment:
            return
            
        self._current_segment.end_time = datetime.now()
        self._segments.append(self._current_segment)
        self.segment_added.emit(self._current_segment)
        
        logger.info(
            f"片段完成: {self._current_segment.file_path.name}, "
            f"大小: {self._current_segment.size_bytes / 1024 / 1024:.1f} MB"
        )
        
        self._current_segment = None
        self._save_metadata()
        
    def get_timeline_segments(self) -> List[TimeSegment]:
        """
        获取用于时间轴显示的片段列表
        
        返回元组列表: (start, end, segment_type)
        """
        result = []
        
        for seg in self._segments:
            result.append(TimeSegment(
                start=seg.start_time,
                end=seg.end_time,
                segment_type="recorded",
            ))
            
        # 添加当前录制中的片段
        if self._current_segment:
            result.append(TimeSegment(
                start=self._current_segment.start_time,
                end=datetime.now(),
                segment_type="catching_up",  # 假设还在追赶
            ))
            
        return result
        
    def get_segment_files(self) -> List[Path]:
        """获取所有片段文件路径"""
        return [s.file_path for s in self._segments if s.file_path.exists()]
        
    def _save_metadata(self):
        """保存元数据到磁盘"""
        try:
            metadata = {
                "output_dir": str(self._output_dir),
                "segments": [s.to_dict() for s in self._segments],
                "saved_at": datetime.now().isoformat(),
            }
            
            path = self._output_dir / self.METADATA_FILE
            with open(path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
                
            logger.debug(f"片段元数据已保存: {path}")
            
        except Exception as e:
            logger.error(f"保存片段元数据失败: {e}")
            
    def _load_metadata(self):
        """从磁盘加载元数据"""
        path = self._output_dir / self.METADATA_FILE
        
        if not path.exists():
            return
            
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                
            self._segments = [
                RecordedSegment.from_dict(s) 
                for s in data.get("segments", [])
            ]
            
            logger.info(f"已加载 {len(self._segments)} 个片段元数据")
            
        except Exception as e:
            logger.error(f"加载片段元数据失败: {e}")
            
    def clear(self):
        """清空所有片段"""
        self._segments = []
        self._current_segment = None
        
        # 删除元数据文件
        path = self._output_dir / self.METADATA_FILE
        if path.exists():
            path.unlink()
