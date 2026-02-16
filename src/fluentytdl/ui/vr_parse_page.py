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


class VRParsePage(QWidget):
    """VR 专用下载页面

    允许用户粘贴 VR 视频链接，自动使用 android_vr 客户端解析。
    """

    parse_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("vrParsePage")

        self.setStyleSheet("""
            #vrParsePage {
                background-color: #F5F5F5;
            }
        """)

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
        self.titleLabel = SubtitleLabel("🥽  VR 视频下载", self)
        self.centerLayout.addWidget(self.titleLabel)

        # 2. VR 说明卡片
        self.infoCard = CardWidget(self)
        self.infoCard.setMaximumWidth(760)
        self.infoCard.setStyleSheet("""
            CardWidget {
                background-color: white;
                border-radius: 12px;
                border: 1px solid rgba(0, 0, 0, 0.05);
            }
        """)
        infoLayout = QVBoxLayout(self.infoCard)
        infoLayout.setContentsMargins(20, 16, 20, 16)
        infoLayout.setSpacing(8)

        infoTitle = BodyLabel("为什么需要 VR 模式？", self.infoCard)
        infoTitle.setStyleSheet("font-weight: 600;")
        infoLayout.addWidget(infoTitle)

        infoText = CaptionLabel(
            "VR180/360 \u89c6\u9891\u5728\u666e\u901a\u6a21\u5f0f\u4e0b\u53ea\u80fd\u83b7\u53d6\u5c55\u5e73\u7684\u5355\u89c6\u89d2\u753b\u9762\uff0c\u4e14\u6700\u9ad8\u4ec5 1440p\u3002\n"
            "VR \u6a21\u5f0f\u4f7f\u7528 android_vr \u5ba2\u6237\u7aef\uff0c\u53ef\u83b7\u53d6\u5b8c\u6574 VR \u6295\u5f71\u548c\u6700\u9ad8 8K \u5206\u8fa8\u7387\u3002\n"
            "\u89e3\u6790\u540e\u4f1a\u81ea\u52a8\u8bc6\u522b\u6295\u5f71\u7c7b\u578b\uff08Equi / Mesh / EAC\uff09\u548c\u7acb\u4f53\u6a21\u5f0f\uff083D / 2D\uff09\u3002\n"
            "\u6ce8\u610f\uff1aVR \u6a21\u5f0f\u4e0d\u652f\u6301 Cookies\uff0c\u90e8\u5206\u5e74\u9f84\u9650\u5236\u89c6\u9891\u53ef\u80fd\u65e0\u6cd5\u4e0b\u8f7d\u3002",
            self.infoCard,
        )
        infoText.setWordWrap(True)
        infoLayout.addWidget(infoText)

        self.centerLayout.addWidget(self.infoCard)

        # 3. 核心操作区
        self.inputCard = CardWidget(self)
        self.inputCard.setMaximumWidth(760)
        self.inputCard.setStyleSheet("""
            CardWidget {
                background-color: white;
                border-radius: 12px;
                border: 1px solid rgba(0, 0, 0, 0.05);
            }
        """)
        self.cardLayout = QVBoxLayout(self.inputCard)
        self.cardLayout.setContentsMargins(20, 20, 20, 20)
        self.cardLayout.setSpacing(15)

        self.instructionLabel = BodyLabel(
            "粘贴 YouTube VR 视频链接", self
        )
        self.cardLayout.addWidget(self.instructionLabel)

        # 输入框行
        self.inputLayout = QHBoxLayout()

        self.urlInput = LineEdit(self)
        self.urlInput.setPlaceholderText("https://www.youtube.com/watch?v=...")
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

        self.parseBtn = PrimaryPushButton(FluentIcon.SEARCH, "开始 VR 解析", self)
        self.parseBtn.setMinimumWidth(140)
        self.parseBtn.clicked.connect(self.on_parse_clicked)

        self.btnLayout.addWidget(self.parseBtn)
        self.cardLayout.addLayout(self.btnLayout)

        self.centerLayout.addWidget(self.inputCard)

        # 4. 底部提示
        self.tipsLabel = CaptionLabel(
            "适用场景：\n"
            "- VR180 / VR360 视频，需要完整 SBS/OU 数据\n"
            "- 需要超过 1440p 分辨率的 VR 视频（4K/5K/8K）\n"
            "- 普通视频请使用左侧「新建任务」页面",
            self,
        )
        self.tipsLabel.setWordWrap(True)
        self.tipsLabel.setMaximumWidth(760)
        self.centerLayout.addWidget(self.tipsLabel)

    def on_parse_clicked(self) -> None:
        url = self.urlInput.text().strip()
        if url:
            self.parse_requested.emit(url)

    def on_paste_clicked(self) -> None:
        text = (QApplication.clipboard().text() or "").strip()
        if text:
            self.urlInput.setText(text)
            self.urlInput.setFocus()
