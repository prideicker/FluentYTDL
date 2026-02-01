"""
FluentYTDL 字幕选择器组件

提供字幕语言多选和格式配置 UI:
- 可用字幕语言列表
- 嵌入/单独文件选择
- 格式转换选项
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    ComboBox,
    SwitchButton,
)

from ...core.subtitle_manager import (
    get_subtitle_languages,
    build_subtitle_opts,
)


class SubtitleSelectorWidget(QFrame):
    """
    字幕选择器组件
    
    显示可用字幕语言列表，允许用户选择要下载的字幕。
    """
    
    selectionChanged = Signal()
    
    def __init__(self, info: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.info = info
        self._selected_languages: set[str] = set()
        self._available_languages: list[dict[str, Any]] = []
        self._checkboxes: dict[str, CheckBox] = {}
        
        self._init_ui()
        self._load_subtitles()
    
    def _init_ui(self):
        self.setObjectName("subtitleSelector")
        self.setStyleSheet("""
            #subtitleSelector {
                background-color: rgba(255, 255, 255, 0.7);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 8px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # 标题行
        header = QHBoxLayout()
        header.setSpacing(8)
        self.titleLabel = BodyLabel("📝 字幕下载", self)
        self.titleLabel.setStyleSheet("font-weight: 600;")
        header.addWidget(self.titleLabel)
        
        self.enableSwitch = SwitchButton(self)
        self.enableSwitch.setChecked(False)
        self.enableSwitch.checkedChanged.connect(self._on_enabled_changed)
        header.addWidget(self.enableSwitch)
        header.addStretch()
        layout.addLayout(header)
        
        # 选项区 (默认隐藏)
        self.optionsWidget = QWidget(self)
        self.optionsLayout = QVBoxLayout(self.optionsWidget)
        self.optionsLayout.setContentsMargins(0, 0, 0, 0)
        self.optionsLayout.setSpacing(12)
        
        # ========== 语言列表滚动区域 ==========
        self.scrollArea = QScrollArea(self.optionsWidget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scrollArea.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
        """)
        self.scrollArea.setMaximumHeight(180)  # 限制最大高度
        
        # 语言复选框容器
        self.languagesWidget = QWidget()
        self.languagesWidget.setStyleSheet("background-color: transparent;")
        self.languagesLayout = QVBoxLayout(self.languagesWidget)
        self.languagesLayout.setContentsMargins(0, 0, 8, 0)  # 右边留出滚动条空间
        self.languagesLayout.setSpacing(8)  # 增加间距防止重叠
        self.languagesLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scrollArea.setWidget(self.languagesWidget)
        self.optionsLayout.addWidget(self.scrollArea)
        
        # 无字幕提示
        self.noSubtitleLabel = CaptionLabel("该视频无可用字幕", self.optionsWidget)
        self.noSubtitleLabel.setStyleSheet("color: #888;")
        self.noSubtitleLabel.hide()
        self.optionsLayout.addWidget(self.noSubtitleLabel)
        
        # ========== 选项栏 ==========
        optRow = QHBoxLayout()
        optRow.setSpacing(16)
        
        # 嵌入选项
        self.embedCheck = CheckBox("嵌入到视频", self.optionsWidget)
        self.embedCheck.setChecked(True)
        optRow.addWidget(self.embedCheck)
        
        # 格式选择
        optRow.addWidget(BodyLabel("格式:", self.optionsWidget))
        self.formatCombo = ComboBox(self.optionsWidget)
        self.formatCombo.addItems(["SRT", "ASS", "VTT"])
        self.formatCombo.setCurrentIndex(0)
        self.formatCombo.setFixedWidth(80)
        optRow.addWidget(self.formatCombo)
        
        optRow.addStretch()
        self.optionsLayout.addLayout(optRow)
        
        layout.addWidget(self.optionsWidget)
        self.optionsWidget.hide()
    
    def _load_subtitles(self):
        """加载可用字幕列表"""
        self._available_languages = get_subtitle_languages(self.info)
        
        if not self._available_languages:
            self.noSubtitleLabel.show()
            self.scrollArea.hide()
            self.enableSwitch.setEnabled(False)
            return
        
        # 清除旧的复选框
        while self.languagesLayout.count():
            item = self.languagesLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self._checkboxes.clear()
        
        # 创建语言复选框
        for lang in self._available_languages:
            code = lang["code"]
            name = lang["name"]
            
            checkbox = CheckBox(name, self.languagesWidget)
            checkbox.setFixedHeight(28)  # 固定高度防止重叠
            checkbox.stateChanged.connect(lambda state, c=code: self._on_lang_toggled(c, state))
            
            self.languagesLayout.addWidget(checkbox)
            self._checkboxes[code] = checkbox
        
        # 添加弹性空间
        self.languagesLayout.addStretch()
        
        # 根据语言数量调整滚动区域高度
        lang_count = len(self._available_languages)
        if lang_count <= 4:
            self.scrollArea.setMaximumHeight(lang_count * 36 + 8)
        else:
            self.scrollArea.setMaximumHeight(180)
        
        # 默认选中第一个中文字幕
        for lang in self._available_languages:
            if lang["code"].startswith("zh"):
                self._checkboxes[lang["code"]].setChecked(True)
                break
    
    def _on_enabled_changed(self, enabled: bool):
        """字幕开关变更"""
        self.optionsWidget.setVisible(enabled)
        self.selectionChanged.emit()
    
    def _on_lang_toggled(self, code: str, state: int):
        """语言选择变化"""
        if state == Qt.CheckState.Checked.value:
            self._selected_languages.add(code)
        else:
            self._selected_languages.discard(code)
        self.selectionChanged.emit()
    
    def is_enabled(self) -> bool:
        """是否启用字幕下载"""
        return self.enableSwitch.isChecked()
    
    def get_selected_languages(self) -> list[str]:
        """获取选中的语言代码"""
        return list(self._selected_languages)
    
    def get_opts(self) -> dict[str, Any]:
        """
        获取 yt-dlp 选项
        
        Returns:
            yt-dlp 选项字典
        """
        if not self.is_enabled():
            return {}
        
        languages = self.get_selected_languages()
        if not languages:
            return {}
        
        embed = self.embedCheck.isChecked()
        convert_to = self.formatCombo.currentText().lower()
        
        return build_subtitle_opts(
            languages=languages,
            embed=embed,
            convert_to=convert_to,
            write_sub=True,
        )
    
    def has_subtitles(self) -> bool:
        """视频是否有可用字幕"""
        return len(self._available_languages) > 0
