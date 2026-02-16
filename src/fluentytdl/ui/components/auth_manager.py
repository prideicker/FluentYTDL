"""
FluentYTDL 账户管理 UI 组件

提供 Cookie 账户的可视化管理：
- 账户列表展示
- 一键刷新 Cookie
- 添加/删除账户
- 状态验证显示
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    FluentIcon,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    StateToolTip,
    StrongBodyLabel,
    SwitchButton,
    ToolButton,
    ToolTipFilter,
    ToolTipPosition,
)

from ...auth.cookie_manager import (
    SUPPORTED_BROWSERS,
    AuthProfile,
    CookieManager,
    cookie_manager,
)
from ...utils.logger import logger


class AuthProfileCard(QFrame):
    """
    单个账户配置卡片
    
    显示账户状态、Cookie 来源、最后更新时间等信息。
    """
    
    refreshRequested = Signal(object)  # AuthProfile
    deleteRequested = Signal(object)   # AuthProfile
    
    def __init__(self, profile: AuthProfile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self._init_ui()
        self._update_display()
    
    def _init_ui(self):
        self.setObjectName("authProfileCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            #authProfileCard {
                background-color: rgba(255, 255, 255, 0.7);
                border: 1px solid rgba(0, 0, 0, 0.1);
                border-radius: 8px;
                padding: 12px;
            }
            #authProfileCard:hover {
                background-color: rgba(255, 255, 255, 0.9);
                border-color: rgba(0, 120, 212, 0.3);
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # 左侧：状态图标
        self.statusIcon = IconWidget(FluentIcon.ACCEPT, self)
        self.statusIcon.setFixedSize(24, 24)
        layout.addWidget(self.statusIcon)
        
        # 中间：信息区
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        
        # 名称行
        name_layout = QHBoxLayout()
        self.nameLabel = StrongBodyLabel(self.profile.name, self)
        name_layout.addWidget(self.nameLabel)
        
        self.platformLabel = CaptionLabel(f"({self.profile.platform})", self)
        self.platformLabel.setStyleSheet("color: #666;")
        name_layout.addWidget(self.platformLabel)
        name_layout.addStretch()
        
        info_layout.addLayout(name_layout)
        
        # 来源行
        self.sourceLabel = CaptionLabel("", self)
        info_layout.addWidget(self.sourceLabel)
        
        # 状态行
        self.statusLabel = CaptionLabel("", self)
        info_layout.addWidget(self.statusLabel)
        
        layout.addLayout(info_layout, 1)
        
        # 右侧：操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        self.enableSwitch = SwitchButton(self)
        self.enableSwitch.setChecked(self.profile.enabled)
        self.enableSwitch.checkedChanged.connect(self._on_enabled_changed)
        btn_layout.addWidget(self.enableSwitch)
        
        self.refreshBtn = ToolButton(FluentIcon.SYNC, self)
        self.refreshBtn.setToolTip("刷新 Cookie")
        self.refreshBtn.installEventFilter(ToolTipFilter(self.refreshBtn, showDelay=300, position=ToolTipPosition.BOTTOM))
        self.refreshBtn.clicked.connect(self._on_refresh)
        btn_layout.addWidget(self.refreshBtn)
        
        self.deleteBtn = ToolButton(FluentIcon.DELETE, self)
        self.deleteBtn.setToolTip("删除账户")
        self.deleteBtn.installEventFilter(ToolTipFilter(self.deleteBtn, showDelay=300, position=ToolTipPosition.BOTTOM))
        self.deleteBtn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self.deleteBtn)
        
        layout.addLayout(btn_layout)
    
    def _update_display(self):
        """更新显示内容"""
        p = self.profile
        
        # 状态图标
        if p.is_valid:
            self.statusIcon.setIcon(FluentIcon.ACCEPT)
            self.statusIcon.setStyleSheet("color: #107C10;")
        else:
            self.statusIcon.setIcon(FluentIcon.INFO)
            self.statusIcon.setStyleSheet("color: #797775;")
        
        # 来源
        source_text = f"🌐 来源: {p.cookie_source.title()}"
        if p.cookie_source == "file" and p.cookie_path:
            source_text += f" ({p.cookie_path[-30:]}...)" if len(p.cookie_path or "") > 30 else f" ({p.cookie_path})"
        self.sourceLabel.setText(source_text)
        
        # 状态
        if p.last_updated:
            status = f"📅 更新: {p.last_updated[:16]}  |  "
        else:
            status = "📅 未更新  |  "
        
        if p.is_valid:
            status += f"✅ 有效 ({p.cookie_count} 条 Cookie)"
        else:
            status += "❌ 需要刷新"
        self.statusLabel.setText(status)
        
        # 开关状态
        self.enableSwitch.setChecked(p.enabled)
    
    def _on_enabled_changed(self, enabled: bool):
        self.profile.enabled = enabled
    
    def _on_refresh(self):
        self.refreshRequested.emit(self.profile)
    
    def _on_delete(self):
        self.deleteRequested.emit(self.profile)
    
    def update_profile(self, profile: AuthProfile):
        """更新配置"""
        self.profile = profile
        self._update_display()


class AddAuthProfileDialog(QFrame):
    """
    添加账户对话框 (内嵌式)
    """
    
    profileCreated = Signal(object)  # AuthProfile
    cancelled = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        self.setObjectName("addAuthDialog")
        self.setStyleSheet("""
            #addAuthDialog {
                background-color: rgba(240, 240, 240, 0.95);
                border: 1px solid rgba(0, 0, 0, 0.15);
                border-radius: 8px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # 名称
        name_layout = QHBoxLayout()
        name_layout.addWidget(BodyLabel("名称:", self))
        self.nameEdit = LineEdit(self)
        self.nameEdit.setPlaceholderText("如 YouTube 会员")
        name_layout.addWidget(self.nameEdit, 1)
        layout.addLayout(name_layout)
        
        # 平台
        platform_layout = QHBoxLayout()
        platform_layout.addWidget(BodyLabel("平台:", self))
        self.platformCombo = ComboBox(self)
        self.platformCombo.addItems(["youtube", "bilibili", "twitter", "tiktok"])
        platform_layout.addWidget(self.platformCombo, 1)
        layout.addLayout(platform_layout)
        
        # 来源
        source_layout = QHBoxLayout()
        source_layout.addWidget(BodyLabel("来源:", self))
        self.sourceCombo = ComboBox(self)
        self.sourceCombo.addItems(SUPPORTED_BROWSERS)
        source_layout.addWidget(self.sourceCombo, 1)
        layout.addLayout(source_layout)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.cancelBtn = PushButton("取消", self)
        self.cancelBtn.clicked.connect(self.cancelled.emit)
        btn_layout.addWidget(self.cancelBtn)
        
        self.confirmBtn = PrimaryPushButton("添加", self)
        self.confirmBtn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(self.confirmBtn)
        
        layout.addLayout(btn_layout)
    
    def _on_confirm(self):
        name = self.nameEdit.text().strip()
        if not name:
            InfoBar.warning("提示", "请输入账户名称", parent=self.window())
            return
        
        profile = AuthProfile(
            name=name,
            platform=self.platformCombo.currentText(),
            cookie_source=self.sourceCombo.currentText(),
        )
        self.profileCreated.emit(profile)
    
    def reset(self):
        """重置表单"""
        self.nameEdit.clear()
        self.platformCombo.setCurrentIndex(0)
        self.sourceCombo.setCurrentIndex(0)


