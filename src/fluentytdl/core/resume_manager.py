"""
断点续传管理模块

负责:
- 下载任务状态的持久化
- 中断后的任务恢复
- 临时文件的清理和管理
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .config_manager import config_manager
from ..utils.paths import config_path
from ..utils.logger import logger


@dataclass
class ResumeTask:
    """可恢复的下载任务"""
    task_id: str
    url: str
    title: str
    download_dir: str
    output_template: str
    format_string: str
    total_bytes: int = 0
    downloaded_bytes: int = 0
    status: str = "pending"  # pending, downloading, paused, completed, failed
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    options: dict = field(default_factory=dict)
    temp_files: list = field(default_factory=list)
    error_message: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ResumeTask":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ResumeManager:
    """断点续传管理器
    
    管理下载任务的状态持久化，支持：
    - 保存/恢复任务状态
    - 跟踪临时文件
    - 清理已完成任务的缓存
    """
    
    _instance: "ResumeManager | None" = None
    
    def __new__(cls) -> "ResumeManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self) -> None:
        self._tasks: dict[str, ResumeTask] = {}
        self._state_file = config_path().parent / "resume_tasks.json"
        self._load_state()
    
    def _load_state(self) -> None:
        """从文件加载持久化状态"""
        if not self._state_file.exists():
            return
        
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "tasks" in data:
                for task_id, task_data in data["tasks"].items():
                    try:
                        self._tasks[task_id] = ResumeTask.from_dict(task_data)
                    except Exception as e:
                        logger.warning(f"无法恢复任务 {task_id}: {e}")
            logger.info(f"已加载 {len(self._tasks)} 个可恢复任务")
        except Exception as e:
            logger.error(f"加载断点续传状态失败: {e}")
    
    def _save_state(self) -> None:
        """保存状态到文件"""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "tasks": {tid: task.to_dict() for tid, task in self._tasks.items()}
            }
            self._state_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"保存断点续传状态失败: {e}")
    
    def create_task(self, url: str, title: str, options: dict[str, Any]) -> ResumeTask:
        """创建新的可恢复任务"""
        import uuid
        task_id = str(uuid.uuid4())[:8]
        
        # 从 options 提取关键信息
        download_dir = ""
        output_template = ""
        format_string = ""
        
        if "paths" in options:
            download_dir = options["paths"].get("home", "")
        if "outtmpl" in options:
            output_template = options["outtmpl"]
        if "format" in options:
            format_string = options["format"]
        
        task = ResumeTask(
            task_id=task_id,
            url=url,
            title=title,
            download_dir=download_dir,
            output_template=output_template,
            format_string=format_string,
            options=options,
            status="pending"
        )
        
        self._tasks[task_id] = task
        self._save_state()
        logger.info(f"创建断点续传任务: {task_id} - {title}")
        return task
    
    def update_task_progress(self, task_id: str, downloaded: int, total: int) -> None:
        """更新任务下载进度"""
        if task_id not in self._tasks:
            return
        
        task = self._tasks[task_id]
        task.downloaded_bytes = downloaded
        task.total_bytes = total
        task.status = "downloading"
        task.updated_at = time.time()
        
        # 定期保存（每 5 秒或 5MB）
        if time.time() - getattr(self, "_last_save", 0) > 5:
            self._save_state()
            self._last_save = time.time()
    
    def add_temp_file(self, task_id: str, file_path: str) -> None:
        """记录任务的临时文件"""
        if task_id not in self._tasks:
            return
        
        task = self._tasks[task_id]
        if file_path not in task.temp_files:
            task.temp_files.append(file_path)
            task.updated_at = time.time()
    
    def mark_completed(self, task_id: str) -> None:
        """标记任务完成"""
        if task_id not in self._tasks:
            return
        
        task = self._tasks[task_id]
        task.status = "completed"
        task.updated_at = time.time()
        self._save_state()
        logger.info(f"任务完成: {task_id}")
    
    def mark_failed(self, task_id: str, error: str) -> None:
        """标记任务失败"""
        if task_id not in self._tasks:
            return
        
        task = self._tasks[task_id]
        task.status = "failed"
        task.error_message = error
        task.updated_at = time.time()
        self._save_state()
        logger.warning(f"任务失败: {task_id} - {error}")
    
    def mark_paused(self, task_id: str) -> None:
        """标记任务暂停（可恢复）"""
        if task_id not in self._tasks:
            return
        
        task = self._tasks[task_id]
        task.status = "paused"
        task.updated_at = time.time()
        self._save_state()
        logger.info(f"任务暂停: {task_id}")
    
    def get_resumable_tasks(self) -> list[ResumeTask]:
        """获取所有可恢复的任务"""
        return [
            task for task in self._tasks.values()
            if task.status in ("paused", "downloading", "pending")
        ]
    
    def get_task(self, task_id: str) -> ResumeTask | None:
        """获取指定任务"""
        return self._tasks.get(task_id)
    
    def remove_task(self, task_id: str, clean_files: bool = False) -> None:
        """移除任务记录"""
        if task_id not in self._tasks:
            return
        
        task = self._tasks[task_id]
        
        if clean_files:
            # 清理临时文件
            for file_path in task.temp_files:
                try:
                    p = Path(file_path)
                    if p.exists():
                        p.unlink()
                        logger.info(f"已删除临时文件: {file_path}")
                except Exception as e:
                    logger.warning(f"删除临时文件失败: {file_path} - {e}")
            
            # 清理 .part 文件
            if task.download_dir:
                try:
                    for f in Path(task.download_dir).glob("*.part"):
                        if task.title in f.name or task.task_id in f.name:
                            f.unlink()
                            logger.info(f"已删除 .part 文件: {f}")
                except Exception:
                    pass
        
        del self._tasks[task_id]
        self._save_state()
        logger.info(f"已移除任务 {task_id}")
    
    def cleanup_completed_tasks(self, max_age_days: int = 7) -> int:
        """清理已完成的旧任务"""
        cutoff = time.time() - (max_age_days * 24 * 3600)
        removed = 0
        
        for task_id in list(self._tasks.keys()):
            task = self._tasks[task_id]
            if task.status == "completed" and task.updated_at < cutoff:
                del self._tasks[task_id]
                removed += 1
        
        if removed > 0:
            self._save_state()
            logger.info(f"已清理 {removed} 个已完成任务")
        
        return removed
    
    def build_resume_options(self, task: ResumeTask) -> dict[str, Any]:
        """为恢复任务构建 yt-dlp 选项
        
        确保启用断点续传相关参数
        """
        opts = dict(task.options)
        
        # 确保启用断点续传
        if config_manager.get("enable_resume", True):
            # yt-dlp 默认支持断点续传，但我们明确设置一些参数
            opts["continuedl"] = True  # 继续下载部分下载的文件
            opts["nooverwrites"] = False  # 允许继续写入
        
        return opts



# 全局单例
resume_manager = ResumeManager()
