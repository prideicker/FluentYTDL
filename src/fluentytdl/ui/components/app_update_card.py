"""
FluentYTDL 软件更新卡片

在设置页 "更新" 标签中显示，提供:
- 当前版本和最新版本对比
- 检查更新 / 立即更新按钮
- 更新日志查看
- 下载进度
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import (
    FluentIcon,
    ProgressBar,
    PushButton,
    SettingCard,
    ToolButton,
    ToolTipFilter,
    ToolTipPosition,
)

from ...core.component_update_manager import component_update_manager
from ...core.config_manager import config_manager
from .custom_info_bar import InfoBar


class AppUpdateSettingCard(SettingCard):
    """软件更新卡片：显示版本信息、检查/执行更新。"""

    def __init__(self, parent: QWidget | None = None):
        try:
            from fluentytdl import __version__

            current_ver = __version__
        except ImportError:
            current_ver = "unknown"

        super().__init__(
            FluentIcon.APPLICATION,
            "FluentYTDL",
            f"当前版本: v{current_ver}",
            parent,
        )
        self._current_version = current_ver
        self._latest_info: dict | None = None
        self._downloading = False

        # 进度条
        self.progressBar = ProgressBar(self)
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.progressBar.setFixedWidth(120)
        self.progressBar.setVisible(False)

        # 更新日志按钮
        self.changelogButton = ToolButton(FluentIcon.DICTIONARY, self)
        self.changelogButton.setToolTip("查看更新日志")
        self.changelogButton.installEventFilter(
            ToolTipFilter(self.changelogButton, showDelay=300, position=ToolTipPosition.BOTTOM)
        )
        self.changelogButton.clicked.connect(self._show_changelog)
        self.changelogButton.setVisible(False)

        # 操作按钮
        self.actionButton = PushButton("检查更新", self)
        self.actionButton.clicked.connect(self._on_action_clicked)

        # 布局
        self.hBoxLayout.addWidget(self.progressBar, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(10)
        self.hBoxLayout.addWidget(self.changelogButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(5)
        self.hBoxLayout.addWidget(self.actionButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

        # 连接信号
        component_update_manager.app_update_available.connect(self._on_update_available)
        component_update_manager.app_no_update.connect(self._on_no_update)
        component_update_manager.app_check_error.connect(self._on_check_error)
        component_update_manager.download_progress.connect(self._on_download_progress)
        component_update_manager.download_finished.connect(self._on_download_finished)
        component_update_manager.download_error.connect(self._on_download_error)

    # ── 状态机 ────────────────────────────────────────────

    def _on_action_clicked(self) -> None:
        text = self.actionButton.text()
        if text == "检查更新":
            self._start_check()
        elif text == "立即更新":
            self._start_download()

    def _start_check(self) -> None:
        """开始检查更新。"""
        # 检查 beta 锁定
        if component_update_manager.is_beta():
            self._show_beta_dialog()
            return

        self.actionButton.setText("正在检查...")
        self.actionButton.setEnabled(False)
        component_update_manager.check_app_update()

    def _start_download(self) -> None:
        """开始下载更新。"""
        if not self._latest_info:
            return

        url = self._latest_info.get("url", "")
        if not url:
            InfoBar.error("错误", "下载地址无效", parent=self.window())
            return

        self._downloading = True
        self.progressBar.setVisible(True)
        self.progressBar.setValue(0)
        self.actionButton.setEnabled(False)
        self.actionButton.setText("正在下载...")
        self.changelogButton.setEnabled(False)

        sha256 = self._latest_info.get("sha256", "")
        component_update_manager.download_app_update(url, sha256)

    # ── 信号回调 ──────────────────────────────────────────

    def _on_update_available(self, info: dict) -> None:
        """有更新可用。"""
        self._latest_info = info
        self.actionButton.setEnabled(True)

        latest_ver = info.get("version", "?")
        is_pre = info.get("is_prerelease", False)
        prefix = "预发布 " if is_pre else ""

        self.setTitle(f"FluentYTDL ({prefix}更新)")
        self.setContent(
            f"当前: v{self._current_version}  |  最新: v{latest_ver}"
        )
        self.actionButton.setText("立即更新")
        self.changelogButton.setVisible(True)

        InfoBar.info(
            "发现新版本",
            f"FluentYTDL v{latest_ver} 已可用",
            duration=10000,
            parent=self.window(),
        )

    def _on_no_update(self) -> None:
        """无更新。"""
        self.actionButton.setEnabled(True)
        self.actionButton.setText("检查更新")
        self.setContent(f"当前版本: v{self._current_version}  |  已是最新")

        InfoBar.success(
            "已是最新",
            f"FluentYTDL v{self._current_version} 已是最新版本。",
            duration=5000,
            parent=self.window(),
        )

    def _on_check_error(self, msg: str) -> None:
        """检查出错。"""
        self.actionButton.setEnabled(True)
        self.actionButton.setText("检查更新")

        if msg == "beta":
            self._show_beta_dialog()
            return

        InfoBar.error("检查更新失败", msg, duration=10000, parent=self.window())

    def _on_download_progress(self, percent: int) -> None:
        """下载进度。"""
        if self._downloading:
            self.progressBar.setValue(percent)
            self.actionButton.setText(f"正在下载... {percent}%")

    def _on_download_finished(self, path: str) -> None:
        """下载完成，启动 updater。"""
        self.progressBar.setValue(100)
        self.actionButton.setText("正在安装...")

        try:
            component_update_manager.apply_app_core_update(path)
        except FileNotFoundError as e:
            self._downloading = False
            self.progressBar.setVisible(False)
            self.actionButton.setEnabled(True)
            self.actionButton.setText("立即更新")
            InfoBar.error("更新失败", str(e), parent=self.window())
        except Exception as e:
            self._downloading = False
            self.progressBar.setVisible(False)
            self.actionButton.setEnabled(True)
            self.actionButton.setText("立即更新")
            InfoBar.error("更新失败", str(e), parent=self.window())

    def _on_download_error(self, msg: str) -> None:
        """下载出错。"""
        self._downloading = False
        self.progressBar.setVisible(False)
        self.actionButton.setEnabled(True)
        self.actionButton.setText("立即更新")
        self.changelogButton.setEnabled(True)
        InfoBar.error("下载失败", msg, duration=15000, parent=self.window())

    # ── 更新日志 ──────────────────────────────────────────

    def _show_changelog(self) -> None:
        """显示更新日志对话框。"""
        if not self._latest_info:
            return

        from .update_dialog import UpdateDialog

        dialog = UpdateDialog(
            {
                "version": self._latest_info.get("version", "?"),
                "changelog": self._latest_info.get("changelog", ""),
                "download_url": self._latest_info.get("url", ""),
                "sha256": self._latest_info.get("sha256", ""),
                "install_type": "full",
            },
            parent=self.window(),
        )
        dialog.exec()

    # ── Beta 弹窗 ─────────────────────────────────────────

    def _show_beta_dialog(self) -> None:
        """显示 beta 版本锁定提示。"""
        try:
            from fluentytdl import __version__

            ver = __version__
        except ImportError:
            ver = "unknown"

        InfoBar.warning(
            "检测到测试版本",
            f"当前运行的是 {ver} 测试版本，不支持自动更新。"
            "如需更新请前往 GitHub Releases 下载正式版。",
            duration=10000,
            parent=self.window(),
        )

    # ── 手动触发检查 ──────────────────────────────────────

    def check_for_update(self) -> None:
        """外部调用：自动检查更新（静默模式，不弹无更新提示）。"""
        if component_update_manager.is_beta():
            return
        component_update_manager.check_app_update()

    def reset_state(self) -> None:
        """重置到初始状态。"""
        self._downloading = False
        self._latest_info = None
        self.progressBar.setVisible(False)
        self.changelogButton.setVisible(False)
        self.actionButton.setEnabled(True)
        self.actionButton.setText("检查更新")
        try:
            from fluentytdl import __version__

            self.setContent(f"当前版本: v{__version__}")
        except ImportError:
            pass
