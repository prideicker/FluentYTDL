from __future__ import annotations

from typing import Any

import shutil
import subprocess
import os
import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QWidget, QVBoxLayout

from qfluentwidgets import (
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
from ..core.yt_dlp_cli import resolve_yt_dlp_exe, run_version
from ..utils.paths import find_bundled_executable, is_frozen
from .components.smart_setting_card import SmartSettingCard
from ..core.dependency_manager import dependency_manager


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
        if self.component_key == "ffmpeg": exe_name = "ffmpeg.exe"
        elif self.component_key == "deno": exe_name = "deno.exe"
        
        file, _ = QFileDialog.getOpenFileName(
            self.window(),
            f"选择 {exe_name}",
            "",
            f"Executables ({exe_name});;All Files (*)"
        )
        
        if not file: return
        
        try:
            src = Path(file)
            if not src.exists(): return
            
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
        if key != self.component_key: return
        self.actionButton.setText("正在检查...")
        self.actionButton.setEnabled(False)

    def _on_check_finished(self, key, result):
        if key != self.component_key: return
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
        if key != self.component_key: return
        self.progressBar.setVisible(True)
        self.progressBar.setValue(0)
        self.actionButton.setEnabled(False)
        self.actionButton.setText("正在下载...")

    def _on_download_progress(self, key, percent):
        if key != self.component_key: return
        self.progressBar.setValue(percent)

    def _on_download_finished(self, key):
        if key != self.component_key: return
        self.actionButton.setText("正在安装...")

    def _on_install_finished(self, key):
        if key != self.component_key: return
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
        if key != self.component_key: return
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

        self.expandLayout.setSpacing(20)
        self.expandLayout.setContentsMargins(30, 20, 30, 20)

        self._init_header()
        self._init_download_group()
        self._init_network_group()
        self._init_core_group()
        self._init_advanced_group()
        self._init_automation_group()
        self._init_behavior_group()
        self._init_about_group()

        self._load_settings_to_ui()

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

        self.cookieModeCard = InlineComboBoxCard(
            FluentIcon.PEOPLE,
            "Cookies 来源",
            "选择 Cookies 注入方式",
            ["从浏览器读取", "手动导入 Netscape 文件"],
            self.coreGroup,
        )
        self.cookieModeCard.comboBox.currentIndexChanged.connect(self._on_cookie_mode_changed)

        self.browserCard = InlineComboBoxCard(
            FluentIcon.GLOBE,
            "选择浏览器",
            "用于 cookies-from-browser",
            ["Google Chrome", "Microsoft Edge", "Firefox"],
            self.coreGroup,
        )
        self.browserCard.comboBox.currentIndexChanged.connect(self._on_cookie_browser_changed)

        self.cookieFileCard = PushSettingCard(
            "选择文件",
            FluentIcon.DOCUMENT,
            "Cookies 文件路径",
            config_manager.get("cookie_file") or "未选择",
            self.coreGroup,
        )
        self.cookieFileCard.clicked.connect(self._select_cookie_file)

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
        self.coreGroup.addSettingCard(self.cookieFileCard)
        self.coreGroup.addSettingCard(self.ytDlpCard)
        self.coreGroup.addSettingCard(self.ffmpegCard)
        self.coreGroup.addSettingCard(self.denoCard)
        self.coreGroup.addSettingCard(self.jsRuntimeCard)
        self.expandLayout.addWidget(self.coreGroup)

        # Make Cookie dependent cards look like "children" of cookie mode card
        self._indent_setting_card(self.browserCard)
        self._indent_setting_card(self.cookieFileCard)

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

    def _load_settings_to_ui(self) -> None:
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

        mode = str(config_manager.get("cookie_mode") or "browser")
        self.browserCard.setVisible(mode == "browser")
        self.cookieFileCard.setVisible(mode == "file")

        # Proxy mode -> combobox index
        proxy_mode = str(config_manager.get("proxy_mode") or "off").lower().strip()
        proxy_index_map = {"off": 0, "system": 1, "http": 2, "socks5": 3}
        self.proxyModeCard.comboBox.blockSignals(True)
        self.proxyModeCard.comboBox.setCurrentIndex(proxy_index_map.get(proxy_mode, 0))
        self.proxyModeCard.comboBox.blockSignals(False)
        self._update_proxy_edit_visibility()
        self.proxyEditCard.lineEdit.setText(str(config_manager.get("proxy_url") or "127.0.0.1:7890"))

        # Cookie mode -> combobox index
        self.cookieModeCard.comboBox.blockSignals(True)
        self.cookieModeCard.comboBox.setCurrentIndex(0 if mode == "browser" else 1)
        self.cookieModeCard.comboBox.blockSignals(False)

        # Browser -> combobox index
        browser = str(config_manager.get("cookie_browser") or "chrome")
        browser_index_map = {"chrome": 0, "edge": 1, "firefox": 2}
        self.browserCard.comboBox.blockSignals(True)
        self.browserCard.comboBox.setCurrentIndex(browser_index_map.get(browser, 0))
        self.browserCard.comboBox.blockSignals(False)


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
        mode = "browser" if index == 0 else "file"
        config_manager.set("cookie_mode", mode)
        self.browserCard.setVisible(mode == "browser")
        self.cookieFileCard.setVisible(mode == "file")

    def _on_cookie_browser_changed(self, index: int) -> None:
        mapping = {0: "chrome", 1: "edge", 2: "firefox"}
        browser = mapping.get(index, "chrome")
        config_manager.set("cookie_browser", browser)

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

    def _select_cookie_file(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self,
            "选择 cookies.txt",
            "",
            "Text Files (*.txt);;All Files (*)",
        )
        if file:
            if self._is_probably_json_cookie_file(file):
                InfoBar.error(
                    "Cookies 文件格式不支持",
                    "检测到疑似 JSON 导出格式。yt-dlp 仅支持 Netscape HTTP Cookie File 格式（纯文本）。\n"
                    "请使用 Get cookies.txt LOCALLY/cookies.txt 插件导出 Netscape 格式。",
                    parent=self,
                )
                return

            header_ok, newline_ok = self._quick_check_cookiefile_format(file)
            if not header_ok:
                InfoBar.warning(
                    "Cookies 文件可能不符合规范",
                    "yt-dlp FAQ 提示 cookies.txt 首行应为 “# Netscape HTTP Cookie File” 或 “# HTTP Cookie File”。\n"
                    "若后续报错 (例如 HTTP 400/解析失败)，建议重新导出为标准 Netscape 格式。",
                    duration=15000,
                    parent=self,
                )
            if not newline_ok:
                InfoBar.warning(
                    "Cookies 文件换行可能不匹配 Windows",
                    "检测到文件可能使用 LF(\n) 而非 CRLF(\r\n)。在 Windows 上这可能导致 HTTP 400。\n"
                    "如遇到 HTTP 400，请用文本工具转换为 CRLF 后重试。",
                    duration=15000,
                    parent=self,
                )

            config_manager.set("cookie_file", file)
            self.cookieFileCard.setContent(file)
            InfoBar.info(
                "提示：YouTube cookies 建议导出方式",
                "YouTube 会在浏览器标签页中频繁轮换账号 cookies。\n"
                "官方建议：用无痕/隐私窗口登录 YouTube → 同一标签页打开 https://www.youtube.com/robots.txt → 导出 youtube.com cookies → 立刻关闭无痕窗口。",
                duration=15000,
                parent=self,
            )

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
