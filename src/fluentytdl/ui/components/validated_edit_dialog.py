from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtWidgets import QWidget

from qfluentwidgets import (
    CaptionLabel,
    LineEdit,
    MessageBoxBase,
    SubtitleLabel,
)

try:
    from qfluentwidgets import TextEdit as FluentTextEdit  # type: ignore
except Exception:  # pragma: no cover
    from PySide6.QtWidgets import QTextEdit as FluentTextEdit  # type: ignore


Validator = Callable[[str], tuple[bool, str]]
Fixer = Callable[[str], str]


class ValidatedEditDialog(MessageBoxBase):
    """带验证和自动修正功能的编辑弹窗。

    - 支持单行/多行输入（根据 prefer_multiline 或初始值长度自动选择）
    - 支持 fixer: 自动清洗输入
    - 支持 validator: 校验失败时不关闭并显示错误
    """

    def __init__(
        self,
        title: str,
        content: str,
        initial_value: str = "",
        validator: Optional[Validator] = None,
        fixer: Optional[Fixer] = None,
        parent: QWidget | None = None,
        prefer_multiline: bool = False,
        min_width: int = 420,
        multiline_height: int = 110,
    ) -> None:
        super().__init__(parent)

        self._validator = validator
        self._fixer = fixer
        self.final_value: str = ""

        self.viewLayout.setSpacing(10)

        self.titleLabel = SubtitleLabel(title, self)
        self.viewLayout.addWidget(self.titleLabel)

        self.infoLabel = CaptionLabel(content, self)
        self.infoLabel.setWordWrap(True)
        self.viewLayout.addWidget(self.infoLabel)

        use_multiline = bool(prefer_multiline) or len(initial_value or "") > 60
        if use_multiline:
            self.inputWidget = FluentTextEdit(self)
            self.inputWidget.setPlainText(initial_value or "")
            self.inputWidget.setFixedHeight(int(multiline_height))
        else:
            self.inputWidget = LineEdit(self)
            self.inputWidget.setText(initial_value or "")
            try:
                self.inputWidget.setClearButtonEnabled(True)
            except Exception:
                pass

        self.viewLayout.addWidget(self.inputWidget)

        self.errorLabel = CaptionLabel("", self)
        self.errorLabel.setWordWrap(True)
        self.errorLabel.hide()
        self.viewLayout.addWidget(self.errorLabel)

        self.yesButton.setText("确认")
        self.cancelButton.setText("取消")

        try:
            self.widget.setMinimumWidth(int(min_width))
        except Exception:
            pass

    def _get_text(self) -> str:
        if isinstance(self.inputWidget, FluentTextEdit):
            return (self.inputWidget.toPlainText() or "").strip()
        return (self.inputWidget.text() or "").strip()

    def _set_text(self, text: str) -> None:
        if isinstance(self.inputWidget, FluentTextEdit):
            self.inputWidget.setPlainText(text)
        else:
            self.inputWidget.setText(text)

    def _show_error(self, message: str) -> None:
        self.errorLabel.setText(message)
        self.errorLabel.show()

    def accept(self) -> None:  # type: ignore[override]
        text = self._get_text()

        if self._fixer is not None:
            try:
                fixed = self._fixer(text)
            except Exception:
                fixed = text
            if fixed != text:
                text = fixed
                self._set_text(text)

        if self._validator is not None:
            try:
                ok, msg = self._validator(text)
            except Exception:
                ok, msg = False, "输入校验失败"
            if not ok:
                self._show_error(msg or "输入不合法")
                return

        self.final_value = text
        super().accept()
