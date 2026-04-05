from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    MessageBoxBase,
    SubtitleLabel,
    SwitchButton,
)

from ...core.config_manager import config_manager
from ...models.subtitle_config import PlaylistSubtitleOverride

PREDEFINED_LANGS = [
    ("zh-Hans", "中文 (简体)"),
    ("zh-Hant", "中文 (繁体)"),
    ("en", "English"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("ru", "Русский"),
    ("es", "Español"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("th", "ไทย"),
    ("vi", "Tiếng Việt"),
    ("ar", "العربية")
]

class PlaylistSubtitleConfigDialog(MessageBoxBase):
    """
    播放列表级别的整体字幕配置弹窗。
    让用户可以全局配置播放列表下载任务的目标语言及参数。
    """

    def __init__(self, current_override: PlaylistSubtitleOverride | None = None, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("播放列表字幕设置", self)
        self.viewLayout.addWidget(self.titleLabel)

        config = config_manager.get_subtitle_config()
        
        # --- 目标语言选取区 ---
        self.viewLayout.addWidget(BodyLabel("选择字幕语言 (可多选):", self))
        
        self.lang_list = QListWidget(self)
        self.lang_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.lang_list.setFixedHeight(180)
        self.lang_list.setStyleSheet(
            "QListWidget { background: transparent; border: 1px solid rgba(128,128,128,0.2); border-radius: 4px; outline: 0px; } "
            "QListWidget::item { padding: 4px; }"
        )
        self.viewLayout.addWidget(self.lang_list)
        
        # 初始语言列表
        init_langs = current_override.target_languages if current_override else config.default_languages
        
        for code, name in PREDEFINED_LANGS:
            item = QListWidgetItem(f"{name} ({code})")
            item.setData(Qt.ItemDataRole.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if code in init_langs else Qt.CheckState.Unchecked)
            self.lang_list.addItem(item)
            
        # --- 自动生成字幕 ---
        auto_layout = QHBoxLayout()
        auto_layout.addWidget(BodyLabel("自动生成字幕 (当没有提供人工字幕时):", self))
        auto_layout.addStretch(1)
        self.auto_switch = SwitchButton(self)
        self.auto_switch.setChecked(current_override.enable_auto_captions if current_override else config.enable_auto_captions)
        auto_layout.addWidget(self.auto_switch)
        self.viewLayout.addLayout(auto_layout)
        
        # --- 嵌入选项区域 ---
        self._embed_row = QHBoxLayout()
        self._embed_combo = ComboBox(self)
        self._embed_combo.addItems(["软嵌入到视频", "外置字幕文件"])
        
        if current_override:
            self._embed_combo.setCurrentIndex(0 if current_override.embed_subtitles else 1)
        else:
            self._embed_combo.setCurrentIndex(0 if config.embed_type == "soft" else 1)
            
        self._embed_row.addWidget(BodyLabel("嵌入方式:", self))
        self._embed_row.addWidget(self._embed_combo)
        
        # --- 输出格式选项 ---
        self._format_combo = ComboBox(self)
        self._format_combo.addItems(["SRT", "ASS", "VTT", "LRC"])
        
        fmt_mapping = {"srt": 0, "ass": 1, "vtt": 2, "lrc": 3}
        if current_override and current_override.output_format:
            self._format_combo.setCurrentIndex(fmt_mapping.get(current_override.output_format.lower(), 0))
        else:
            self._format_combo.setCurrentIndex(fmt_mapping.get(config.output_format, 0))
            
        self._embed_row.addSpacing(20)
        self._embed_row.addWidget(BodyLabel("字幕格式:", self))
        self._embed_row.addWidget(self._format_combo)
        self._embed_row.addStretch(1)
        self.viewLayout.addLayout(self._embed_row)
        
        # 提示
        hint = CaptionLabel("💡 提示：YT-DLP 将自动下载勾选的所有语言组合。该配置将覆盖全局设置。", self)
        hint.setStyleSheet("color: #8D9BE2;")
        hint.setWordWrap(True)
        self.viewLayout.addWidget(hint)
        
        self.yesButton.setText("确认")
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(450)
            
    def get_override(self) -> PlaylistSubtitleOverride:
        langs = []
        for i in range(self.lang_list.count()):
            item = self.lang_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                langs.append(item.data(Qt.ItemDataRole.UserRole))
                
        embed = self._embed_combo.currentIndex() == 0
        fmt = self._format_combo.currentText().lower()
        auto = self.auto_switch.isChecked()
        return PlaylistSubtitleOverride(
            target_languages=langs,
            enable_auto_captions=auto,
            embed_subtitles=embed,
            output_format=fmt
        )
