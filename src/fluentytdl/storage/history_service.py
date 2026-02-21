"""
下载历史记录服务

轻量级方案 A：基于 JSON 持久化 + 文件存在性验证。
- 下载完成时写入记录
- 启动时后台验证文件
- 按 video_id 分组同名文件
- 不做文件指纹、不做智能搜索
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from ..utils.logger import logger
from ..utils.paths import config_path

# 历史记录新增回调（UI 用来实时更新）
_on_add_callbacks: list = []


def on_history_added(callback) -> None:
    """注册历史记录新增回调"""
    _on_add_callbacks.append(callback)


def _notify_added(record) -> None:
    for cb in _on_add_callbacks:
        try:
            cb(record)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class HistoryRecord:
    """单条下载历史"""

    video_id: str  # YouTube video ID
    url: str  # 原始链接
    title: str  # 视频标题
    output_path: str  # 最终输出路径
    file_size: int = 0  # 文件大小 (bytes)
    thumbnail_url: str = ""  # 缩略图 URL
    duration: int = 0  # 视频时长 (秒)
    format_note: str = ""  # 格式备注 (如 "1080p MP4")
    download_time: float = field(default_factory=time.time)  # 下载完成时间戳
    file_exists: bool = True  # 文件是否存在（运行时计算）

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("file_exists", None)  # 不持久化运行时字段
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryRecord:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class HistoryGroup:
    """同一视频的多次下载分组"""

    video_id: str
    title: str
    records: list[HistoryRecord] = field(default_factory=list)

    @property
    def latest(self) -> HistoryRecord | None:
        return self.records[0] if self.records else None

    @property
    def any_exists(self) -> bool:
        return any(r.file_exists for r in self.records)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

_YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})")


def extract_video_id(url: str) -> str:
    """从 YouTube URL 提取 11 位 video_id"""
    m = _YT_ID_RE.search(url or "")
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# HistoryService
# ---------------------------------------------------------------------------


class HistoryService:
    """下载历史管理（全局单例）"""

    _instance: HistoryService | None = None

    def __new__(cls) -> HistoryService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    # ------ 初始化 / 持久化 ------

    def _init(self) -> None:
        self._records: list[HistoryRecord] = []
        self._history_file = config_path().parent / "download_history.json"
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if not self._history_file.exists():
            return
        try:
            data = json.loads(self._history_file.read_text(encoding="utf-8"))
            for item in data.get("records", []):
                try:
                    self._records.append(HistoryRecord.from_dict(item))
                except Exception as e:
                    logger.warning(f"[History] 恢复记录失败: {e}")
            # 按下载时间降序（最新在前）
            self._records.sort(key=lambda r: r.download_time, reverse=True)
            logger.info(f"[History] 已加载 {len(self._records)} 条历史记录")
        except Exception as e:
            logger.error(f"[History] 加载历史记录失败: {e}")

    def save(self) -> None:
        """持久化到文件（原子写入）"""
        if not self._dirty and self._history_file.exists():
            return
        try:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "updated_at": time.time(),
                "records": [r.to_dict() for r in self._records],
            }
            tmp = self._history_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._history_file)
            self._dirty = False
        except Exception as e:
            logger.error(f"[History] 保存失败: {e}")

    # ------ 写入 ------

    def add(
        self,
        url: str,
        title: str,
        output_path: str,
        *,
        video_id: str = "",
        file_size: int = 0,
        thumbnail_url: str = "",
        duration: int = 0,
        format_note: str = "",
    ) -> HistoryRecord:
        """下载完成后调用，添加一条记录"""
        vid = video_id or extract_video_id(url)

        # 自动获取文件大小
        if not file_size and output_path:
            try:
                file_size = os.path.getsize(output_path)
            except OSError:
                pass

        rec = HistoryRecord(
            video_id=vid,
            url=url,
            title=title,
            output_path=os.path.abspath(output_path) if output_path else "",
            file_size=file_size,
            thumbnail_url=thumbnail_url,
            duration=duration,
            format_note=format_note,
        )
        self._records.insert(0, rec)  # 最新在前
        self._dirty = True
        self.save()
        logger.info(f"[History] 已记录: {title} -> {output_path}")
        _notify_added(rec)
        return rec

    # ------ 查询 ------

    def all_records(self) -> list[HistoryRecord]:
        """所有记录（最新在前）"""
        return list(self._records)

    def validated_records(self) -> list[HistoryRecord]:
        """验证文件存在性后返回所有记录"""
        for r in self._records:
            r.file_exists = bool(r.output_path and os.path.exists(r.output_path))
        return list(self._records)

    def existing_records(self) -> list[HistoryRecord]:
        """仅返回文件仍存在的记录"""
        return [r for r in self.validated_records() if r.file_exists]

    def grouped(self, only_existing: bool = False) -> list[HistoryGroup]:
        """按 video_id 分组返回"""
        records = self.existing_records() if only_existing else self.validated_records()
        groups: dict[str, HistoryGroup] = {}

        for r in records:
            key = r.video_id or r.output_path  # 没有 video_id 时按路径分组
            if key not in groups:
                groups[key] = HistoryGroup(video_id=r.video_id, title=r.title)
            groups[key].records.append(r)

        return list(groups.values())

    def find_by_video_id(self, video_id: str) -> list[HistoryRecord]:
        """查找同一视频的所有下载记录"""
        return [r for r in self._records if r.video_id == video_id]

    def is_downloaded(self, url: str) -> bool:
        """检查 URL 对应的视频是否已下载且文件存在"""
        vid = extract_video_id(url)
        if not vid:
            return False
        for r in self._records:
            if r.video_id == vid and r.output_path and os.path.exists(r.output_path):
                return True
        return False

    def search(self, keyword: str) -> list[HistoryRecord]:
        """按关键词搜索标题"""
        kw = keyword.lower()
        return [r for r in self._records if kw in r.title.lower()]

    # ------ 删除 ------

    def remove(self, record: HistoryRecord) -> None:
        """移除一条记录"""
        if record in self._records:
            self._records.remove(record)
            self._dirty = True
            self.save()

    def remove_missing(self) -> int:
        """清理所有文件不存在的记录"""
        before = len(self._records)
        self._records = [
            r for r in self._records if r.output_path and os.path.exists(r.output_path)
        ]
        removed = before - len(self._records)
        if removed:
            self._dirty = True
            self.save()
            logger.info(f"[History] 已清理 {removed} 条无效记录")
        return removed

    def clear(self) -> int:
        """清空所有历史"""
        count = len(self._records)
        self._records.clear()
        self._dirty = True
        self.save()
        return count

    # ------ 统计 ------

    @property
    def count(self) -> int:
        return len(self._records)

    def total_size(self) -> int:
        """所有文件的总大小"""
        return sum(r.file_size for r in self._records if r.file_exists)


# 全局单例
history_service = HistoryService()
