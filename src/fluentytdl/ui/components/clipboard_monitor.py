from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from ...utils.validators import UrlValidator


class ClipboardMonitor(QObject):
    """剪贴板监听组件

    当检测到合法的 YouTube 链接时发出信号。
    """

    youtube_url_detected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.clipboard = QApplication.clipboard()
        self.last_text = ""
        # 监听剪贴板变化信号
        self.clipboard.dataChanged.connect(self._on_clipboard_change)

    def _on_clipboard_change(self) -> None:
        # 获取当前剪贴板文本
        text = (self.clipboard.text() or "").strip()

        # 1. 简单的去重（防止同一内容触发多次）
        if text == self.last_text:
            return
        self.last_text = text

        # 2. 验证是否为 YouTube 链接
        if UrlValidator.is_youtube_url(text):
            self.youtube_url_detected.emit(text)
