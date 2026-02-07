from __future__ import annotations

from typing import Any

import shutil
import subprocess
import os
import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import QFileDialog, QWidget, QVBoxLayout

from qfluentwidgets import (
    CheckBox,
    ComboBox,
    FluentIcon,
    HyperlinkCard,
    InfoBar,
    LineEdit,
    PushButton,
    PushSettingCard,
    ScrollArea,
    SettingCard,
    SettingCardGroup,
    SwitchButton,
    SubtitleLabel,
    ProgressBar,
    ToolButton,
)

from ..core.config_manager import config_manager
from ..youtube.yt_dlp_cli import resolve_yt_dlp_exe, run_version
from ..utils.paths import find_bundled_executable, is_frozen
from ..utils.logger import LOG_DIR
from .components.smart_setting_card import SmartSettingCard
from ..core.dependency_manager import dependency_manager


# ============================================================================
# Cookie 刷新 Worker（使用Qt线程，确保打包后正常工作）
# ============================================================================

class CookieRefreshWorker(QThread):
    """Cookie刷新工作线程（Qt线程，打包后可靠）"""
    finished = Signal(bool, str, bool)  # (成功标志, 消息, 是否需要管理员权限)
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def run(self):
        """在Qt线程中执行Cookie刷新"""
        from ..auth.cookie_sentinel import cookie_sentinel
        from ..auth.auth_service import auth_service
        from ..utils.logger import logger
        
        success = False
        message = "未知错误"
        
        try:
            # 直接刷新（调用前已检查权限，或已是管理员/非Edge/Chrome）
            success, message = cookie_sentinel.force_refresh_with_uac()
            
            if not success:
                # 获取详细状态
                status = auth_service.last_status
                if status and hasattr(status, 'message') and status.message:
                    message = status.message
                
                # 友好的错误引导
                browser_name = auth_service.current_source_display
                if "未找到" in message or "not found" in message.lower():
                    message = (
                        f"无法从 {browser_name} 提取 Cookie\n\n"
                        "可能的原因：\n"
                        f"1. {browser_name} 未安装或未登录 YouTube\n"
                        f"2. {browser_name} Cookie 数据库被锁定（请关闭浏览器）\n\n"
                        "建议：完全关闭浏览器后重试"
                    )
                
                logger.warning(f"[CookieRefreshWorker] 提取失败: {message}")
        except Exception as e:
            success = False
            message = f"刷新异常: {str(e)}"
            logger.error(f"[CookieRefreshWorker] 异常: {e}", exc_info=True)
        
        # 发射信号（线程安全，第三个参数保留但不再使用）
        self.finished.emit(success, message, False)


