from PySide6.QtCore import Qt
from qfluentwidgets import MessageBoxBase, SubtitleLabel

from ...models.playlist_format import PlaylistGlobalFormatOverride
from ..components.format_selector import SimplePresetWidget, _ContainerFormatBar


class PlaylistFormatConfigDialog(MessageBoxBase):
    """
    播放列表级别的全局格式设置面板。
    提供统一的分辨率预设和容器格式设置，配置结果将覆盖自动默认值。
    """
    def __init__(self, current_override: PlaylistGlobalFormatOverride | None = None, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("高级格式设置", self)
        self.viewLayout.addWidget(self.titleLabel)

        self.widget.setMinimumWidth(480)

        # 简单预设面板
        self.preset_widget = SimplePresetWidget(info=None, parent=self)
        self.preset_widget.audio_pick_btn.hide()  # 全局模式下不支持精选到某一条音轨
        
        # 容器输出设定栏
        self.format_bar = _ContainerFormatBar(self)
        
        # 联动：切换“音、视”大类时更新底部的格式扩展栏状态
        self.preset_widget.typeChanged.connect(self.format_bar.set_mode)
        
        self.viewLayout.addWidget(self.preset_widget)
        self.viewLayout.addWidget(self.format_bar)

        if current_override:
            # 根据已保存的覆盖配置还原界面
            type_idx = {"video_audio": 0, "video_only": 1, "audio_only": 2}.get(current_override.download_type, 0)
            self.preset_widget._type_combo.setCurrentIndex(type_idx)
            
            for radio in self.preset_widget.radios:
                if radio.property("preset_id") == current_override.preset_id:
                    radio.setChecked(True)
                    break
            
            if current_override.container_override:
                idx = self.format_bar.container_combo.findText(
                    current_override.container_override, 
                    Qt.MatchFlag.MatchFixedString | Qt.MatchFlag.MatchCaseSensitive
                )
                if idx == -1:
                    idx = self.format_bar.container_combo.findText(
                        current_override.container_override.lower(), 
                        Qt.MatchFlag.MatchStartsWith | Qt.MatchFlag.MatchCaseSensitive
                    )
                if idx >= 0:
                    self.format_bar.container_combo.setCurrentIndex(idx)
            
            if current_override.audio_format_override:
                idx = self.format_bar.audio_combo.findText(
                    current_override.audio_format_override, 
                    Qt.MatchFlag.MatchFixedString | Qt.MatchFlag.MatchCaseSensitive
                )
                if idx == -1:
                    idx = self.format_bar.audio_combo.findText(
                        current_override.audio_format_override.lower(), 
                        Qt.MatchFlag.MatchStartsWith | Qt.MatchFlag.MatchCaseSensitive
                    )
                if idx >= 0:
                    self.format_bar.audio_combo.setCurrentIndex(idx)
                    
        self.yesButton.setText("应用至全体")
        self.cancelButton.setText("取消")

    def get_override(self) -> PlaylistGlobalFormatOverride:
        sel = self.preset_widget.get_current_selection()
        # 由于 SimplePresetWidget 的组合框索引映射为预设数组的键
        download_type = self.preset_widget.get_current_type()
        
        return PlaylistGlobalFormatOverride(
            download_type=download_type,
            preset_id=sel.get("id"),
            preset_intent=sel.get("intent"),
            container_override=self.format_bar.get_container_override(),
            audio_format_override=self.format_bar.get_audio_override()
        )
