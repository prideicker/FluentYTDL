"""
FluentYTDL 任务队列管理模块

提供下载任务的状态管理、持久化和重试机制：
- 任务状态模型 (DownloadTask)
- JSON 持久化
- 自动重试逻辑
- 程序重启后恢复
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from ..utils.logger import logger


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"          # 等待开始
    QUEUED = "queued"            # 已加入队列
    DOWNLOADING = "downloading"  # 下载中
    PAUSED = "paused"            # 已暂停
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败
    CANCELLED = "cancelled"      # 已取消


@dataclass
class DownloadTask:
    """
    下载任务数据模型
    
    用于持久化任务状态，支持程序重启后恢复。
    """
    # 必需字段
    url: str
    output_dir: str
    
    # 自动生成
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # 状态
    status: str = TaskStatus.PENDING.value
    
    # 下载选项 (yt-dlp 参数)
    options: dict[str, Any] = field(default_factory=dict)
    
    # 进度信息
    progress: float = 0.0  # 0-100
    speed: str = ""
    eta: str = ""
    downloaded_bytes: int = 0
    total_bytes: int = 0
    
    # 输出
    output_path: str | None = None
    title: str = ""
    thumbnail_url: str = ""
    duration: int = 0
    
    # 重试
    retries: int = 0
    max_retries: int = 3
    last_error: str | None = None
    
    # 时间戳
    started_at: str | None = None
    completed_at: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化的字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DownloadTask:
        """从字典创建任务"""
        # 过滤掉未知字段
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)
    
    def can_retry(self) -> bool:
        """是否可以重试"""
        return (
            self.status == TaskStatus.FAILED.value
            and self.retries < self.max_retries
        )
    
    def mark_started(self) -> None:
        """标记开始下载"""
        self.status = TaskStatus.DOWNLOADING.value
        self.started_at = datetime.now().isoformat()
    
    def mark_completed(self, output_path: str | None = None) -> None:
        """标记完成"""
        self.status = TaskStatus.COMPLETED.value
        self.completed_at = datetime.now().isoformat()
        self.progress = 100.0
        if output_path:
            self.output_path = output_path
    
    def mark_failed(self, error: str) -> None:
        """标记失败"""
        self.status = TaskStatus.FAILED.value
        self.last_error = error
        self.retries += 1
    
    def mark_cancelled(self) -> None:
        """标记取消"""
        self.status = TaskStatus.CANCELLED.value
    
    def reset_for_retry(self) -> None:
        """重置状态以便重试"""
        if self.can_retry():
            self.status = TaskStatus.PENDING.value
            self.progress = 0.0
            self.speed = ""
            self.eta = ""


class TaskQueue:
    """
    任务队列管理器
    
    负责任务的创建、查询、持久化和生命周期管理。
    """
    
    def __init__(self, persist_path: Path | None = None):
        """
        初始化任务队列
        
        Args:
            persist_path: 持久化文件路径，None 则不持久化
        """
        self._tasks: dict[str, DownloadTask] = {}
        self._persist_path = persist_path
        self._on_change_callbacks: list[Callable[[], None]] = []
        
        # 加载已保存的任务
        if persist_path and persist_path.exists():
            self._load()
    
    def add(self, task: DownloadTask) -> str:
        """
        添加任务
        
        Args:
            task: 下载任务
            
        Returns:
            任务 ID
        """
        self._tasks[task.id] = task
        self._notify_change()
        self._save()
        return task.id
    
    def create(
        self,
        url: str,
        output_dir: str,
        options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> DownloadTask:
        """
        创建并添加新任务
        
        Args:
            url: 视频 URL
            output_dir: 输出目录
            options: yt-dlp 选项
            **kwargs: 其他任务属性
            
        Returns:
            创建的任务
        """
        task = DownloadTask(
            url=url,
            output_dir=output_dir,
            options=options or {},
            **kwargs,
        )
        self.add(task)
        return task
    
    def get(self, task_id: str) -> DownloadTask | None:
        """获取任务"""
        return self._tasks.get(task_id)
    
    def remove(self, task_id: str) -> bool:
        """
        移除任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否成功移除
        """
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._notify_change()
            self._save()
            return True
        return False
    
    def update(self, task: DownloadTask) -> None:
        """更新任务状态"""
        if task.id in self._tasks:
            self._tasks[task.id] = task
            self._notify_change()
            self._save()
    
    def all(self) -> list[DownloadTask]:
        """获取所有任务"""
        return list(self._tasks.values())
    
    def by_status(self, status: TaskStatus) -> list[DownloadTask]:
        """按状态筛选任务"""
        return [t for t in self._tasks.values() if t.status == status.value]
    
    def pending(self) -> list[DownloadTask]:
        """获取待处理任务"""
        return [
            t for t in self._tasks.values()
            if t.status in (TaskStatus.PENDING.value, TaskStatus.QUEUED.value)
        ]
    
    def active(self) -> list[DownloadTask]:
        """获取活跃任务 (下载中)"""
        return self.by_status(TaskStatus.DOWNLOADING)
    
    def completed(self) -> list[DownloadTask]:
        """获取已完成任务"""
        return self.by_status(TaskStatus.COMPLETED)
    
    def failed(self) -> list[DownloadTask]:
        """获取失败任务"""
        return self.by_status(TaskStatus.FAILED)
    
    def retryable(self) -> list[DownloadTask]:
        """获取可重试的失败任务"""
        return [t for t in self.failed() if t.can_retry()]
    
    def clear_completed(self) -> int:
        """清除已完成任务"""
        to_remove = [t.id for t in self.completed()]
        for task_id in to_remove:
            del self._tasks[task_id]
        if to_remove:
            self._notify_change()
            self._save()
        return len(to_remove)
    
    def retry_all_failed(self) -> int:
        """重试所有可重试的失败任务"""
        count = 0
        for task in self.retryable():
            task.reset_for_retry()
            count += 1
        if count:
            self._notify_change()
            self._save()
        return count
    
    def on_change(self, callback: Callable[[], None]) -> None:
        """注册变更回调"""
        self._on_change_callbacks.append(callback)
    
    def _notify_change(self) -> None:
        """通知变更"""
        for callback in self._on_change_callbacks:
            try:
                callback()
            except Exception as e:
                logger.warning(f"任务变更回调失败: {e}")
    
    def _save(self) -> None:
        """保存到文件"""
        if not self._persist_path:
            return
        
        try:
            data = {
                "version": 1,
                "tasks": [t.to_dict() for t in self._tasks.values()],
                "updated_at": datetime.now().isoformat(),
            }
            
            # 确保目录存在
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入临时文件后重命名 (原子操作)
            tmp_path = self._persist_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            tmp_path.replace(self._persist_path)
            
        except Exception as e:
            logger.error(f"保存任务队列失败: {e}")
    
    def _load(self) -> None:
        """从文件加载"""
        if not self._persist_path or not self._persist_path.exists():
            return
        
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            
            for task_data in data.get("tasks", []):
                try:
                    task = DownloadTask.from_dict(task_data)
                    # 恢复时将下载中的任务标记为待处理
                    if task.status == TaskStatus.DOWNLOADING.value:
                        task.status = TaskStatus.PENDING.value
                    self._tasks[task.id] = task
                except Exception as e:
                    logger.warning(f"恢复任务失败: {e}")
            
            logger.info(f"已恢复 {len(self._tasks)} 个任务")
            
        except Exception as e:
            logger.error(f"加载任务队列失败: {e}")
    
    def __len__(self) -> int:
        return len(self._tasks)
    
    def __iter__(self):
        return iter(self._tasks.values())
