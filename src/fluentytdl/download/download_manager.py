from __future__ import annotations

from collections import deque
from typing import Any

from PySide6.QtCore import QObject, Signal

from ..core.config_manager import config_manager
from .workers import DownloadWorker


class DownloadManager(QObject):
    # 通知 UI：任务列表/状态变化（新增/结束/删除/暂停等）
    task_updated = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.active_workers: list[DownloadWorker] = []
        self._pending_workers: deque[DownloadWorker] = deque()

    def _max_concurrent(self) -> int:
        try:
            n = int(config_manager.get("max_concurrent_downloads", 2) or 2)
        except Exception:
            n = 2
        # Use 32-bit int max to avoid overflow in UI / Qt validators.
        return max(1, min(2_147_483_647, n))

    def _running_count(self) -> int:
        return sum(1 for w in self.active_workers if w.isRunning())

    def running_count(self) -> int:
        return self._running_count()

    def pending_count(self) -> int:
        return len(self._pending_workers)

    def has_active_tasks(self) -> bool:
        return self.running_count() > 0 or self.pending_count() > 0

    def _remove_from_pending(self, worker: DownloadWorker) -> None:
        if not self._pending_workers:
            return
        try:
            self._pending_workers = deque([w for w in self._pending_workers if w is not worker])
        except Exception:
            pass

    def is_queued(self, worker: DownloadWorker) -> bool:
        return any(w is worker for w in self._pending_workers)

    def pump(self) -> None:
        """Start queued downloads until reaching the concurrency limit."""

        limit = self._max_concurrent()
        while self._pending_workers and self._running_count() < limit:
            w = self._pending_workers.popleft()
            try:
                if w.isRunning() or w.isFinished():
                    continue
                w.start()
            except Exception:
                continue
        self.task_updated.emit()

    def create_worker(self, url: str, opts: dict[str, Any]) -> DownloadWorker:
        worker = DownloadWorker(url, opts)
        self.active_workers.append(worker)

        # When a worker ends, free a slot and pump queued tasks.
        try:
            worker.finished.connect(lambda: self._on_worker_finished(worker))
        except Exception:
            pass
        worker.completed.connect(lambda: self.task_updated.emit())
        worker.cancelled.connect(lambda: self.task_updated.emit())
        worker.error.connect(lambda *_: self.task_updated.emit())
        return worker

    def _on_worker_finished(self, worker: DownloadWorker) -> None:
        # Worker ended => free slot
        self._remove_from_pending(worker)
        self.pump()

    def start_worker(self, worker: DownloadWorker) -> bool:
        """Start worker if a slot is available; otherwise queue it."""

        self._remove_from_pending(worker)

        if worker.isRunning():
            return True
        if worker.isFinished():
            return False

        if self._running_count() < self._max_concurrent():
            try:
                worker.start()
                self.task_updated.emit()
                return True
            except Exception:
                return False

        self._pending_workers.append(worker)
        self.task_updated.emit()
        return False

    def stop_all(self) -> None:
        # Clear queued tasks first (so they won't start after pausing).
        self._pending_workers.clear()
        for worker in list(self.active_workers):
            if worker.isRunning():
                worker.stop()

    def shutdown(self, grace_ms: int = 2000) -> bool:
        """Stop all workers and wait for them to exit.

        Returns True if all workers have stopped within the grace period.
        """

        self.stop_all()

        all_stopped = True
        for worker in list(self.active_workers):
            if not worker.isRunning():
                continue
            try:
                # Try graceful wait first.
                if not worker.wait(grace_ms):
                    all_stopped = False
                    # Last resort: terminate the thread.
                    try:
                        worker.terminate()
                    except Exception:
                        pass
                    try:
                        worker.wait(500)
                    except Exception:
                        pass
            except Exception:
                all_stopped = False

        return all_stopped

    def start_all(self) -> None:
        # QThread 结束后不能重用；“继续/重试”应由 UI 重建 worker。
        self.pump()

    def remove_worker(self, worker: DownloadWorker) -> None:
        self._remove_from_pending(worker)
        if worker in self.active_workers:
            if worker.isRunning():
                worker.stop()
                worker.wait()
            self.active_workers.remove(worker)
            self.task_updated.emit()


download_manager = DownloadManager()
