"""
Task persistence for saving and restoring recording tasks.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List

from ..models.live_models import TaskState
from ..utils.logger import logger


class TaskPersistence:
    """
    任务持久化管理
    
    将录制任务状态保存到磁盘，支持应用重启后恢复。
    """
    
    STATE_FILE = ".task_state.json"
    
    @staticmethod
    def save(output_dir: Path, state: TaskState) -> bool:
        """
        保存任务状态
        
        Args:
            output_dir: 输出目录
            state: 任务状态
            
        Returns:
            是否成功
        """
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 更新时间戳
            state.updated_at = datetime.now().isoformat()
            
            path = output_dir / TaskPersistence.STATE_FILE
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
                
            logger.debug(f"任务状态已保存: {path}")
            return True
            
        except Exception as e:
            logger.error(f"保存任务状态失败: {e}")
            return False
            
    @staticmethod
    def load(output_dir: Path) -> TaskState | None:
        """
        加载任务状态
        
        Args:
            output_dir: 输出目录
            
        Returns:
            任务状态，如果不存在或加载失败则返回 None
        """
        path = output_dir / TaskPersistence.STATE_FILE
        
        if not path.exists():
            return None
            
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                
            state = TaskState.from_dict(data)
            logger.debug(f"任务状态已加载: {state.video_id}")
            return state
            
        except Exception as e:
            logger.error(f"加载任务状态失败: {e}")
            return None
            
    @staticmethod
    def scan_resumable_tasks(base_dir: Path) -> List[TaskState]:
        """
        扫描可恢复的任务
        
        Args:
            base_dir: 基础目录（通常是下载目录）
            
        Returns:
            可恢复任务列表
        """
        tasks = []
        
        if not base_dir.exists():
            return tasks
            
        # 可恢复的状态
        resumable_states = {
            "paused",
            "catching_up",
            "live_recording",
            "synchronizing",
            "waiting",
        }
        
        try:
            for subdir in base_dir.iterdir():
                if not subdir.is_dir():
                    continue
                    
                state = TaskPersistence.load(subdir)
                if state and state.state in resumable_states:
                    tasks.append(state)
                    
        except Exception as e:
            logger.error(f"扫描可恢复任务失败: {e}")
            
        if tasks:
            logger.info(f"发现 {len(tasks)} 个可恢复任务")
            
        return tasks
        
    @staticmethod
    def delete(output_dir: Path) -> bool:
        """
        删除任务状态文件
        
        Args:
            output_dir: 输出目录
            
        Returns:
            是否成功
        """
        path = output_dir / TaskPersistence.STATE_FILE
        
        if not path.exists():
            return True
            
        try:
            path.unlink()
            logger.debug(f"任务状态已删除: {path}")
            return True
        except Exception as e:
            logger.error(f"删除任务状态失败: {e}")
            return False
            
    @staticmethod
    def update_state(output_dir: Path, new_state: str) -> bool:
        """
        仅更新状态字段
        
        Args:
            output_dir: 输出目录
            new_state: 新状态
            
        Returns:
            是否成功
        """
        state = TaskPersistence.load(output_dir)
        if not state:
            return False
            
        state.state = new_state
        return TaskPersistence.save(output_dir, state)


# 便捷函数
def save_task_state(output_dir: Path, state: TaskState) -> bool:
    """保存任务状态"""
    return TaskPersistence.save(output_dir, state)


def load_task_state(output_dir: Path) -> TaskState | None:
    """加载任务状态"""
    return TaskPersistence.load(output_dir)


def scan_resumable_tasks(base_dir: Path) -> List[TaskState]:
    """扫描可恢复任务"""
    return TaskPersistence.scan_resumable_tasks(base_dir)
