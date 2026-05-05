from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    FluentIcon,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SubtitleLabel,
)


class ChannelParsePage(QWidget):
    """频道解析页面

    允许用户粘贴 YouTube 频道链接，自动解析频道内所有视频。
    """

    parse_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("channelParsePage")

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(30, 30, 30, 30)
        self.vBoxLayout.setSpacing(0)

        # Center container
        self.centerWidget = QWidget(self)
        self.centerLayout = QVBoxLayout(self.centerWidget)
        self.centerLayout.setContentsMargins(0, 0, 0, 0)
        self.centerLayout.setSpacing(20)
        self.centerLayout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.vBoxLayout.addStretch(1)
        self.vBoxLayout.addWidget(self.centerWidget, 0, Qt.AlignmentFlag.AlignHCenter)
        self.vBoxLayout.addStretch(1)

        # 1. 顶部标题
        self.titleLabel = SubtitleLabel("📺  频道下载", self)
        self.centerLayout.addWidget(self.titleLabel)

        # 2. 说明卡片
        self.infoCard = CardWidget(self)
        self.infoCard.setMaximumWidth(760)
        infoLayout = QVBoxLayout(self.infoCard)
        infoLayout.setContentsMargins(20, 16, 20, 16)
        infoLayout.setSpacing(8)

        infoTitle = BodyLabel("频道批量下载", self.infoCard)
        infoTitle.setStyleSheet("font-weight: 600;")
        infoLayout.addWidget(infoTitle)

        infoText = CaptionLabel(
            "粘贴 YouTube 频道链接，自动解析频道内所有视频。\n"
            "支持切换「视频」和「Shorts」标签页，以及按时间正序/倒序排列。\n"
            "解析采用渐进式加载，先展示标题和封面，滚动到可视区域时再获取详细格式。",
            self.infoCard,
        )
        infoText.setWordWrap(True)
        infoLayout.addWidget(infoText)

        self.centerLayout.addWidget(self.infoCard)

        # 3. 核心操作区
        self.inputCard = CardWidget(self)
        self.inputCard.setMaximumWidth(760)
        self.cardLayout = QVBoxLayout(self.inputCard)
        self.cardLayout.setContentsMargins(20, 20, 20, 20)
        self.cardLayout.setSpacing(15)

        self.instructionLabel = BodyLabel("粘贴 YouTube 频道链接", self)
        self.cardLayout.addWidget(self.instructionLabel)

        # 输入框行
        self.inputLayout = QHBoxLayout()

        self.urlInput = LineEdit(self)
        self.urlInput.setPlaceholderText("https://www.youtube.com/@ChannelName")
        self.urlInput.setClearButtonEnabled(True)
        self.urlInput.setMinimumWidth(560)
        self.urlInput.returnPressed.connect(self.on_parse_clicked)

        self.inputLayout.addWidget(self.urlInput)

        self.pasteBtn = PushButton("粘贴", self)
        self.pasteBtn.setMinimumWidth(72)
        self.pasteBtn.clicked.connect(self.on_paste_clicked)
        self.inputLayout.addWidget(self.pasteBtn)
        self.cardLayout.addLayout(self.inputLayout)

        # 按钮行 (右对齐)
        self.btnLayout = QHBoxLayout()
        self.btnLayout.addStretch(1)

        self.parseBtn = PrimaryPushButton(FluentIcon.SEARCH, "开始解析频道", self)
        self.parseBtn.setMinimumWidth(140)
        self.parseBtn.clicked.connect(self.on_parse_clicked)

        self.btnLayout.addWidget(self.parseBtn)
        self.cardLayout.addLayout(self.btnLayout)

        self.centerLayout.addWidget(self.inputCard)

        # 4. 底部提示
        self.tipsLabel = CaptionLabel(
            "支持的频道 URL 格式：\n"
            "- https://www.youtube.com/@ChannelName\n"
            "- https://www.youtube.com/channel/UCxxxxxxxxx\n"
            "- https://www.youtube.com/c/ChannelName\n"
            "- 单个视频请使用左侧「新建任务」页面",
            self,
        )
        self.tipsLabel.setWordWrap(True)
        self.tipsLabel.setMaximumWidth(760)
        self.centerLayout.addWidget(self.tipsLabel)

        # Connect to theme changes
        from qfluentwidgets import qconfig

        qconfig.themeChanged.connect(self._update_style)
        self._update_style()

    def on_parse_clicked(self) -> None:
        url = self.urlInput.text().strip()
        if url:
            self.parse_requested.emit(url)

    def _update_style(self):
        from qfluentwidgets import isDarkTheme

        page_bg = "transparent" if isDarkTheme() else "#F5F5F5"
        self.setStyleSheet(f"#channelParsePage {{ background-color: {page_bg}; }}")

        card_bg = "rgba(255, 255, 255, 0.05)" if isDarkTheme() else "white"
        card_bd = "rgba(255, 255, 255, 0.08)" if isDarkTheme() else "rgba(0, 0, 0, 0.05)"
        card_style = f"CardWidget {{ background-color: {card_bg}; border-radius: 12px; border: 1px solid {card_bd}; }}"
        self.infoCard.setStyleSheet(card_style)
        self.inputCard.setStyleSheet(card_style)

    def on_paste_clicked(self) -> None:
        text = (QApplication.clipboard().text() or "").strip()
        if text:
            self.urlInput.setText(text)
            self.urlInput.setFocus()
