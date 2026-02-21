from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


def _rgba(c: QColor) -> str:
    return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"


def _with_alpha(c: QColor, alpha: int) -> QColor:
    out = QColor(c)
    out.setAlpha(max(0, min(255, int(alpha))))
    return out


def _hsl_adjust(
    c: QColor, *, hue_shift: float = 0.0, sat_mul: float = 1.0, light_mul: float = 1.0
) -> QColor:
    h, s, light, a = cast(tuple[float, float, float, float], c.getHslF())
    if h < 0:
        h = 0.0
    h = (h + hue_shift) % 1.0
    s = max(0.0, min(1.0, s * sat_mul))
    light = max(0.0, min(1.0, light * light_mul))
    out = QColor()
    out.setHslF(h, s, light, a)
    return out


def _macaron_bg(color_style: str) -> QColor:
    """Macaron background colors (light theme)."""

    # User-specified macaron hex backgrounds.
    bg_hex = {
        "gold": "#FFF4CE",
        "blue": "#CFE2FF",
        "purple": "#E0CFFC",
        "green": "#D1E7DD",
        "orange": "#FFE5D0",
        "red": "#F8D7DA",
        "gray": "#F8F9FA",
    }.get(color_style, "#F8F9FA")
    return QColor(bg_hex)


class QualityBadge(QLabel):
    """Soft Fluent-style badge.

    Uses macaron background hex colors for visual consistency.
    """

    def __init__(self, text: str, color_style: str = "gray", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(18)
        self.setMinimumWidth(30)

        font = self.font()
        base_ps = font.pointSize()
        if not isinstance(base_ps, int) or base_ps <= 0:
            base_ps = 9
        font.setPointSize(max(9, base_ps - 1))
        font.setWeight(QFont.Weight.DemiBold)
        self.setFont(font)

        bg = _macaron_bg(color_style)
        # Derive border/text from the background itself to keep the palette cohesive.
        border = _with_alpha(_hsl_adjust(bg, sat_mul=1.05, light_mul=0.82), 200)
        fg = _hsl_adjust(bg, sat_mul=1.10, light_mul=0.28)
        fg.setAlpha(255)

        self.setStyleSheet(
            "QLabel {"
            f"background-color: {bg.name()};"
            f"color: {_rgba(fg)};"
            f"border: 1px solid {_rgba(border)};"
            "border-radius: 4px;"
            "padding: 0px 6px;"
            "}"
        )


class QualityCellWidget(QWidget):
    """Zero-margin, vertically centered badge+text container."""

    def __init__(
        self,
        badges_data: Iterable[tuple[str, str]],
        text: str,
        parent: QWidget | None = None,
        *,
        bold_text: bool = False,
        alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    ):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(alignment)

        for badge_text, color in badges_data:
            badge = QualityBadge(badge_text, color, self)
            layout.addWidget(badge)

        if text:
            label = QLabel(text, self)
            label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            font = label.font()
            base_ps = font.pointSize()
            if not isinstance(base_ps, int) or base_ps <= 0:
                base_ps = 10
            font.setPointSize(max(10, base_ps))
            if bold_text:
                font.setWeight(QFont.Weight.DemiBold)
            label.setFont(font)
            layout.addWidget(label)

        if alignment & Qt.AlignmentFlag.AlignLeft:
            layout.addStretch(1)
