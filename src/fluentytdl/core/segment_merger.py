"""
Segment merger for combining recorded segments using FFmpeg.
"""
from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import List

from PySide6.QtCore import QThread, Signal

from ..core.dependency_manager import dependency_manager
from ..utils.logger import logger


class MergeWorker(QThread):
    """
    后台片段合并工作线程
    
    使用 FFmpeg concat demuxer 合并多个片段。
    """
    
    # 信号
    progress = Signal(int, int, str)  # current, total, message
    finished = Signal(bool, str)      # success, output_path
    error = Signal(str)               # error_message
    
    def __init__(
        self,
        segments: List[Path],
        output: Path,
        ffmpeg_path: str | None = None,
        parent=None
    ):
        super().__init__(parent)
        
        self.segments = segments
        self.output = output
        self.ffmpeg_path = ffmpeg_path or self._get_ffmpeg_path()
        
        self._is_cancelled = False
        
    def _get_ffmpeg_path(self) -> str:
        """获取 FFmpeg 路径"""
        ffmpeg = dependency_manager.get_exe_path("ffmpeg")
        if ffmpeg.exists():
            return str(ffmpeg)
        return "ffmpeg"  # 尝试系统 PATH
        
    def cancel(self):
        """取消合并"""
        self._is_cancelled = True
        
    def run(self):
        """执行合并"""
        total = len(self.segments)
        
        if total == 0:
            self.finished.emit(False, "")
            return
            
        # 过滤不存在的文件
        valid_segments = [s for s in self.segments if s.exists()]
        if len(valid_segments) != total:
            logger.warning(f"跳过 {total - len(valid_segments)} 个不存在的片段")
            total = len(valid_segments)
            
        if total == 0:
            self.error.emit("没有有效的片段文件")
            self.finished.emit(False, "")
            return
            
        if total == 1:
            # 只有一个片段，直接复制/移动
            self._handle_single_segment(valid_segments[0])
            return
            
        # 多个片段需要合并
        self._merge_segments(valid_segments)
        
    def _handle_single_segment(self, segment: Path):
        """处理单个片段"""
        self.progress.emit(1, 1, "移动文件...")
        
        try:
            shutil.copy2(segment, self.output)
            self.progress.emit(1, 1, "完成")
            self.finished.emit(True, str(self.output))
        except Exception as e:
            self.error.emit(f"文件复制失败: {e}")
            self.finished.emit(False, "")
            
    def _merge_segments(self, segments: List[Path]):
        """合并多个片段"""
        total = len(segments)
        self.progress.emit(0, total, "准备合并...")
        
        # 创建 concat 文件
        concat_file = self.output.parent / ".concat_list.txt"
        
        try:
            with open(concat_file, "w", encoding="utf-8") as f:
                for seg in segments:
                    # 使用相对路径或绝对路径
                    f.write(f"file '{seg.absolute()}'\n")
                    
            self.progress.emit(0, total, "正在合并...")
            
            # FFmpeg 命令
            cmd = [
                self.ffmpeg_path,
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                "-y",  # 覆盖输出
                str(self.output)
            ]
            
            logger.info(f"执行 FFmpeg 合并: {' '.join(cmd)}")
            
            # 创建进程
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            
            # 监控输出
            current = 0
            for line in iter(process.stdout.readline, ''):
                if self._is_cancelled:
                    process.terminate()
                    self.error.emit("合并已取消")
                    self.finished.emit(False, "")
                    return
                    
                # 尝试解析进度 (FFmpeg 输出)
                if "frame=" in line or "time=" in line:
                    # 简单估算进度
                    current = min(current + 1, total - 1)
                    self.progress.emit(current, total, f"合并中 ({current}/{total})...")
                    
            process.wait()
            
            if process.returncode == 0:
                self.progress.emit(total, total, "合并完成")
                logger.info(f"合并完成: {self.output}")
                self.finished.emit(True, str(self.output))
            else:
                self.error.emit(f"FFmpeg 返回错误代码: {process.returncode}")
                self.finished.emit(False, "")
                
        except Exception as e:
            logger.error(f"合并失败: {e}")
            self.error.emit(str(e))
            self.finished.emit(False, "")
            
        finally:
            # 清理临时文件
            if concat_file.exists():
                try:
                    concat_file.unlink()
                except Exception:
                    pass


class SegmentMerger:
    """
    片段合并器
    
    提供同步和异步合并接口。
    """
    
    def __init__(self, ffmpeg_path: str | None = None):
        self.ffmpeg_path = ffmpeg_path
        self._worker: MergeWorker | None = None
        
    def merge_async(
        self,
        segments: List[Path],
        output: Path,
        on_progress=None,
        on_finished=None,
        on_error=None,
    ) -> MergeWorker:
        """
        异步合并片段
        
        Args:
            segments: 片段文件列表
            output: 输出文件路径
            on_progress: 进度回调 (current, total, message)
            on_finished: 完成回调 (success, output_path)
            on_error: 错误回调 (error_message)
            
        Returns:
            MergeWorker 实例
        """
        self._worker = MergeWorker(segments, output, self.ffmpeg_path)
        
        if on_progress:
            self._worker.progress.connect(on_progress)
        if on_finished:
            self._worker.finished.connect(on_finished)
        if on_error:
            self._worker.error.connect(on_error)
            
        self._worker.start()
        return self._worker
        
    def merge_sync(self, segments: List[Path], output: Path) -> bool:
        """
        同步合并片段
        
        Args:
            segments: 片段文件列表
            output: 输出文件路径
            
        Returns:
            是否成功
        """
        worker = MergeWorker(segments, output, self.ffmpeg_path)
        worker.run()  # 直接在当前线程运行
        
        # 等待完成
        result = [False]
        
        def on_finished(success, path):
            result[0] = success
            
        worker.finished.connect(on_finished)
        
        return result[0]
        
    def cancel(self):
        """取消当前合并"""
        if self._worker:
            self._worker.cancel()
