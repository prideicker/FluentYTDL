"""
FluentYTDL 动态限速控制组件

提供运行时速度调节功能:
- 滑块实时调节下载速度
- 支持单任务和全局限速
- 预设快捷按钮
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    FluentIcon,
    Slider,
    ToolButton,
    ToolTipFilter,
    ToolTipPosition,
)

from ...core.config_manager import config_manager

# 限速预设值 (bytes/s), 0 表示不限速
RATE_LIMIT_PRESETS = [
    (0, "不限速"),
    (512 * 1024, "512 KB/s"),
    (1024 * 1024, "1 MB/s"),
    (2 * 1024 * 1024, "2 MB/s"),
    (5 * 1024 * 1024, "5 MB/s"),
    (10 * 1024 * 1024, "10 MB/s"),
    (20 * 1024 * 1024, "20 MB/s"),
    (50 * 1024 * 1024, "50 MB/s"),
]


def _format_rate(bytes_per_sec: int) -> str:
    """格式化速度值"""
    if bytes_per_sec <= 0:
        return "不限速"
    elif bytes_per_sec < 1024:
        return f"{bytes_per_sec} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.0f} KB/s"
    else:
        return f"{bytes_per_sec / 1024 / 1024:.1f} MB/s"


class RateLimitSlider(QWidget):
    """
    动态限速滑块组件
    
    可嵌入到下载卡片或全局工具栏。
    """
    
    rateChanged = Signal(int)  # 发射速度值 (bytes/s), 0 表示不限速
    
    def __init__(
        self,
        on_rate_change: Callable[[int], None] | None = None,
        compact: bool = False,
        parent: QWidget | None = None,
    ):
        """
        Args:
            on_rate_change: 速度变化回调
            compact: 紧凑模式（仅显示滑块和值）
            parent: 父组件
        """
        super().__init__(parent)
        self._on_rate_change = on_rate_change
        self._compact = compact
        self._current_rate = 0  # bytes/s
        
        self._init_ui()
        self._load_saved_rate()
    
    def _init_ui(self):
        if self._compact:
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
        else:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            
            # 标签行
            label_layout = QHBoxLayout()
            self.titleLabel = BodyLabel("下载限速", self)
            self.valueLabel = CaptionLabel("不限速", self)
            self.valueLabel.setStyleSheet("color: #0078D4;")
            label_layout.addWidget(self.titleLabel)
            label_layout.addStretch()
            label_layout.addWidget(self.valueLabel)
            layout.addLayout(label_layout)
        
        # 滑块行
        slider_layout = QHBoxLayout()
        slider_layout.setSpacing(8)
        
        # 无限速按钮
        self.unlimitedBtn = ToolButton(FluentIcon.SPEED_HIGH, self)
        self.unlimitedBtn.setToolTip("取消限速")
        self.unlimitedBtn.installEventFilter(ToolTipFilter(self.unlimitedBtn, showDelay=300, position=ToolTipPosition.BOTTOM))
        self.unlimitedBtn.clicked.connect(self._on_unlimited_clicked)
        slider_layout.addWidget(self.unlimitedBtn)
        
        # 滑块 (对数刻度: 0-7 对应预设)
        self.slider = Slider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(0, len(RATE_LIMIT_PRESETS) - 1)
        self.slider.setValue(0)
        self.slider.setTickInterval(1)
        self.slider.setTickPosition(Slider.TickPosition.TicksBelow)
        self.slider.valueChanged.connect(self._on_slider_changed)
        slider_layout.addWidget(self.slider, 1)
        
        if self._compact:
            # 紧凑模式：值标签在右侧
            self.valueLabel = CaptionLabel("不限速", self)
            self.valueLabel.setFixedWidth(70)
            self.valueLabel.setStyleSheet("color: #0078D4;")
            slider_layout.addWidget(self.valueLabel)
            layout.addLayout(slider_layout)
        else:
            layout.addLayout(slider_layout)
    
    def _load_saved_rate(self):
        """从配置加载保存的限速值"""
        saved = config_manager.get("rate_limit", "")
        if not saved:
            self.set_rate(0)
            return
        
        # 解析保存的值 (如 "5M", "1000K")
        try:
            saved = str(saved).strip().upper()
            if saved.endswith("M"):
                rate = int(float(saved[:-1]) * 1024 * 1024)
            elif saved.endswith("K"):
                rate = int(float(saved[:-1]) * 1024)
            else:
                rate = int(saved)
            self.set_rate(rate)
        except ValueError:
            self.set_rate(0)
    
    def set_rate(self, bytes_per_sec: int):
        """
        设置限速值
        
        Args:
            bytes_per_sec: 速度 (bytes/s), 0 表示不限速
        """
        self._current_rate = max(0, bytes_per_sec)
        
        # 更新滑块位置 (找到最接近的预设)
        best_idx = 0
        best_diff = abs(RATE_LIMIT_PRESETS[0][0] - bytes_per_sec)
        for i, (rate, _) in enumerate(RATE_LIMIT_PRESETS):
            diff = abs(rate - bytes_per_sec)
            if diff < best_diff:
                best_diff = diff
                best_idx = i
        
        self.slider.blockSignals(True)
        self.slider.setValue(best_idx)
        self.slider.blockSignals(False)
        
        # 更新显示
        self.valueLabel.setText(_format_rate(self._current_rate))
    
    def get_rate(self) -> int:
        """获取当前限速值 (bytes/s)"""
        return self._current_rate
    
    def get_rate_string(self) -> str:
        """获取限速字符串 (用于 yt-dlp)"""
        if self._current_rate <= 0:
            return ""
        elif self._current_rate >= 1024 * 1024:
            return f"{self._current_rate // 1024 // 1024}M"
        elif self._current_rate >= 1024:
            return f"{self._current_rate // 1024}K"
        else:
            return str(self._current_rate)
    
    def _on_slider_changed(self, index: int):
        """滑块值变更"""
        if 0 <= index < len(RATE_LIMIT_PRESETS):
            rate, _ = RATE_LIMIT_PRESETS[index]
            self._current_rate = rate
            self.valueLabel.setText(_format_rate(rate))
            
            # 保存到配置
            config_manager.set("rate_limit", self.get_rate_string())
            
            # 发射信号
            self.rateChanged.emit(rate)
            if self._on_rate_change:
                self._on_rate_change(rate)
    
    def _on_unlimited_clicked(self):
        """取消限速"""
        self.set_rate(0)
        config_manager.set("rate_limit", "")
        self.rateChanged.emit(0)
        if self._on_rate_change:
            self._on_rate_change(0)


class GlobalRateLimitWidget(QWidget):
    """
    全局限速控制组件
    
    显示在主界面工具栏或状态栏。
    """
    
    rateChanged = Signal(int)
    
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        
        # 图标
        self.iconBtn = ToolButton(FluentIcon.SPEED_OFF, self)
        self.iconBtn.setToolTip("全局限速设置")
        self.iconBtn.installEventFilter(ToolTipFilter(self.iconBtn, showDelay=300, position=ToolTipPosition.BOTTOM))
        layout.addWidget(self.iconBtn)
        
        # 下拉选择
        self.comboBox = ComboBox(self)
        for rate, label in RATE_LIMIT_PRESETS:
            self.comboBox.addItem(label, userData=rate)
        self.comboBox.setCurrentIndex(0)
        self.comboBox.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self.comboBox)
        
        # 从配置加载
        self._load_saved()
    
    def _load_saved(self):
        """加载保存的限速配置"""
        saved = config_manager.get("rate_limit", "")
        if not saved:
            return
        
        try:
            saved = str(saved).strip().upper()
            if saved.endswith("M"):
                rate = int(float(saved[:-1]) * 1024 * 1024)
            elif saved.endswith("K"):
                rate = int(float(saved[:-1]) * 1024)
            else:
                rate = int(saved)
            
            # 找到匹配的预设
            for i, (preset_rate, _) in enumerate(RATE_LIMIT_PRESETS):
                if preset_rate == rate:
                    self.comboBox.setCurrentIndex(i)
                    break
        except ValueError:
            pass
    
    def _on_combo_changed(self, index: int):
        """下拉选择变化"""
        rate = self.comboBox.currentData()
        if rate is not None:
            # 保存到配置
            if rate > 0:
                if rate >= 1024 * 1024:
                    rate_str = f"{rate // 1024 // 1024}M"
                else:
                    rate_str = f"{rate // 1024}K"
                config_manager.set("rate_limit", rate_str)
            else:
                config_manager.set("rate_limit", "")
            
            self.rateChanged.emit(rate)
    
    def get_rate(self) -> int:
        """获取当前限速值"""
        return self.comboBox.currentData() or 0