class ComponentSettingCard(SettingCard):
    """Card for managing an external component (check update, install)."""

    def __init__(
        self,
        component_key: str,
        icon: FluentIcon,
        title: str,
        content: str,
        parent=None,
    ):
        super().__init__(icon, title, content, parent)
        self.component_key = component_key
        
        # UI Elements
        self.progressBar = ProgressBar(self)
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.progressBar.setFixedWidth(120)
        self.progressBar.setVisible(False)
        
        self.actionButton = PushButton("检查更新", self)
        self.actionButton.clicked.connect(self._on_action_clicked)
        
        self.importButton = PushButton("手动导入", self, FluentIcon.ADD)
        self.importButton.setToolTip("选择本地文件覆盖当前组件")
        self.importButton.clicked.connect(self._on_import_clicked)
        
        self.folderButton = ToolButton(FluentIcon.FOLDER, self)
        self.folderButton.setToolTip("打开所在文件夹")
        self.folderButton.clicked.connect(self._open_folder)

        # Layout
        self.hBoxLayout.addWidget(self.progressBar, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(10)
        self.hBoxLayout.addWidget(self.actionButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(5)
        self.hBoxLayout.addWidget(self.importButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(5)
        self.hBoxLayout.addWidget(self.folderButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)
        
        # Connect signals
        dependency_manager.check_started.connect(self._on_check_started)
        dependency_manager.check_finished.connect(self._on_check_finished)
        dependency_manager.check_error.connect(self._on_error)
        
        dependency_manager.download_started.connect(self._on_download_started)
        dependency_manager.download_progress.connect(self._on_download_progress)
        dependency_manager.download_finished.connect(self._on_download_finished)
        dependency_manager.download_error.connect(self._on_error)
        dependency_manager.install_finished.connect(self._on_install_finished)

    def _on_action_clicked(self):
        text = self.actionButton.text()
        if text == "检查更新":
            dependency_manager.check_update(self.component_key)
        elif text in ("立即更新", "立即安装"):
            dependency_manager.install_component(self.component_key)
            
    def _on_import_clicked(self):
        # Filter based on component type
        exe_name = "yt-dlp.exe"
        if self.component_key == "ffmpeg":
            exe_name = "ffmpeg.exe"
        elif self.component_key == "deno":
            exe_name = "deno.exe"
        elif self.component_key == "pot-provider":
            exe_name = "bgutil-pot-provider.exe"
        elif self.component_key == "ytarchive":
            exe_name = "ytarchive.exe"
        elif self.component_key == "atomicparsley":
            exe_name = "AtomicParsley.exe"
        
        file, _ = QFileDialog.getOpenFileName(
            self.window(),
            f"选择 {exe_name}",
            "",
            f"Executables ({exe_name});;All Files (*)"
        )
        
        if not file:
            return
        
        try:
            src = Path(file)
            if not src.exists():
                return
            
            target_dir = dependency_manager.get_target_dir(self.component_key)
            target_path = target_dir / exe_name
            
            # Simple check
            if src.stat().st_size == 0:
                InfoBar.error("错误", "所选文件为空", parent=self.window())
                return
                
            shutil.copy2(src, target_path)
            
            InfoBar.success("导入成功", f"已手动导入 {exe_name}", parent=self.window())
            # Refresh version info
            dependency_manager.check_update(self.component_key)
            
        except Exception as e:
            InfoBar.error("导入失败", str(e), parent=self.window())

    def _open_folder(self):
        try:
            path = dependency_manager.get_target_dir(self.component_key)
            if path.exists():
                os.startfile(path)
            else:
                InfoBar.warning("目录不存在", f"{path} 尚未创建", parent=self.window())
        except Exception as e:
            InfoBar.error("错误", str(e), parent=self.window())

    def _on_check_started(self, key):
        if key != self.component_key:
            return
        self.actionButton.setText("正在检查...")
        self.actionButton.setEnabled(False)

    def _on_check_finished(self, key, result):
        if key != self.component_key:
            return
        self.actionButton.setEnabled(True)
        
        curr = result.get('current', 'unknown')
        latest = result.get('latest', 'unknown')
        has_update = result.get('update_available', False)
        
        self.setContent(f"当前: {curr}  |  最新: {latest}")
        
        title_text = self.titleLabel.text()
        
        if has_update:
            self.actionButton.setText("立即更新")
            InfoBar.info(
                f"发现新版本: {title_text}",
                f"版本 {latest} 可用 (当前: {curr})",
                duration=15000,
                parent=self.window()
            )
        else:
            if curr == "unknown":
                self.actionButton.setText("立即安装")
            else:
                self.actionButton.setText("检查更新")
                InfoBar.success(
                    "已是最新",
                    f"{title_text} 当前版本 {curr} 已是最新。",
                    duration=5000,
                    parent=self.window()
                )

    def _on_download_started(self, key):
        if key != self.component_key:
            return
        self.progressBar.setVisible(True)
        self.progressBar.setValue(0)
        self.actionButton.setEnabled(False)
        self.actionButton.setText("正在下载...")

    def _on_download_progress(self, key, percent):
        if key != self.component_key:
            return
        self.progressBar.setValue(percent)

    def _on_download_finished(self, key):
        if key != self.component_key:
            return
        self.actionButton.setText("正在安装...")

    def _on_install_finished(self, key):
        if key != self.component_key:
            return
        self.progressBar.setVisible(False)
        self.actionButton.setEnabled(True)
        self.actionButton.setText("检查更新")
        # Trigger a re-check to update version text
        dependency_manager.check_update(self.component_key)
        
        title_text = self.titleLabel.text()
        InfoBar.success(
            "安装完成",
            f"{title_text} 已成功安装/更新。",
            duration=5000,
            parent=self.window()
        )

    def _on_error(self, key, msg):
        if key != self.component_key:
            return
        self.progressBar.setVisible(False)
        self.actionButton.setEnabled(True)
        self.actionButton.setText("检查更新")  # Reset
        
        title_text = self.titleLabel.text()
        InfoBar.error(
            f"{title_text} 错误",
            msg,
            duration=15000,
            parent=self.window()
        )


class InlineComboBoxCard(SettingCard):
    """A fluent setting card with a right-aligned ComboBox.

    We intentionally avoid QFluentWidgets' ComboBoxSettingCard because it is
    tightly coupled to qconfig persistence.
    """

    def __init__(self, icon, title: str, content: str | None, texts: list[str], parent=None):
        super().__init__(icon, title, content, parent)
        self.comboBox = ComboBox(self)
        self.hBoxLayout.addWidget(self.comboBox, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

        for text in texts:
            self.comboBox.addItem(text)


class InlineLineEditCard(SettingCard):
    """A fluent setting card with a right-aligned LineEdit."""

    def __init__(
        self,
        icon,
        title: str,
        content: str | None,
        placeholder: str | None = None,
        parent=None,
    ):
        super().__init__(icon, title, content, parent)
        self.lineEdit = LineEdit(self)
        if placeholder is not None:
            self.lineEdit.setPlaceholderText(placeholder)
        self.hBoxLayout.addWidget(self.lineEdit, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)


class InlinePathPickerCard(SettingCard):
    """A fluent setting card with a right-aligned LineEdit + pick button."""

    def __init__(
        self,
        icon,
        title: str,
        content: str | None,
        button_text: str = "选择",
        placeholder: str | None = None,
        parent=None,
    ):
        super().__init__(icon, title, content, parent)
        self.lineEdit = LineEdit(self)
        if placeholder is not None:
            self.lineEdit.setPlaceholderText(placeholder)

        self.pickButton = PushButton(button_text, self)

        self.hBoxLayout.addWidget(self.lineEdit, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.pickButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)


class InlinePathPickerActionCard(SettingCard):
    """A fluent setting card with a right-aligned LineEdit + pick button + action button."""

    def __init__(
        self,
        icon,
        title: str,
        content: str | None,
        pick_text: str = "选择",
        action_text: str = "检查",
        placeholder: str | None = None,
        parent=None,
    ):
        super().__init__(icon, title, content, parent)
        self.lineEdit = LineEdit(self)
        if placeholder is not None:
            self.lineEdit.setPlaceholderText(placeholder)

        self.pickButton = PushButton(pick_text, self)
        self.actionButton = PushButton(action_text, self)

        self.hBoxLayout.addWidget(self.lineEdit, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.pickButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.actionButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)


class InlineSwitchCard(SettingCard):
    """A fluent setting card with a right-aligned SwitchButton."""

    checkedChanged = Signal(bool)

    def __init__(self, icon, title: str, content: str | None, parent=None):
        super().__init__(icon, title, content, parent)
        self.switchButton = SwitchButton(self)
        self.hBoxLayout.addWidget(self.switchButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.switchButton.checkedChanged.connect(self.checkedChanged)


class SettingsPage(ScrollArea):
    """设置页面：管理下载、网络、核心组件配置"""

    clipboardAutoDetectChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")

        self.scrollWidget = QWidget()
        self.expandLayout = QVBoxLayout(self.scrollWidget)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        self.scrollWidget.setObjectName("scrollWidget")
        
        # Cookie刷新worker引用（防止垃圾回收）
        self._cookie_worker = None

        self.expandLayout.setSpacing(20)
        self.expandLayout.setContentsMargins(30, 20, 30, 20)

        self._init_header()
        self._init_download_group()
        self._init_network_group()
        self._init_core_group()
        self._init_advanced_group()
        self._init_automation_group()
        self._init_postprocess_group()
        self._init_subtitle_group()
        self._init_behavior_group()
        self._init_log_group()
        self._init_about_group()

        self._load_settings_to_ui()

    def showEvent(self, event):
        """页面显示时更新Cookie状态"""
        super().showEvent(event)
        # 每次显示设置页面时刷新Cookie状态
        self._update_cookie_status()

    def _init_header(self) -> None:
        self.titleLabel = SubtitleLabel("设置", self.scrollWidget)
        self.expandLayout.addWidget(self.titleLabel)

    def _init_download_group(self) -> None:
        self.downloadGroup = SettingCardGroup("下载选项", self.scrollWidget)

        self.downloadFolderCard = PushSettingCard(
            "选择文件夹",
            FluentIcon.FOLDER,
            "默认保存路径",
            str(config_manager.get("download_dir")),
            self.downloadGroup,
        )
        self.downloadFolderCard.clicked.connect(self._select_download_folder)

        self.downloadGroup.addSettingCard(self.downloadFolderCard)
        self.expandLayout.addWidget(self.downloadGroup)

    def _init_network_group(self) -> None:
        self.networkGroup = SettingCardGroup("网络连接", self.scrollWidget)

        self.proxyModeCard = InlineComboBoxCard(
            FluentIcon.GLOBE,
            "代理模式",
            "选择网络连接方式",
            ["不使用代理", "使用系统代理", "手动 HTTP 代理", "手动 SOCKS5 代理"],
            self.networkGroup,
        )
        self.proxyModeCard.comboBox.currentIndexChanged.connect(self._on_proxy_mode_changed)

        self.proxyEditCard = InlineLineEditCard(
            FluentIcon.EDIT,
            "自定义代理地址",
            "仅手动代理模式生效 (示例: 127.0.0.1:7890)",
            placeholder="127.0.0.1:7890",
            parent=self.networkGroup,
        )
        self.proxyEditCard.lineEdit.setText(str(config_manager.get("proxy_url") or "127.0.0.1:7890"))
        self.proxyEditCard.lineEdit.editingFinished.connect(self._on_proxy_url_edited)

        self.networkGroup.addSettingCard(self.proxyModeCard)
        self.networkGroup.addSettingCard(self.proxyEditCard)
        self.expandLayout.addWidget(self.networkGroup)

    def _init_core_group(self) -> None:
        self.coreGroup = SettingCardGroup("核心组件", self.scrollWidget)

        # Check Updates on Startup
        self.checkUpdatesOnStartupCard = InlineSwitchCard(
            FluentIcon.SYNC,
            "启动时自动检查更新",
            "开启后，每隔 24 小时尝试自动检查 yt-dlp 和 ffmpeg 更新（默认开启）",
            parent=self.coreGroup,
        )
        self.checkUpdatesOnStartupCard.checkedChanged.connect(self._on_check_updates_startup_changed)

        # Update Source
        self.updateSourceCard = InlineComboBoxCard(
            FluentIcon.GLOBE,
            "组件更新源",
            "选择组件下载和检查更新的网络来源",
            ["GitHub (官方)", "GHProxy (加速镜像)"],
            self.coreGroup,
        )
        self.updateSourceCard.comboBox.currentIndexChanged.connect(self._on_update_source_changed)

        # === Cookie Sentinel 配置 ===
        self.cookieModeCard = InlineComboBoxCard(
            FluentIcon.PEOPLE,
            "Cookie 验证方式",
            "选择 Cookie 来源（Cookie 卫士会自动维护生命周期）",
            ["🚀 自动从浏览器提取", "📄 手动导入 cookies.txt"],
            self.coreGroup,
        )
        self.cookieModeCard.comboBox.currentIndexChanged.connect(self._on_cookie_mode_changed)

        self.browserCard = InlineComboBoxCard(
            FluentIcon.GLOBE,
            "选择浏览器",
            "Chromium 内核需管理员权限，Firefox 内核无需管理员权限",
            [
                "Microsoft Edge", "Google Chrome (⚠️不稳定)", "Chromium",
                "Brave", "Opera", "Opera GX", "Vivaldi", "Arc",
                "Firefox", "LibreWolf"
            ],
            self.coreGroup,
        )
        self.browserCard.comboBox.currentIndexChanged.connect(self._on_cookie_browser_changed)

        # 手动刷新按钮
        self.refreshCookieCard = PushSettingCard(
            "立即刷新",
            FluentIcon.SYNC,
            "手动刷新 Cookie",
            "从浏览器重新提取 Cookie（可能需要管理员权限）",
            self.coreGroup,
        )
        self.refreshCookieCard.clicked.connect(self._on_refresh_cookie_clicked)

        # Cookie 文件选择
        self.cookieFileCard = PushSettingCard(
            "选择文件",
            FluentIcon.DOCUMENT,
            "Cookie 文件路径",
            "未选择",
            self.coreGroup,
        )
        self.cookieFileCard.clicked.connect(self._select_cookie_file)
        
        # Cookie 状态显示（带打开位置按钮）
        self.cookieStatusCard = PushSettingCard(
            "打开位置",
            FluentIcon.INFO,
            "Cookie 文件",
            "显示当前 Cookie 信息",
            self.coreGroup,
        )
        self.cookieStatusCard.clicked.connect(self._open_cookie_location)
        self._update_cookie_status()

        # New Component Cards
        self.ytDlpCard = ComponentSettingCard(
            "yt-dlp",
            FluentIcon.DOWNLOAD,
            "yt-dlp 引擎",
            "点击检查更新以获取最新版本",
            self.coreGroup
        )
        
        self.ffmpegCard = ComponentSettingCard(
            "ffmpeg",
            FluentIcon.VIDEO,
            "FFmpeg 引擎",
            "点击检查更新以获取最新版本",
            self.coreGroup
        )
        
        # JS Runtime (Deno only for auto-update now)
        self.denoCard = ComponentSettingCard(
            "deno",
            FluentIcon.CODE,
            "JS Runtime (Deno)",
            "用于加速 yt-dlp 解析（点击检查更新）",
            self.coreGroup
        )
        
        # POT Provider (PO Token 服务)
        self.potProviderCard = ComponentSettingCard(
            "pot-provider",
            FluentIcon.CERTIFICATE,
            "POT Provider",
            "用于绕过 YouTube 机器人检测（点击检查更新）",
            self.coreGroup
        )

        # AtomicParsley (封面嵌入工具)
        self.atomicParsleyCard = ComponentSettingCard(
            "atomicparsley",
            FluentIcon.PHOTO,
            "AtomicParsley",
            "用于 MP4/M4A 封面嵌入（启用封面嵌入功能需要此工具）",
            self.coreGroup
        )

        self.jsRuntimeCard = InlineComboBoxCard(
            FluentIcon.CODE,
            "JS Runtime 策略",
            "选择首选的 JavaScript 运行时",
            ["自动(推荐)", "Deno", "Node", "Bun", "QuickJS"],
            self.coreGroup,
        )
        self.jsRuntimeCard.comboBox.currentIndexChanged.connect(self._on_js_runtime_changed)

        self.coreGroup.addSettingCard(self.checkUpdatesOnStartupCard)
        self.coreGroup.addSettingCard(self.updateSourceCard)
        self.coreGroup.addSettingCard(self.cookieModeCard)
        self.coreGroup.addSettingCard(self.browserCard)
        self.coreGroup.addSettingCard(self.refreshCookieCard)
        self.coreGroup.addSettingCard(self.cookieStatusCard)
        self.coreGroup.addSettingCard(self.cookieFileCard)
        self.coreGroup.addSettingCard(self.ytDlpCard)
        self.coreGroup.addSettingCard(self.ffmpegCard)
        self.coreGroup.addSettingCard(self.denoCard)
        self.coreGroup.addSettingCard(self.potProviderCard)
        self.coreGroup.addSettingCard(self.atomicParsleyCard)
        self.coreGroup.addSettingCard(self.jsRuntimeCard)
        self.expandLayout.addWidget(self.coreGroup)

        # Make Cookie dependent cards look like "children" of cookie mode card
        self._indent_setting_card(self.browserCard)
        self._indent_setting_card(self.refreshCookieCard)
        self._indent_setting_card(self.cookieFileCard)
        self._indent_setting_card(self.cookieStatusCard)

    def _init_advanced_group(self) -> None:
        self.advancedGroup = SettingCardGroup("高级", self.scrollWidget)

        self.poTokenCard = SmartSettingCard(
            FluentIcon.CODE,
            "YouTube PO Token(可选)",
            "可留空清除；保存后用于提升可用性（偏极客/实验性）",
            config_key="youtube_po_token",
            parent=self.advancedGroup,
            validator=self._validate_po_token,
            fixer=None,
            prefer_multiline=True,
            dialog_content="粘贴或输入 PO Token。允许留空；非空时将进行简单格式校验。",
        )

        self.jsRuntimePathCard = SmartSettingCard(
            FluentIcon.DOCUMENT,
            "JS Runtime 路径(可选)",
            self._js_runtime_status_text(),
            config_key="js_runtime_path",
            parent=self.advancedGroup,
            validator=self._validate_optional_exe_path,
            fixer=self._fix_windows_path,
            empty_text="",
            dialog_content="请输入 JS Runtime 可执行文件路径（可留空）。支持粘贴带引号的路径。",
            pick_file=True,
            file_filter="Executable Files (*.exe);;All Files (*)",
        )
        self.jsRuntimePathCard.valueChanged.connect(lambda _: self.jsRuntimePathCard.setContent(self._js_runtime_status_text()))

        self.advancedGroup.addSettingCard(self.poTokenCard)
        self.advancedGroup.addSettingCard(self.jsRuntimePathCard)
        self.expandLayout.addWidget(self.advancedGroup)

    def _init_automation_group(self) -> None:
        self.automationGroup = SettingCardGroup("自动化", self.scrollWidget)

        self.clipboardDetectCard = InlineSwitchCard(
            FluentIcon.EDIT,
            "剪贴板自动识别",
            "自动识别复制的 YouTube 链接并弹出解析窗口（默认关闭）",
            parent=self.automationGroup,
        )
        self.clipboardDetectCard.checkedChanged.connect(self._on_clipboard_detect_changed)

        self.automationGroup.addSettingCard(self.clipboardDetectCard)
        self.expandLayout.addWidget(self.automationGroup)

    def _indent_setting_card(self, card: QWidget, left: int = 32) -> None:
        """Indent a setting card to visually indicate it depends on another option."""
        try:
            layout = getattr(card, "hBoxLayout", None) or card.layout()
            if not layout:
                return
            m = layout.contentsMargins()
            layout.setContentsMargins(left, m.top(), m.right(), m.bottom())
        except Exception:
            pass

    @staticmethod
    def _fix_windows_path(text: str) -> str:
        """去除复制路径时常见的引号并清理空白。"""
        s = str(text or "").strip()
        # remove surrounding and embedded quotes
        s = s.replace('"', "").replace("'", "").strip()
        s = os.path.expandvars(s)
        return s

    @staticmethod
    def _validate_optional_exe_path(text: str) -> tuple[bool, str]:
        """校验可选的可执行文件路径：允许为空；非空则必须存在。

        Windows 上额外要求 .exe 结尾（避免把目录/文本误当成可执行文件）。
        """
        s = str(text or "").strip()
        if not s:
            return True, ""
        s = os.path.expandvars(s)
        if not os.path.exists(s):
            return False, "文件不存在，请检查路径是否正确"
        if os.name == "nt" and not s.lower().endswith(".exe"):
            return False, "这看起来不是一个 .exe 文件"
        return True, ""

    @staticmethod
    def _validate_po_token(text: str) -> tuple[bool, str]:
        """PO Token 简单格式校验：允许为空；非空时做保守检查。"""
        s = str(text or "").strip()
        if not s:
            return True, ""
        low = s.lower()
        if "mweb" not in low and "visitor" not in low:
            return False, "Token 格式看起来不对（通常包含 'mweb' 或 'visitor'）"
        return True, ""

    def _init_behavior_group(self) -> None:
        self.behaviorGroup = SettingCardGroup("行为策略", self.scrollWidget)

        self.deletionPolicyCard = InlineComboBoxCard(
            FluentIcon.DELETE,
            "移除任务时的默认行为",
            "选择从列表中删除任务时的文件处理策略",
            ["每次询问 (默认)", "仅移除记录 (保留文件)", "彻底删除 (同时删除文件)"],
            self.behaviorGroup,
        )
        self.deletionPolicyCard.comboBox.currentIndexChanged.connect(self._on_deletion_policy_changed)

        self.playlistSkipAuthcheckCard = InlineSwitchCard(
            FluentIcon.VIDEO,
            "加速播放列表解析（实验性）",
            "跳过 YouTube 登录验证检查（authcheck）。可加快大列表解析，但可能导致部分受限视频无法解析（默认关闭）",
            parent=self.behaviorGroup,
        )
        self.playlistSkipAuthcheckCard.checkedChanged.connect(self._on_playlist_skip_authcheck_changed)

        self.behaviorGroup.addSettingCard(self.deletionPolicyCard)
        self.behaviorGroup.addSettingCard(self.playlistSkipAuthcheckCard)
        self.expandLayout.addWidget(self.behaviorGroup)

    def _init_postprocess_group(self) -> None:
        """初始化后处理设置组（封面嵌入、元数据等）"""
        self.postprocessGroup = SettingCardGroup("后处理", self.scrollWidget)

        # 封面嵌入开关
        self.embedThumbnailCard = InlineSwitchCard(
            FluentIcon.PHOTO,
            "嵌入封面图片",
            "将视频缩略图嵌入到下载文件中作为封面（支持 MP4/MKV/MP3/M4A/FLAC/OGG/OPUS 等格式）",
            parent=self.postprocessGroup,
        )
        self.embedThumbnailCard.checkedChanged.connect(self._on_embed_thumbnail_changed)

        # 元数据嵌入开关
        self.embedMetadataCard = InlineSwitchCard(
            FluentIcon.TAG,
            "嵌入元数据",
            "将视频标题、作者、描述等信息嵌入到下载文件中（推荐开启）",
            parent=self.postprocessGroup,
        )
        self.embedMetadataCard.checkedChanged.connect(self._on_embed_metadata_changed)

        self.postprocessGroup.addSettingCard(self.embedThumbnailCard)
        self.postprocessGroup.addSettingCard(self.embedMetadataCard)
        
        # === SponsorBlock 广告跳过 ===
        # 主开关
        self.sponsorBlockCard = InlineSwitchCard(
            FluentIcon.CANCEL,
            "SponsorBlock 广告跳过",
            "自动跳过视频中的赞助广告、自我推广等片段（基于社区标注）",
            parent=self.postprocessGroup,
        )
        self.sponsorBlockCard.checkedChanged.connect(self._on_sponsorblock_changed)
        
        # 类别选择（点击按钮打开对话框）
        self.sponsorBlockCategoriesCard = SettingCard(
            FluentIcon.SETTING,
            "跳过类别设置",
            self._get_sponsorblock_categories_text(),
            parent=self.postprocessGroup,
        )
        
        # 添加选择按钮
        self._sponsorBlockCategoriesBtn = PushButton("选择类别")
        self._sponsorBlockCategoriesBtn.clicked.connect(self._show_sponsorblock_categories_dialog)
        self.sponsorBlockCategoriesCard.hBoxLayout.addWidget(self._sponsorBlockCategoriesBtn)
        self.sponsorBlockCategoriesCard.hBoxLayout.addSpacing(16)
        
        # 类别复选框容器（用于对话框）
        self._sponsorblock_checkboxes: dict[str, CheckBox] = {}
        
        # 添加到组
        self.postprocessGroup.addSettingCard(self.sponsorBlockCard)
        self.postprocessGroup.addSettingCard(self.sponsorBlockCategoriesCard)
        
        # 缩进类别卡片
        self._indent_setting_card(self.sponsorBlockCategoriesCard)
        
        self.expandLayout.addWidget(self.postprocessGroup)

    def _init_subtitle_group(self) -> None:
        """初始化字幕配置组"""
        self.subtitleGroup = SettingCardGroup("字幕下载", self.scrollWidget)
        
        # 字幕启用开关
        self.subtitleEnabledCard = InlineSwitchCard(
            FluentIcon.DOCUMENT,
            "启用字幕下载",
            "自动下载视频字幕（支持多语言、嵌入、双语合成）",
            parent=self.subtitleGroup,
        )
        self.subtitleEnabledCard.checkedChanged.connect(self._on_subtitle_enabled_changed)
        
        # 默认语言设置
        self.subtitleLanguagesCard = InlineLineEditCard(
            FluentIcon.GLOBE,
            "默认语言",
            "优先下载的字幕语言（逗号分隔，如: zh-Hans,en,ja）",
            placeholder="zh-Hans,en",
            parent=self.subtitleGroup,
        )
        self.subtitleLanguagesCard.lineEdit.editingFinished.connect(self._on_subtitle_languages_edited)
        
        # 嵌入模式
        self.subtitleEmbedModeCard = InlineComboBoxCard(
            FluentIcon.VIDEO,
            "嵌入模式",
            "字幕嵌入视频的策略",
            ["总是嵌入", "从不嵌入", "每次询问"],
            parent=self.subtitleGroup,
        )
        self.subtitleEmbedModeCard.comboBox.currentIndexChanged.connect(self._on_subtitle_embed_mode_changed)
        
        # 字幕格式
        self.subtitleFormatCard = InlineComboBoxCard(
            FluentIcon.DOCUMENT,
            "字幕格式",
            "下载的字幕文件格式",
            ["SRT", "ASS", "VTT"],
            parent=self.subtitleGroup,
        )
        self.subtitleFormatCard.comboBox.currentIndexChanged.connect(self._on_subtitle_format_changed)
        
        # 双语字幕开关
        self.subtitleBilingualCard = InlineSwitchCard(
            FluentIcon.SYNC,
            "启用双语字幕",
            "合成两种语言的字幕到一个文件（主语言在上，副语言在下）",
            parent=self.subtitleGroup,
        )
        self.subtitleBilingualCard.checkedChanged.connect(self._on_subtitle_bilingual_changed)
        
        # 添加卡片到组
        self.subtitleGroup.addSettingCard(self.subtitleEnabledCard)
        self.subtitleGroup.addSettingCard(self.subtitleLanguagesCard)
        self.subtitleGroup.addSettingCard(self.subtitleEmbedModeCard)
        self.subtitleGroup.addSettingCard(self.subtitleFormatCard)
        self.subtitleGroup.addSettingCard(self.subtitleBilingualCard)
        
        # 缩进依赖项
        self._indent_setting_card(self.subtitleLanguagesCard)
        self._indent_setting_card(self.subtitleEmbedModeCard)
        self._indent_setting_card(self.subtitleFormatCard)
        self._indent_setting_card(self.subtitleBilingualCard)
        
        self.expandLayout.addWidget(self.subtitleGroup)

    def _init_about_group(self) -> None:
        self.aboutGroup = SettingCardGroup("关于", self.scrollWidget)
        self.aboutCard = HyperlinkCard(
            "https://github.com/yt-dlp/yt-dlp",
            "访问 yt-dlp 仓库",
            FluentIcon.GITHUB,
            "FluentYTDL Pro",
            "基于 PySide6 & Fluent Design 构建",
            self.aboutGroup,
        )
        self.aboutGroup.addSettingCard(self.aboutCard)
        self.expandLayout.addWidget(self.aboutGroup)

    def _init_log_group(self) -> None:
        """初始化日志管理组"""
        self.logGroup = SettingCardGroup("日志管理", self.scrollWidget)

        # 日志管理卡片
        self.logCard = SettingCard(
            FluentIcon.DOCUMENT,
            "运行日志",
            f"日志目录: {LOG_DIR}",
            self.logGroup,
        )
        
        # 添加按钮到卡片
        self.viewLogBtn = PushButton("查看日志", self.logCard)
        self.viewLogBtn.clicked.connect(self._on_view_log_clicked)
        
        self.openLogDirBtn = ToolButton(FluentIcon.FOLDER, self.logCard)
        self.openLogDirBtn.setToolTip("打开日志目录")
        self.openLogDirBtn.clicked.connect(self._on_open_log_dir)
        
        self.cleanLogBtn = ToolButton(FluentIcon.DELETE, self.logCard)
        self.cleanLogBtn.setToolTip("清理所有日志")
        self.cleanLogBtn.clicked.connect(self._on_clean_log_clicked)
        
        self.logCard.hBoxLayout.addWidget(self.viewLogBtn, 0, Qt.AlignmentFlag.AlignRight)
        self.logCard.hBoxLayout.addSpacing(8)
        self.logCard.hBoxLayout.addWidget(self.openLogDirBtn, 0, Qt.AlignmentFlag.AlignRight)
        self.logCard.hBoxLayout.addSpacing(8)
        self.logCard.hBoxLayout.addWidget(self.cleanLogBtn, 0, Qt.AlignmentFlag.AlignRight)
        self.logCard.hBoxLayout.addSpacing(16)
        
        self.logGroup.addSettingCard(self.logCard)
        self.expandLayout.addWidget(self.logGroup)

    def _on_view_log_clicked(self):
        """打开日志查看器"""
        from .components.log_viewer_dialog import LogViewerDialog
        dialog = LogViewerDialog(self.window())
        dialog.exec()

    def _on_open_log_dir(self):
        """打开日志目录"""
        try:
            if os.path.exists(LOG_DIR):
                os.startfile(LOG_DIR)
            else:
                InfoBar.warning("目录不存在", f"{LOG_DIR} 尚未创建", parent=self.window())
        except Exception as e:
            InfoBar.error("错误", str(e), parent=self.window())

    def _on_clean_log_clicked(self):
        """清理所有日志"""
        from qfluentwidgets import MessageBox
        box = MessageBox(
            "确认清理",
            f"确定要删除所有日志文件吗？\n\n日志目录: {LOG_DIR}",
            self.window()
        )
        if box.exec():
            try:
                if os.path.exists(LOG_DIR):
                    import shutil
                    for f in os.listdir(LOG_DIR):
                        fp = os.path.join(LOG_DIR, f)
                        try:
                            if os.path.isfile(fp):
                                os.remove(fp)
                            elif os.path.isdir(fp):
                                shutil.rmtree(fp)
                        except Exception:
                            pass
                    InfoBar.success("清理完成", "已删除所有日志文件", parent=self.window())
                else:
                    InfoBar.info("无需清理", "日志目录不存在", parent=self.window())
            except Exception as e:
                InfoBar.error("清理失败", str(e), parent=self.window())

    def _load_settings_to_ui(self) -> None:
        # Download paths
        self.downloadFolderCard.setContent(str(config_manager.get("download_dir")))

        # Update Source
        src = str(config_manager.get("update_source") or "github")
        src_idx = 1 if src == "ghproxy" else 0
        self.updateSourceCard.comboBox.blockSignals(True)
        self.updateSourceCard.comboBox.setCurrentIndex(src_idx)
        self.updateSourceCard.comboBox.blockSignals(False)

        # Auto update switch
        auto_check = bool(config_manager.get("check_updates_on_startup", True))
        self.checkUpdatesOnStartupCard.switchButton.blockSignals(True)
        self.checkUpdatesOnStartupCard.switchButton.setChecked(auto_check)
        self.checkUpdatesOnStartupCard.switchButton.blockSignals(False)

        # Proxy mode -> combobox index
        proxy_mode = str(config_manager.get("proxy_mode") or "off").lower().strip()
        proxy_index_map = {"off": 0, "system": 1, "http": 2, "socks5": 3}
        self.proxyModeCard.comboBox.blockSignals(True)
        self.proxyModeCard.comboBox.setCurrentIndex(proxy_index_map.get(proxy_mode, 0))
        self.proxyModeCard.comboBox.blockSignals(False)
        self._update_proxy_edit_visibility()
        self.proxyEditCard.lineEdit.setText(str(config_manager.get("proxy_url") or "127.0.0.1:7890"))

        # Cookie 配置从 auth_service 加载
        from ..auth.auth_service import auth_service, AuthSourceType
        
        current_source = auth_service.current_source
        
        self.cookieModeCard.comboBox.blockSignals(True)
        self.browserCard.comboBox.blockSignals(True)
        
        # 设置 Cookie 模式
        if current_source == AuthSourceType.FILE:
            self.cookieModeCard.comboBox.setCurrentIndex(1)  # 手动文件
            if auth_service._current_file_path:
                self.cookieFileCard.setContent(auth_service._current_file_path)
        else:
            self.cookieModeCard.comboBox.setCurrentIndex(0)  # 自动提取
            
            # 设置浏览器（顺序与UI一致）
            browser_map = {
                AuthSourceType.EDGE: 0,
                AuthSourceType.CHROME: 1,
                AuthSourceType.CHROMIUM: 2,
                AuthSourceType.BRAVE: 3,
                AuthSourceType.OPERA: 4,
                AuthSourceType.OPERA_GX: 5,
                AuthSourceType.VIVALDI: 6,
                AuthSourceType.ARC: 7,
                AuthSourceType.FIREFOX: 8,
                AuthSourceType.LIBREWOLF: 9,
            }
            browser_idx = browser_map.get(current_source, 0)
            self.browserCard.comboBox.setCurrentIndex(browser_idx)
        
        self.cookieModeCard.comboBox.blockSignals(False)
        self.browserCard.comboBox.blockSignals(False)
        
        # 触发可见性更新
        self._on_cookie_mode_changed(self.cookieModeCard.comboBox.currentIndex())


        self.poTokenCard.setValue(str(config_manager.get("youtube_po_token") or ""))

        # Automatic update check (frequency control)
        # Only check if enabled in settings
        if config_manager.get("check_updates_on_startup", True):
            last_check = float(config_manager.get("last_update_check") or 0)
            now = time.time()
            # Check if 24 hours (86400 seconds) have passed.
            if now - last_check > 86400:
                dependency_manager.check_update("yt-dlp")
                dependency_manager.check_update("ffmpeg")
                dependency_manager.check_update("deno")
                dependency_manager.check_update("pot-provider")
                config_manager.set("last_update_check", now)
        
        self.jsRuntimePathCard.setContent(self._js_runtime_status_text())
        self.jsRuntimePathCard.setValue(str(config_manager.get("js_runtime_path") or ""))

        # JS runtime -> combobox index
        js_runtime = str(config_manager.get("js_runtime") or "auto").lower().strip()
        js_index_map = {"auto": 0, "deno": 1, "node": 2, "bun": 3, "quickjs": 4}
        self.jsRuntimeCard.comboBox.blockSignals(True)
        self.jsRuntimeCard.comboBox.setCurrentIndex(js_index_map.get(js_runtime, 0))
        self.jsRuntimeCard.comboBox.blockSignals(False)

        # Clipboard auto-detect
        enabled = bool(config_manager.get("clipboard_auto_detect") or False)
        self.clipboardDetectCard.switchButton.blockSignals(True)
        self.clipboardDetectCard.switchButton.setChecked(enabled)
        self.clipboardDetectCard.switchButton.blockSignals(False)

        # Deletion Policy
        policy = str(config_manager.get("deletion_policy") or "AlwaysAsk")
        # Combo box texts order: ["每次询问 (默认)", "仅移除记录 (保留文件)", "彻底删除 (同时删除文件)"]
        # Map config values to the correct indices
        policy_map = {"AlwaysAsk": 0, "KeepFiles": 1, "DeleteFiles": 2}
        self.deletionPolicyCard.comboBox.blockSignals(True)
        self.deletionPolicyCard.comboBox.setCurrentIndex(policy_map.get(policy, 0))
        self.deletionPolicyCard.comboBox.blockSignals(False)

        # Playlist: skip authcheck
        skip_authcheck = bool(config_manager.get("playlist_skip_authcheck") or False)
        self.playlistSkipAuthcheckCard.switchButton.blockSignals(True)
        self.playlistSkipAuthcheckCard.switchButton.setChecked(skip_authcheck)
        self.playlistSkipAuthcheckCard.switchButton.blockSignals(False)

        # Postprocess: embed thumbnail
        embed_thumbnail = bool(config_manager.get("embed_thumbnail", True))
        self.embedThumbnailCard.switchButton.blockSignals(True)
        self.embedThumbnailCard.switchButton.setChecked(embed_thumbnail)
        self.embedThumbnailCard.switchButton.blockSignals(False)

        # Postprocess: embed metadata
        embed_metadata = bool(config_manager.get("embed_metadata", True))
        self.embedMetadataCard.switchButton.blockSignals(True)
        self.embedMetadataCard.switchButton.setChecked(embed_metadata)
        self.embedMetadataCard.switchButton.blockSignals(False)

        # SponsorBlock: enabled switch
        sponsorblock_enabled = bool(config_manager.get("sponsorblock_enabled", False))
        self.sponsorBlockCard.switchButton.blockSignals(True)
        self.sponsorBlockCard.switchButton.setChecked(sponsorblock_enabled)
        self.sponsorBlockCard.switchButton.blockSignals(False)
        
        # SponsorBlock: 更新类别卡片描述和可见性
        self.sponsorBlockCategoriesCard.setContent(self._get_sponsorblock_categories_text())
        self._update_sponsorblock_categories_visibility(sponsorblock_enabled)
        
        # Subtitle: enabled switch
        subtitle_enabled = bool(config_manager.get("subtitle_enabled", False))
        self.subtitleEnabledCard.switchButton.blockSignals(True)
        self.subtitleEnabledCard.switchButton.setChecked(subtitle_enabled)
        self.subtitleEnabledCard.switchButton.blockSignals(False)
        
        # Subtitle: languages
        subtitle_languages = config_manager.get("subtitle_default_languages", ["zh-Hans", "en"])
        languages_str = ",".join(subtitle_languages) if isinstance(subtitle_languages, list) else str(subtitle_languages)
        self.subtitleLanguagesCard.lineEdit.setText(languages_str)
        
        # Subtitle: embed mode
        embed_mode = str(config_manager.get("subtitle_embed_mode", "always"))
        embed_mode_map = {"always": 0, "never": 1, "ask": 2}
        self.subtitleEmbedModeCard.comboBox.blockSignals(True)
        self.subtitleEmbedModeCard.comboBox.setCurrentIndex(embed_mode_map.get(embed_mode, 0))
        self.subtitleEmbedModeCard.comboBox.blockSignals(False)
        
        # Subtitle: format
        subtitle_format = str(config_manager.get("subtitle_format", "srt")).lower()
        format_map = {"srt": 0, "ass": 1, "vtt": 2}
        self.subtitleFormatCard.comboBox.blockSignals(True)
        self.subtitleFormatCard.comboBox.setCurrentIndex(format_map.get(subtitle_format, 0))
        self.subtitleFormatCard.comboBox.blockSignals(False)
        
        # Subtitle: bilingual
        subtitle_bilingual = bool(config_manager.get("subtitle_enable_bilingual", False))
        self.subtitleBilingualCard.switchButton.blockSignals(True)
        self.subtitleBilingualCard.switchButton.setChecked(subtitle_bilingual)
        self.subtitleBilingualCard.switchButton.blockSignals(False)
        
        # Update subtitle settings visibility
        self._update_subtitle_settings_visibility(subtitle_enabled)

    def _on_update_source_changed(self, index: int) -> None:
        source = "ghproxy" if index == 1 else "github"
        config_manager.set("update_source", source)
        InfoBar.success("设置已更新", f"下载源已切换为: {source}", duration=5000, parent=self)

    def _on_check_updates_startup_changed(self, checked: bool) -> None:
        config_manager.set("check_updates_on_startup", bool(checked))
        InfoBar.success(
            "设置已更新",
            "已开启启动时自动检查更新" if checked else "已关闭启动时自动检查更新",
            duration=5000,
            parent=self,
        )

    def _on_clipboard_detect_changed(self, checked: bool) -> None:
        config_manager.set("clipboard_auto_detect", bool(checked))
        self.clipboardAutoDetectChanged.emit(bool(checked))
        InfoBar.success("设置已更新", "剪贴板自动识别已开启" if checked else "剪贴板自动识别已关闭", duration=5000, parent=self)

    def _on_deletion_policy_changed(self, index: int) -> None:
        # Combo texts order: Ask, KeepFiles, DeleteFiles
        policies = ["AlwaysAsk", "KeepFiles", "DeleteFiles"]
        if 0 <= index < len(policies):
            policy = policies[index]
            config_manager.set("deletion_policy", policy)
            InfoBar.success("设置已更新", f"删除策略已更改为: {policy}", duration=5000, parent=self)

    def _on_playlist_skip_authcheck_changed(self, checked: bool) -> None:
        config_manager.set("playlist_skip_authcheck", bool(checked))
        InfoBar.success(
            "设置已更新",
            "已开启：加速播放列表解析（实验性）" if checked else "已关闭：加速播放列表解析（实验性）",
            duration=5000,
            parent=self,
        )

    def _on_embed_thumbnail_changed(self, checked: bool) -> None:
        """处理封面嵌入开关变更"""
        config_manager.set("embed_thumbnail", bool(checked))
        InfoBar.success(
            "设置已更新",
            "已开启封面嵌入（支持 MP4/MKV/MP3/M4A/FLAC/OGG/OPUS 等格式）" if checked else "已关闭封面嵌入",
            duration=5000,
            parent=self,
        )

    def _on_embed_metadata_changed(self, checked: bool) -> None:
        """处理元数据嵌入开关变更"""
        config_manager.set("embed_metadata", bool(checked))
        InfoBar.success(
            "设置已更新",
            "已开启元数据嵌入（标题、作者、描述等）" if checked else "已关闭元数据嵌入",
            duration=5000,
            parent=self,
        )

    def _on_sponsorblock_changed(self, checked: bool) -> None:
        """处理 SponsorBlock 开关变更"""
        config_manager.set("sponsorblock_enabled", bool(checked))
        self._update_sponsorblock_categories_visibility(checked)
        
        if checked:
            categories = config_manager.get("sponsorblock_categories", [])
            if categories:
                cat_names = {
                    "sponsor": "赞助广告",
                    "selfpromo": "自我推广",
                    "interaction": "互动提醒",
                    "intro": "片头",
                    "outro": "片尾",
                    "preview": "预告",
                    "filler": "填充内容",
                    "music_offtopic": "非音乐部分",
                }
                cat_display = ", ".join(cat_names.get(c, c) for c in categories[:3])
                if len(categories) > 3:
                    cat_display += f" 等 {len(categories)} 项"
                InfoBar.success(
                    "SponsorBlock 已启用",
                    f"将跳过: {cat_display}",
                    duration=5000,
                    parent=self,
                )
            else:
                InfoBar.warning(
                    "SponsorBlock 已启用",
                    "请在下方选择要跳过的类别",
                    duration=5000,
                    parent=self,
                )
        else:
            InfoBar.info(
                "SponsorBlock 已关闭",
                "视频将保留原始内容",
                duration=3000,
                parent=self,
            )
    
    def _update_sponsorblock_categories_visibility(self, visible: bool) -> None:
        """更新 SponsorBlock 类别卡片的可见性"""
        self.sponsorBlockCategoriesCard.setVisible(visible)
    
    def _get_sponsorblock_categories_text(self) -> str:
        """获取当前选中的 SponsorBlock 类别的描述文本"""
        categories = config_manager.get("sponsorblock_categories", ["sponsor", "selfpromo", "interaction"])
        cat_names = {
            "sponsor": "赞助广告",
            "selfpromo": "自我推广", 
            "interaction": "互动提醒",
            "intro": "片头",
            "outro": "片尾",
            "preview": "预告",
            "filler": "填充内容",
            "music_offtopic": "非音乐部分",
        }
        if not categories:
            return "未选择任何类别"
        names = [cat_names.get(c, c) for c in categories]
        if len(names) <= 3:
            return "已选择: " + ", ".join(names)
        return f"已选择 {len(names)} 个类别: " + ", ".join(names[:2]) + " 等"
    
    def _show_sponsorblock_categories_dialog(self) -> None:
        """显示 SponsorBlock 类别选择对话框"""
        from qfluentwidgets import MessageBox
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        
        # 类别定义
        sponsorblock_categories = [
            ("sponsor", "赞助广告", "视频中的付费推广内容"),
            ("selfpromo", "自我推广", "频道推广、社交媒体链接等"),
            ("interaction", "互动提醒", "订阅、点赞、评论提醒"),
            ("intro", "片头", "视频开头的固定片头"),
            ("outro", "片尾", "视频结尾的固定片尾"),
            ("preview", "预告", "视频中的预告片段"),
            ("filler", "填充内容", "与主题无关的闲聊内容"),
            ("music_offtopic", "非音乐部分", "音乐视频中的非音乐内容"),
        ]
        
        # 获取当前选中的类别
        current_categories = set(config_manager.get("sponsorblock_categories", []))
        
        # 创建对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("选择要跳过的片段类型")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 创建复选框
        checkboxes: dict[str, CheckBox] = {}
        for cat_id, cat_name, cat_desc in sponsorblock_categories:
            checkbox = CheckBox(f"{cat_name} - {cat_desc}", dialog)
            checkbox.setChecked(cat_id in current_categories)
            layout.addWidget(checkbox)
            checkboxes[cat_id] = checkbox
        
        # 添加按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            dialog
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 保存选中的类别
            selected = [cat_id for cat_id, cb in checkboxes.items() if cb.isChecked()]
            config_manager.set("sponsorblock_categories", selected)
            
            # 更新卡片描述
            self.sponsorBlockCategoriesCard.setContent(self._get_sponsorblock_categories_text())
            
            if selected:
                InfoBar.success(
                    "类别已更新",
                    f"已选择 {len(selected)} 个类别",
                    duration=3000,
                    parent=self,
                )
            else:
                InfoBar.warning(
                    "未选择类别",
                    "请至少选择一个要跳过的类别",
                    duration=5000,
                    parent=self,
                )

    def _on_proxy_mode_changed(self, index: int) -> None:
        modes = ["off", "system", "http", "socks5"]
        if 0 <= index < len(modes):
            mode = modes[index]
            config_manager.set("proxy_mode", mode)
            # Backward-compat shadow key
            config_manager.set("proxy_enabled", mode in {"http", "socks5"})
            InfoBar.success("设置已更新", f"代理模式已切换为: {self.proxyModeCard.comboBox.currentText()}", duration=5000, parent=self)
            self._update_proxy_edit_visibility()

    def _update_proxy_edit_visibility(self) -> None:
        idx = int(self.proxyModeCard.comboBox.currentIndex())
        self.proxyEditCard.setVisible(idx in (2, 3))

    def _on_proxy_url_edited(self) -> None:
        new_proxy = (self.proxyEditCard.lineEdit.text() or "").strip()
        config_manager.set("proxy_url", new_proxy)
        if new_proxy:
            InfoBar.success("保存成功", f"代理已更新为 {new_proxy}", duration=5000, parent=self)
        else:
            InfoBar.info("已清空", "代理地址已清空。", duration=5000, parent=self)

    def _on_cookie_mode_changed(self, index: int) -> None:
        """Cookie 模式切换：0=浏览器提取, 1=手动文件"""
        from ..auth.auth_service import auth_service, AuthSourceType
        
        if index == 0:
            # 浏览器提取模式
            browser_index = self.browserCard.comboBox.currentIndex()
            browser_map = [
                AuthSourceType.EDGE, AuthSourceType.CHROME, AuthSourceType.CHROMIUM,
                AuthSourceType.BRAVE, AuthSourceType.OPERA, AuthSourceType.OPERA_GX,
                AuthSourceType.VIVALDI, AuthSourceType.ARC,
                AuthSourceType.FIREFOX, AuthSourceType.LIBREWOLF,
            ]
            source = browser_map[browser_index] if 0 <= browser_index < len(browser_map) else AuthSourceType.EDGE
            auth_service.set_source(source, auto_refresh=True)
            
            self.browserCard.setVisible(True)
            self.refreshCookieCard.setVisible(True)
            self.cookieFileCard.setVisible(False)
            
            InfoBar.success(
                "已切换到自动提取",
                f"将从 {auth_service.current_source_display} 自动提取 Cookie",
                duration=3000,
                parent=self
            )
        else:
            # 手动文件模式
            auth_service.set_source(AuthSourceType.FILE, auto_refresh=False)
            
            self.browserCard.setVisible(False)
            self.refreshCookieCard.setVisible(False)
            self.cookieFileCard.setVisible(True)
            
            InfoBar.info(
                "已切换到手动导入",
                "请选择 cookies.txt 文件",
                duration=3000,
                parent=self
            )
        
        self._update_cookie_status()

    def _on_cookie_browser_changed(self, index: int) -> None:
        """浏览器选择变化 - 自动提取新浏览器的 Cookies"""
        from ..auth.auth_service import auth_service, AuthSourceType
        from ..utils.admin_utils import is_admin
        from qfluentwidgets import MessageBox
        
        # 顺序与UI一致
        browser_map = [
            (AuthSourceType.EDGE, "Edge"),
            (AuthSourceType.CHROME, "Chrome"),
            (AuthSourceType.CHROMIUM, "Chromium"),
            (AuthSourceType.BRAVE, "Brave"),
            (AuthSourceType.OPERA, "Opera"),
            (AuthSourceType.OPERA_GX, "Opera GX"),
            (AuthSourceType.VIVALDI, "Vivaldi"),
            (AuthSourceType.ARC, "Arc"),
            (AuthSourceType.FIREFOX, "Firefox"),
            (AuthSourceType.LIBREWOLF, "LibreWolf"),
        ]
        
        if 0 <= index < len(browser_map):
            source, name = browser_map[index]
            
            # Chromium 内核浏览器 v130+ 需要管理员权限
            from ..auth.auth_service import ADMIN_REQUIRED_BROWSERS
            if source in ADMIN_REQUIRED_BROWSERS and not is_admin():
                box = MessageBox(
                    f"{name} 需要管理员权限",
                    f"{name} 使用了 App-Bound 加密保护，\n"
                    f"需要以管理员身份运行程序才能提取 Cookie。\n\n"
                    "点击「以管理员身份重启」后将自动完成提取。\n\n"
                    "或者您可以：\n"
                    "• 选择 Firefox/LibreWolf 浏览器（无需管理员权限）\n"
                    "• 手动导出 Cookie 文件",
                    self
                )
                box.yesButton.setText("以管理员身份重启")
                box.cancelButton.setText("取消")
                
                if box.exec():
                    # 先保存选择
                    auth_service.set_source(source, auto_refresh=True)
                    from ..utils.admin_utils import restart_as_admin
                    restart_as_admin(f"提取 {name} Cookie")
                return
            
            # Firefox/Brave 或已是管理员，正常切换
            auth_service.set_source(source, auto_refresh=True)
            
            InfoBar.info(
                "正在切换浏览器",
                f"正在从 {name} 提取 Cookies，请稍候...",
                duration=3000,
                parent=self
            )
            
            # 清理旧worker
            if self._cookie_worker is not None:
                self._cookie_worker.deleteLater()
            
            # 创建Qt工作线程
            self._cookie_worker = CookieRefreshWorker(self)
            
            # 连接信号（自动在主线程执行）
            def on_finished(success: bool, message: str, need_admin: bool = False):
                if success:
                    InfoBar.success(
                        "切换成功", 
                        f"已从 {name} 提取 Cookies", 
                        duration=8000, 
                        parent=self
                    )
                else:
                    # 显示多行错误消息
                    lines = message.split('\n')
                    if len(lines) > 1:
                        title = f"{name} - {lines[0]}"
                        content = '\n'.join(lines[1:])
                    else:
                        title = f"{name} 提取失败"
                        content = message
                    
                    # 如果需要管理员权限，显示带重启按钮的对话框
                    if need_admin:
                        from qfluentwidgets import MessageBox
                        
                        box = MessageBox(
                            f"{name} 需要管理员权限",
                            content,
                            self
                        )
                        box.yesButton.setText("以管理员身份重启")
                        box.cancelButton.setText("取消")
                        
                        if box.exec():
                            from ..utils.admin_utils import restart_as_admin
                            restart_as_admin(f"提取 {name} Cookie")
                    else:
                        InfoBar.error(
                            title,
                            content,
                            duration=15000,
                            parent=self
                        )
                
                # 总是更新Cookie状态显示
                try:
                    self._update_cookie_status()
                except Exception as e:
                    from ..utils.logger import logger
                    logger.error(f"更新Cookie状态显示失败: {e}")
                
                # 清理worker
                self._cookie_worker = None
            
            self._cookie_worker.finished.connect(on_finished, Qt.QueuedConnection)
            self._cookie_worker.start()

    def _on_refresh_cookie_clicked(self):
        """手动刷新 Cookie 按钮点击"""
        from ..auth.auth_service import auth_service
        from ..utils.admin_utils import is_admin
        from qfluentwidgets import MessageBox
        
        current_source = auth_service.current_source
        
        # 检查是否是 Chromium 内核浏览器且非管理员 - 直接提示重启
        from ..auth.auth_service import ADMIN_REQUIRED_BROWSERS
        if current_source in ADMIN_REQUIRED_BROWSERS and not is_admin():
            browser_name = auth_service.current_source_display
            
            box = MessageBox(
                f"{browser_name} 需要管理员权限",
                f"{browser_name} 使用了 App-Bound 加密保护，\n"
                f"需要以管理员身份运行程序才能提取 Cookie。\n\n"
                "点击「以管理员身份重启」后将自动完成提取。\n\n"
                "或者您可以：\n"
                "• 切换到 Firefox/LibreWolf 浏览器（无需管理员权限）\n"
                "• 手动导出 Cookie 文件",
                self
            )
            box.yesButton.setText("以管理员身份重启")
            box.cancelButton.setText("取消")
            
            if box.exec():
                from ..utils.admin_utils import restart_as_admin
                restart_as_admin(f"提取 {browser_name} Cookie")
            return
        
        # 非 Edge/Chrome 或已是管理员，正常刷新
        self._do_cookie_refresh()
    
    def _do_cookie_refresh(self):
        """实际执行Cookie刷新（已确认权限或非Edge/Chrome）"""
        # 禁用按钮
        self.refreshCookieCard.setEnabled(False)
        self.refreshCookieCard.button.setText("刷新中...")
        
        # 显示进度提示
        InfoBar.info(
            "正在刷新 Cookie",
            "请稍候...",
            duration=3000,
            parent=self
        )
        
        # 清理旧worker
        if self._cookie_worker is not None:
            self._cookie_worker.deleteLater()
        
        # 创建Qt工作线程
        self._cookie_worker = CookieRefreshWorker(self)
        
        # 连接信号（自动在主线程执行）
        def on_finished(success: bool, message: str, need_admin: bool = False):
            # 1. 总是重置按钮状态
            self.refreshCookieCard.setEnabled(True)
            self.refreshCookieCard.button.setText("立即刷新")
            
            # 2. 显示结果消息
            if success:
                InfoBar.success(
                    "刷新成功", 
                    message, 
                    duration=8000, 
                    parent=self
                )
            else:
                # 显示多行错误消息
                lines = message.split('\n')
                if len(lines) > 1:
                    title = lines[0]
                    content = '\n'.join(lines[1:])
                else:
                    title = "Cookie 刷新失败"
                    content = message
                
                InfoBar.error(
                    title,
                    content,
                    duration=15000,
                    parent=self
                )
            
            # 3. 总是更新Cookie状态显示
            try:
                self._update_cookie_status()
            except Exception as e:
                from ..utils.logger import logger
                logger.error(f"更新Cookie状态显示失败: {e}")
            
            # 清理worker
            self._cookie_worker = None
        
        self._cookie_worker.finished.connect(on_finished, Qt.QueuedConnection)
        self._cookie_worker.start()
    
    def _select_cookie_file(self):
        """选择 Cookie 文件并导入到 bin/cookies.txt"""
        from ..auth.auth_service import auth_service, AuthSourceType
        from ..auth.cookie_sentinel import cookie_sentinel
        import shutil
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Cookies 文件",
            "",
            "Cookies 文件 (*.txt);;所有文件 (*.*)"
        )
        
        if file_path:
            # 先验证文件格式
            status = auth_service.validate_file(file_path)
            
            if not status.valid:
                InfoBar.warning(
                    "文件格式有问题",
                    status.message,
                    duration=5000,
                    parent=self
                )
                return
            
            # 复制到统一的 bin/cookies.txt
            try:
                target_path = cookie_sentinel.cookie_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, target_path)
                
                # 设置为文件模式（但实际使用统一路径）
                auth_service.set_source(AuthSourceType.FILE, file_path=str(target_path), auto_refresh=False)
                
                self.cookieFileCard.setContent(f"已导入: {status.cookie_count} 个 Cookie")
                InfoBar.success(
                    "导入成功",
                    f"已导入 {status.cookie_count} 个 Cookie 到 bin/cookies.txt",
                    duration=3000,
                    parent=self
                )
            except Exception as e:
                InfoBar.error(
                    "导入失败",
                    f"复制文件时出错: {e}",
                    duration=5000,
                    parent=self
                )
                return
            
            self._update_cookie_status()
    
    def _open_cookie_location(self):
        """打开 Cookie 文件所在位置"""
        from ..auth.cookie_sentinel import cookie_sentinel
        import subprocess
        import os
        
        cookie_path = cookie_sentinel.cookie_path
        
        if cookie_path.exists():
            # Windows: 使用 explorer 选中文件
            subprocess.run(["explorer", "/select,", str(cookie_path)])
        else:
            # 文件不存在，打开目录
            folder = cookie_path.parent
            if folder.exists():
                os.startfile(str(folder))
            else:
                InfoBar.warning(
                    "目录不存在",
                    f"Cookie 目录尚未创建: {folder}",
                    duration=3000,
                    parent=self
                )
    
    def _update_cookie_status(self):
        """更新 Cookie 状态显示"""
        try:
            from ..auth.cookie_sentinel import cookie_sentinel
            
            info = cookie_sentinel.get_status_info()
            cookie_path = cookie_sentinel.cookie_path
            
            if info['exists']:
                age = info['age_minutes']
                age_str = f"{int(age)}分钟前" if age is not None else "未知"
                
                # 显示实际来源，而不是配置来源
                actual_display = info.get('actual_source_display') or info['source']
                
                # 回退警告或来源不匹配警告
                if info.get('using_fallback') or info.get('source_mismatch'):
                    emoji = "⚠️"
                    # 显示实际来源并标注配置来源
                    if info.get('source_mismatch') and info.get('actual_source_display'):
                        source_text = f"{actual_display}（配置: {info['source']}）"
                    else:
                        source_text = actual_display
                elif info['is_stale']:
                    emoji = "⚠️"
                    source_text = actual_display
                else:
                    emoji = "✅"
                    source_text = actual_display
                
                status_text = f"{emoji} {source_text} | 更新于 {age_str} | {info['cookie_count']} 个 Cookie"
                
                # 如果有回退警告，添加提示
                if info.get('fallback_warning'):
                    status_text += f"\n{info['fallback_warning']}"
            else:
                status_text = f"❌ Cookie 文件不存在 ({cookie_path.name})"
            
            self.cookieStatusCard.contentLabel.setText(status_text)
            
        except Exception as e:
            self.cookieStatusCard.contentLabel.setText(f"状态获取失败: {e}")
    
    def _on_js_runtime_changed(self, index: int) -> None:
        mapping = {0: "auto", 1: "deno", 2: "node", 3: "bun", 4: "quickjs"}
        mode = mapping.get(index, "auto")
        config_manager.set("js_runtime", mode)
        InfoBar.success("设置已更新", f"JS Runtime 已切换为: {self.jsRuntimeCard.comboBox.currentText()}", duration=5000, parent=self)
        self.jsRuntimePathCard.setContent(self._js_runtime_status_text())

    def _on_po_token_edited(self) -> None:
        # Legacy no-op: PO Token is now edited via SmartSettingCard dialog.
        val = str(config_manager.get("youtube_po_token") or "").strip()
        try:
            self.poTokenCard.setValue(val)
        except Exception:
            pass

    def _select_download_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择下载目录")
        if folder:
            config_manager.set("download_dir", folder)
            self.downloadFolderCard.setContent(folder)

    def _select_yt_dlp_path(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self,
            "选择 yt-dlp.exe",
            "",
            "Executables (*.exe);;All Files (*)",
        )
        if file:
            path = self._fix_windows_path(file)
            config_manager.set("yt_dlp_exe_path", path)
            self._on_yt_dlp_path_edited()

    def _on_yt_dlp_path_edited(self) -> None:
        path = self._fix_windows_path(str(config_manager.get("yt_dlp_exe_path") or ""))
        if path and not Path(path).exists():
            InfoBar.warning(
                "路径无效",
                "未找到该文件，已回退为自动检测（优先内置，其次 PATH）。",
                duration=15000,
                parent=self,
            )
            config_manager.set("yt_dlp_exe_path", "")
            try:
                self.ytDlpCard.setValue("")
                self.ytDlpCard.setContent(self._yt_dlp_status_text())
            except Exception:
                pass
            return

        config_manager.set("yt_dlp_exe_path", path)
        try:
            self.ytDlpCard.setValue(path)
            self.ytDlpCard.setContent(f"自定义: {path}" if path else self._yt_dlp_status_text())
        except Exception:
            pass

    def _yt_dlp_status_text(self) -> str:
        cfg = str(config_manager.get("yt_dlp_exe_path") or "").strip()
        if cfg:
            try:
                if Path(cfg).exists():
                    return "已就绪（手动指定）"
            except Exception:
                pass

        if is_frozen():
            p = find_bundled_executable(
                "yt-dlp.exe",
                "yt-dlp/yt-dlp.exe",
                "yt_dlp/yt-dlp.exe",
            )
            if p is not None:
                return "已就绪（内置）"

        which = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
        if which:
            return "已就绪（环境（PATH））"

        return "未就绪（无法解析/下载）"

    @staticmethod
    def _quick_check_cookiefile_format(path: str) -> tuple[bool, bool]:
        """Return (header_ok, newline_ok) for Netscape cookie files."""

        try:
            p = Path(path)
            head = p.read_bytes()[:4096]
            first_line = head.splitlines()[0].decode("utf-8", errors="ignore").strip() if head else ""

            header_ok = first_line.startswith("# Netscape HTTP Cookie File") or first_line.startswith(
                "# HTTP Cookie File"
            )

            # Heuristic: if file contains any '\n' but no '\r\n', it is likely LF-only.
            has_lf = b"\n" in head
            has_crlf = b"\r\n" in head
            newline_ok = (not has_lf) or has_crlf
            return header_ok, newline_ok
        except Exception:
            return True, True

    @staticmethod
    def _is_probably_json_cookie_file(path: str) -> bool:
        try:
            p = Path(path)
            head = p.read_bytes()[:2048]
            text = head.decode("utf-8", errors="ignore").lstrip()
            return bool(text) and text[0] in "[{"
        except Exception:
            return False

    def _select_ffmpeg_path(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self,
            "选择 ffmpeg.exe",
            "",
            "Executables (*.exe);;All Files (*)",
        )
        if file:
            path = self._fix_windows_path(file)
            config_manager.set("ffmpeg_path", path)
            self._on_ffmpeg_path_edited()

    def _on_ffmpeg_path_edited(self) -> None:
        path = self._fix_windows_path(str(config_manager.get("ffmpeg_path") or ""))
        config_manager.set("ffmpeg_path", path)

        if path:
            if not Path(path).exists():
                InfoBar.warning("路径可能无效", "未找到该文件，请确认 ffmpeg.exe 路径是否正确。", duration=15000, parent=self)
            try:
                self.ffmpegCard.setValue(path)
                self.ffmpegCard.setContent(f"自定义: {path}")
            except Exception:
                pass
        else:
            try:
                self.ffmpegCard.setValue("")
                self.ffmpegCard.setContent(self._ffmpeg_status_text())
            except Exception:
                pass

    def _ffmpeg_status_text(self) -> str:
        custom = str(config_manager.get("ffmpeg_path") or "").strip()
        if custom:
            try:
                if Path(custom).exists():
                    return "已就绪（手动指定）"
            except Exception:
                pass

        # Auto-detect priority: bundled (_internal) > PATH
        bundled = find_bundled_executable("ffmpeg.exe", "ffmpeg/ffmpeg.exe") if is_frozen() else None
        if bundled is not None:
            return "已就绪（内置）"

        which = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
        if which:
            return "已就绪（环境（PATH））"

        return "未找到（解决：使用 full 包内置 FFmpeg，或安装 FFmpeg 并加入 PATH，或在此处选择）"

    def _resolve_js_runtime_bundled(self, runtime_id: str) -> Path | None:
        if not is_frozen():
            return None
        if runtime_id == "deno":
            return find_bundled_executable("deno.exe", "js/deno.exe", "deno/deno.exe")
        if runtime_id == "node":
            return find_bundled_executable("node.exe", "js/node.exe", "node/node.exe")
        if runtime_id == "bun":
            return find_bundled_executable("bun.exe", "js/bun.exe", "bun/bun.exe")
        if runtime_id == "quickjs":
            return find_bundled_executable("qjs.exe", "js/qjs.exe", "quickjs/qjs.exe")
        return None

    def _js_runtime_text(self) -> str:
        mode = str(config_manager.get("js_runtime") or "auto").lower()
        label_map = {
            "auto": "自动(推荐)",
            "deno": "Deno",
            "node": "Node",
            "bun": "Bun",
            "quickjs": "QuickJS",
        }
        return label_map.get(mode, mode)

    def _resolve_js_runtime_exe(self) -> tuple[str, Path | None, str]:
        """Return (runtime_id, exe_path, source_text)."""

        preferred = str(config_manager.get("js_runtime") or "auto").strip().lower()
        custom = str(config_manager.get("js_runtime_path") or "").strip()

        if preferred in {"deno", "node", "bun", "quickjs"}:
            if custom and Path(custom).exists():
                return preferred, Path(custom), "自定义"

            bundled = self._resolve_js_runtime_bundled(preferred)
            if bundled is not None:
                return preferred, bundled, "内置"

            if preferred == "deno":
                which = shutil.which("deno")
                return preferred, Path(which) if which else None, "PATH"
            if preferred == "node":
                which = shutil.which("node") or shutil.which("node.exe")
                return preferred, Path(which) if which else None, "PATH"
            if preferred == "bun":
                which = shutil.which("bun") or shutil.which("bun.exe")
                return preferred, Path(which) if which else None, "PATH"
            if preferred == "quickjs":
                which = (
                    shutil.which("qjs")
                    or shutil.which("qjs.exe")
                    or shutil.which("quickjs")
                    or shutil.which("quickjs.exe")
                )
                return preferred, Path(which) if which else None, "PATH"

        # auto: prefer bundled deno (full package), then PATH deno/node/bun/quickjs
        bundled_deno = self._resolve_js_runtime_bundled("deno")
        if bundled_deno is not None:
            return "deno", bundled_deno, "内置"

        deno = shutil.which("deno")
        if deno:
            return "deno", Path(deno), "PATH"

        # winget deno heuristic
        try:
            local_app_data = Path(os.environ.get("LOCALAPPDATA") or "")
            if local_app_data:
                winget_packages = local_app_data / "Microsoft" / "WinGet" / "Packages"
                if winget_packages.exists():
                    matches = list(winget_packages.glob("DenoLand.Deno_*\\deno.exe"))
                    if matches:
                        return "deno", matches[0], "winget"
        except Exception:
            pass

        node = shutil.which("node") or shutil.which("node.exe")
        if node:
            return "node", Path(node), "PATH"
        bun = shutil.which("bun") or shutil.which("bun.exe")
        if bun:
            return "bun", Path(bun), "PATH"
        qjs = shutil.which("qjs") or shutil.which("qjs.exe") or shutil.which("quickjs") or shutil.which("quickjs.exe")
        if qjs:
            return "quickjs", Path(qjs), "PATH"

        return "auto", None, ""

    def _js_runtime_status_text(self) -> str:
        preferred = str(config_manager.get("js_runtime") or "auto").strip().lower()
        rid, exe, source = self._resolve_js_runtime_exe()
        label = {"deno": "Deno", "node": "Node", "bun": "Bun", "quickjs": "QuickJS"}.get(rid, rid)

        source_map = {
            "自定义": "手动指定",
            "内置": "内置",
            "PATH": "环境（PATH）",
            "winget": "winget",
        }
        source_text = source_map.get(source, source or "")

        if preferred == "auto":
            if exe is None:
                return "未就绪（解决：使用 full 包内置 Deno，或安装 deno 并加入 PATH，或在此处选择）"
            return f"已就绪（自动：{label} / {source_text or '未知'}）"

        if exe is None:
            preferred_label = {"deno": "Deno", "node": "Node", "bun": "Bun", "quickjs": "QuickJS"}.get(preferred, preferred)
            return f"未就绪: {preferred_label}（解决：优先使用内置，其次 PATH；也可在此处选择）"
        return f"已就绪（{source_text or '未知'}）"

    def _select_js_runtime_path(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self,
            "选择 JS Runtime 可执行文件（可选）",
            "",
            "Executables (*.exe);;All Files (*)",
        )
        if file:
            path = self._fix_windows_path(file)
            config_manager.set("js_runtime_path", path)
            self._on_js_runtime_path_edited()

    def _on_js_runtime_path_edited(self) -> None:
        path = self._fix_windows_path(str(config_manager.get("js_runtime_path") or ""))
        if path and not Path(path).exists():
            InfoBar.warning(
                "路径无效",
                "未找到该文件，已回退为自动检测（优先内置，其次 PATH）。",
                parent=self,
            )
            config_manager.set("js_runtime_path", "")
            try:
                self.jsRuntimePathCard.setValue("")
                self.jsRuntimePathCard.setContent(self._js_runtime_status_text())
            except Exception:
                pass
            return

        config_manager.set("js_runtime_path", path)
        try:
            self.jsRuntimePathCard.setValue(path)
            self.jsRuntimePathCard.setContent(self._js_runtime_status_text())
        except Exception:
            pass

    def _check_js_runtime(self) -> None:
        rid, exe, source = self._resolve_js_runtime_exe()
        if exe is None:
            InfoBar.warning("未找到 JS Runtime", "请安装 deno/node/bun/quickjs 或在此处指定可执行文件路径。", duration=15000, parent=self)
            return

        candidates: list[list[str]] = [[str(exe), "--version"], [str(exe), "-v"], [str(exe), "-V"]]
        out = ""
        for cmd in candidates:
            try:
                kwargs: dict[str, Any] = {}
                if os.name == "nt":
                    try:
                        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    try:
                        si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
                        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
                        si.wShowWindow = 0
                        kwargs["startupinfo"] = si
                    except Exception:
                        pass

                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **kwargs,
                )
                out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
                if proc.returncode == 0 and out:
                    break
            except Exception:
                continue

        label = {"deno": "Deno", "node": "Node", "bun": "Bun", "quickjs": "QuickJS"}.get(rid, rid)
        ver_line = out.splitlines()[0].strip() if out else "(unknown)"
        InfoBar.info(
            "JS Runtime",
            f"类型: {label}\n版本: {ver_line}\n路径: {exe}\n来源: {source or '未知'}",
            duration=5000,
            parent=self,
        )
        self.jsRuntimePathCard.setContent(self._js_runtime_status_text())

    def _check_yt_dlp(self) -> None:
        exe = resolve_yt_dlp_exe()
        if exe is None:
            InfoBar.error(
                "未找到 yt-dlp.exe",
                "请在此处选择 yt-dlp.exe，或将 yt-dlp.exe 放入 _internal/yt-dlp/，或加入 PATH。",
                duration=15000,
                parent=self,
            )
            return

        ver = run_version() or "(unknown)"
        InfoBar.info(
            "yt-dlp",
            f"版本: {ver}\n路径: {exe}\n更新方式: 替换该 yt-dlp.exe",
            duration=5000,
            parent=self,
        )
        self.ytDlpCard.setContent(self._yt_dlp_status_text())

    def _on_subtitle_enabled_changed(self, checked: bool) -> None:
        config_manager.set('subtitle_enabled', checked)
        self._update_subtitle_settings_visibility(checked)
        status = 'enabled' if checked else 'disabled'
        InfoBar.success('Subtitle Settings', f'Subtitle download {status}', duration=3000, parent=self)
    
    def _on_subtitle_languages_edited(self) -> None:
        text = self.subtitleLanguagesCard.lineEdit.text().strip()
        languages = [lang.strip() for lang in text.split(',') if lang.strip()] if text else ['zh-Hans', 'en']
        config_manager.set('subtitle_default_languages', languages)
        InfoBar.success('Language Settings', f'Default subtitle languages: {", ".join(languages)}', duration=3000, parent=self)
    
    def _on_subtitle_embed_mode_changed(self, index: int) -> None:
        mode_map = {0: 'always', 1: 'never', 2: 'ask'}
        mode = mode_map.get(index, 'always')
        config_manager.set('subtitle_embed_mode', mode)
        InfoBar.success('Embed Mode', f'Subtitle embed strategy: {mode}', duration=3000, parent=self)
    
    def _on_subtitle_format_changed(self, index: int) -> None:
        format_map = {0: 'srt', 1: 'ass', 2: 'vtt'}
        fmt = format_map.get(index, 'srt')
        config_manager.set('subtitle_format', fmt)
        InfoBar.success('Format Settings', f'Subtitle format: {fmt.upper()}', duration=3000, parent=self)
    
    def _on_subtitle_bilingual_changed(self, checked: bool) -> None:
        config_manager.set('subtitle_enable_bilingual', checked)
        status = 'enabled' if checked else 'disabled'
        InfoBar.success('Bilingual Subtitles', f'Bilingual subtitle merge {status}', duration=3000, parent=self)
    
    def _update_subtitle_settings_visibility(self, enabled: bool) -> None:
        self.subtitleLanguagesCard.setVisible(enabled)
        self.subtitleEmbedModeCard.setVisible(enabled)
        self.subtitleFormatCard.setVisible(enabled)
        self.subtitleBilingualCard.setVisible(enabled)