class AuthManagerWidget(QWidget):
    """
    账户管理器组件
    
    包含账户列表和添加按钮。
    """
    
    def __init__(self, manager: CookieManager | None = None, parent=None):
        super().__init__(parent)
        self.manager = manager or cookie_manager
        self._cards: dict[str, AuthProfileCard] = {}
        self._state_tooltip: StateToolTip | None = None
        self._init_ui()
        self._load_profiles()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 账户列表容器
        self.listContainer = QWidget(self)
        self.listLayout = QVBoxLayout(self.listContainer)
        self.listLayout.setContentsMargins(0, 0, 0, 0)
        self.listLayout.setSpacing(8)
        layout.addWidget(self.listContainer)
        
        # 空状态提示
        self.emptyLabel = CaptionLabel("暂无账户配置，点击下方按钮添加", self)
        self.emptyLabel.setStyleSheet("color: #666;")
        self.listLayout.addWidget(self.emptyLabel, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # 添加对话框 (默认隐藏)
        self.addDialog = AddAuthProfileDialog(self)
        self.addDialog.setVisible(False)
        self.addDialog.profileCreated.connect(self._on_profile_created)
        self.addDialog.cancelled.connect(self._hide_add_dialog)
        layout.addWidget(self.addDialog)
        
        # 添加按钮
        self.addBtn = PushButton("添加账户", self, FluentIcon.ADD)
        self.addBtn.clicked.connect(self._show_add_dialog)
        layout.addWidget(self.addBtn)
        
        # 可用性提示
        if not self.manager.available:
            self.warningLabel = CaptionLabel(
                "❌ rookiepy 未安装，Cookie 自动提取不可用。请运行: pip install rookiepy",
                self
            )
            self.warningLabel.setStyleSheet("color: #A80000;")
            layout.addWidget(self.warningLabel)
    
    def _load_profiles(self):
        """加载现有账户"""
        profiles = self.manager.get_profiles()
        
        for profile in profiles:
            self._add_profile_card(profile)
        
        self._update_empty_state()
    
    def _add_profile_card(self, profile: AuthProfile):
        """添加账户卡片"""
        key = f"{profile.platform}_{profile.name}"
        
        if key in self._cards:
            self._cards[key].update_profile(profile)
            return
        
        card = AuthProfileCard(profile, self)
        card.refreshRequested.connect(self._on_refresh_profile)
        card.deleteRequested.connect(self._on_delete_profile)
        
        self._cards[key] = card
        self.listLayout.insertWidget(self.listLayout.count() - 1, card)
    
    def _update_empty_state(self):
        """更新空状态提示"""
        is_empty = len(self._cards) == 0
        self.emptyLabel.setVisible(is_empty)
    
    def _show_add_dialog(self):
        self.addDialog.reset()
        self.addDialog.setVisible(True)
        self.addBtn.setEnabled(False)
    
    def _hide_add_dialog(self):
        self.addDialog.setVisible(False)
        self.addBtn.setEnabled(True)
    
    def _on_profile_created(self, profile: AuthProfile):
        """处理新建账户"""
        self._hide_add_dialog()
        
        # 添加到管理器
        self.manager.add_profile(profile)
        
        # 添加卡片
        self._add_profile_card(profile)
        self._update_empty_state()
        
        # 立即刷新
        self._on_refresh_profile(profile)
        
        InfoBar.success(
            "成功",
            f"已添加账户: {profile.name}",
            parent=self.window(),
            position=InfoBarPosition.TOP,
        )
    
    def _on_refresh_profile(self, profile: AuthProfile):
        """刷新账户 Cookie"""
        if not self.manager.available:
            InfoBar.warning(
                "不可用",
                "rookiepy 未安装，无法自动提取 Cookie",
                parent=self.window(),
            )
            return
        
        # 显示进度提示
        self._state_tooltip = StateToolTip(
            f"正在刷新 {profile.name}...",
            "请稍候",
            self.window(),
        )
        self._state_tooltip.move(self.window().width() - 300, 50)
        self._state_tooltip.show()
        
        try:
            success = self.manager.refresh_profile(profile)
            
            if success:
                self._state_tooltip.setContent("刷新成功！")
                self._state_tooltip.setState(True)
            else:
                self._state_tooltip.setContent("刷新失败")
                self._state_tooltip.setState(True)
            
            # 更新卡片
            key = f"{profile.platform}_{profile.name}"
            if key in self._cards:
                self._cards[key].update_profile(profile)
                
        except Exception as e:
            logger.error(f"刷新 Cookie 失败: {e}")
            self._state_tooltip.setContent(f"失败: {e}")
            self._state_tooltip.setState(True)
    
    def _on_delete_profile(self, profile: AuthProfile):
        """删除账户"""
        key = f"{profile.platform}_{profile.name}"
        
        # 从管理器删除
        self.manager.remove_profile(profile.platform, profile.name)
        
        # 移除卡片
        if key in self._cards:
            card = self._cards.pop(key)
            card.deleteLater()
        
        self._update_empty_state()
        
        InfoBar.info(
            "已删除",
            f"账户 {profile.name} 已移除",
            parent=self.window(),
        )
