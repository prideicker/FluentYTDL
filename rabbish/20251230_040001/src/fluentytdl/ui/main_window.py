from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QIntValidator
from PySide6.QtWidgets import (
	QApplication,
	QCheckBox,
	QFrame,
	QHBoxLayout,
	QMenu,
	QScrollArea,
	QSystemTrayIcon,
	QVBoxLayout,
	QWidget,
)

from qfluentwidgets import (
	CaptionLabel,
	ComboBox,
	FluentIcon,
	FluentWindow,
	InfoBar,
	InfoBarPosition,
	LineEdit,
	MessageBox,
	MessageBoxBase,
	MessageDialog,
	NavigationItemPosition,
	PushButton,
	PrimaryPushButton,
	SplashScreen,
	SubtitleLabel,
	TransparentToolButton,
)

from .components.clipboard_monitor import ClipboardMonitor
from .components.download_card import DownloadItemCard
from .components.selection_dialog import SelectionDialog
from .parse_page import ParsePage
from .settings_page import SettingsPage
from .help_window import HelpWindow
from .welcome_wizard import WelcomeWizardDialog
from ..core.download_manager import download_manager
from ..core.config_manager import config_manager
from ..utils.logger import logger
from ..utils.paths import resource_path


class MainWindow(FluentWindow):
	def __init__(self) -> None:
		super().__init__()
		self._updating_concurrent = False
		self._max_concurrent_ui = 2_147_483_647

		# 1. 窗口基础设置
		self.setWindowTitle("FluentYTDL Pro")
		self.resize(1150, 780)

		# 测试钩子：若设置环境变量 FLUENTYTDL_FORCE_POPUP=1，则在删除任务时
		# 强制弹出确认对话框（忽略用户设置），并开启更详细的删除日志。
		try:
			self._force_delete_popup = str(os.environ.get("FLUENTYTDL_FORCE_POPUP") or "").strip() == "1"
		except Exception:
			self._force_delete_popup = False
		logger.debug("force_delete_popup=%s", self._force_delete_popup)

		# 居中显示
		desktop = QApplication.screens()[0].availableGeometry()
		w, h = desktop.width(), desktop.height()
		self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

		# 2. 初始化主页（下载列表容器）
		self.init_home_interface()

		# 解析页
		self.init_parse_interface()

		# 设置页
		self.settings_interface = SettingsPage(self)
		self.settings_interface.clipboardAutoDetectChanged.connect(self.set_clipboard_monitor_enabled)

		# 3. 初始化导航栏
		self.init_navigation()

		# 4. 初始化系统组件 (托盘 & 剪贴板)
		self.init_system_tray()
		self.init_clipboard_monitor()

		# 5. 启动欢迎动画 (可选)
		self.splashScreen = SplashScreen(self.windowIcon(), self)
		self.splashScreen.finish()

		# 6. 帮助中心入口
		self.helpBtn = TransparentToolButton(FluentIcon.HELP, self)
		self.helpBtn.setToolTip("帮助中心 (快速入门 & 手册)")
		self.helpBtn.clicked.connect(self.show_help_window)
		self.titleBar.addWidget(self.helpBtn)

		# 7. 首次启动检测
		self._check_first_run()

	def show_help_window(self):
		if getattr(self, "_help_window", None) is None:
			self._help_window = HelpWindow(self)
		self._help_window.show()
		self._help_window.activateWindow()

	def _check_first_run(self):
		# Delay check to ensure window is fully initialized
		# and not blocking the splash screen fade-out
		from PySide6.QtCore import QTimer
		QTimer.singleShot(1000, self._show_wizard_if_needed)

	def _show_wizard_if_needed(self):
		if not config_manager.get("has_shown_welcome_guide", False):
			w = WelcomeWizardDialog(self)
			w.exec()

	def init_navigation(self) -> None:
		"""配置侧边栏导航"""
		self.addSubInterface(
			self.parse_page,
			FluentIcon.SEARCH,
			"新建解析",
			position=NavigationItemPosition.TOP,
		)

		self.addSubInterface(
			self.home_widget,
			FluentIcon.DOWNLOAD,
			"下载列表",
			position=NavigationItemPosition.TOP,
		)

		self.addSubInterface(
			self.settings_interface,
			FluentIcon.SETTING,
			"设置",
			position=NavigationItemPosition.BOTTOM,
		)

	def init_system_tray(self) -> None:
		"""初始化系统托盘"""
		self.tray_icon = QSystemTrayIcon(self)

		icon_path = resource_path("assets", "logo.png")
		if icon_path.exists():
			self.tray_icon.setIcon(QIcon(str(icon_path)))
		else:
			# fallback: avoid invisible tray icon if resource not present yet
			self.tray_icon.setIcon(self.windowIcon())

		tray_menu = QMenu()
		show_action = QAction("显示主界面", self)
		show_action.triggered.connect(self.showNormal)
		quit_action = QAction("退出", self)
		quit_action.triggered.connect(self.quit_app)

		tray_menu.addAction(show_action)
		tray_menu.addSeparator()
		tray_menu.addAction(quit_action)

		self.tray_icon.setContextMenu(tray_menu)
		self.tray_icon.show()
		self.tray_icon.activated.connect(self._on_tray_icon_activated)

	def _on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
		if reason == QSystemTrayIcon.Trigger:
			if self.isVisible():
				if self.isMinimized():
					self.showNormal()
				else:
					self.showNormal()
					self.activateWindow()
			else:
				self.showNormal()

	def init_clipboard_monitor(self) -> None:
		"""初始化剪贴板监听（默认关闭，可在设置页开启）"""
		enabled = bool(config_manager.get("clipboard_auto_detect") or False)
		self.set_clipboard_monitor_enabled(enabled)

	def set_clipboard_monitor_enabled(self, enabled: bool) -> None:
		# disable
		if not enabled:
			mon = getattr(self, "clipboard_monitor", None)
			if mon is not None:
				try:
					mon.youtube_url_detected.disconnect(self.on_youtube_url_detected)
				except Exception:
					pass
				try:
					mon.deleteLater()
				except Exception:
					pass
				self.clipboard_monitor = None
			return

		# enable
		if getattr(self, "clipboard_monitor", None) is None:
			self.clipboard_monitor = ClipboardMonitor()
			self.clipboard_monitor.youtube_url_detected.connect(self.on_youtube_url_detected)

	def on_youtube_url_detected(self, url: str) -> None:
		"""当检测到 YouTube 链接时的回调"""
		# 如果当前窗口不可见，先唤起窗口（形成“复制链接 -> 自动识别 -> 弹窗”闭环）
		if not self.isVisible():
			self.tray_icon.showMessage(
				"检测到视频链接",
				"点击处理下载任务",
				QSystemTrayIcon.Information,
				2000,
			)
			self.showNormal()
			self.activateWindow()

		self.show_selection_dialog(url)

	def init_parse_interface(self) -> None:
		self.parse_page = ParsePage(self)
		self.parse_page.parse_requested.connect(self.show_selection_dialog)

	def init_home_interface(self) -> None:
		"""初始化主页（下载列表容器）"""
		self.home_widget = QWidget()
		self.home_widget.setObjectName("homeInterface")

		self.home_layout = QVBoxLayout(self.home_widget)
		self.home_layout.setContentsMargins(20, 20, 20, 20)
		self.home_layout.setSpacing(10)

		# === 顶部工具栏区域 ===
		tool_bar = QHBoxLayout()
		tool_bar.addWidget(SubtitleLabel("下载列表", self.home_widget))
		tool_bar.addStretch(1)

		tool_bar.addWidget(CaptionLabel("并发", self.home_widget))
		self.concurrent_box = ComboBox(self.home_widget)
		self.concurrent_box.addItems([str(i) for i in range(1, 9)])
		self.concurrent_box.setToolTip("同时下载任务数（推荐 2~3）")
		try:
			current = int(config_manager.get("max_concurrent_downloads", 3) or 3)
		except Exception:
			current = 3
		current = max(1, min(self._max_concurrent_ui, current))
		# Ensure the preset box can display custom values.
		cur_text = str(current)
		try:
			items = [self.concurrent_box.itemText(i) for i in range(self.concurrent_box.count())]
			if cur_text not in items:
				self.concurrent_box.insertItem(0, cur_text)
		except Exception:
			pass
		self.concurrent_box.setCurrentText(str(current))
		self.concurrent_box.currentTextChanged.connect(self.on_concurrent_preset_changed)
		tool_bar.addWidget(self.concurrent_box)

		tool_bar.addWidget(CaptionLabel("自定义", self.home_widget))
		self.concurrent_edit = LineEdit(self.home_widget)
		self.concurrent_edit.setFixedWidth(72)
		self.concurrent_edit.setPlaceholderText("自定义")
		try:
			self.concurrent_edit.setValidator(
				QIntValidator(1, self._max_concurrent_ui, self.concurrent_edit)
			)
		except Exception:
			pass
		self.concurrent_edit.editingFinished.connect(self.on_concurrent_custom_committed)
		self.concurrent_edit.setToolTip("输入正整数并回车/失焦生效")
		tool_bar.addWidget(self.concurrent_edit)

		self.start_all_btn = TransparentToolButton(FluentIcon.PLAY, self)
		self.start_all_btn.setToolTip("全部开始")
		self.start_all_btn.clicked.connect(self.on_start_all)
		tool_bar.addWidget(self.start_all_btn)

		self.pause_all_btn = TransparentToolButton(FluentIcon.PAUSE, self)
		self.pause_all_btn.setToolTip("全部暂停")
		self.pause_all_btn.clicked.connect(self.on_pause_all)
		tool_bar.addWidget(self.pause_all_btn)

		self.clear_all_btn = TransparentToolButton(FluentIcon.DELETE, self)
		self.clear_all_btn.setToolTip("清空所有任务")
		self.clear_all_btn.clicked.connect(self.on_clear_all)
		tool_bar.addWidget(self.clear_all_btn)

		self.clear_completed_btn = TransparentToolButton(FluentIcon.DELETE, self)
		self.clear_completed_btn.setToolTip("清理已完成")
		self.clear_completed_btn.clicked.connect(self.on_clear_completed)
		tool_bar.addWidget(self.clear_completed_btn)

		self.batch_mode_btn = TransparentToolButton(FluentIcon.EDIT, self)
		self.batch_mode_btn.setToolTip("批量选择")
		self.batch_mode_btn.clicked.connect(self.toggle_batch_mode)
		tool_bar.addWidget(self.batch_mode_btn)

		self.select_all_btn = PushButton("全选", self)
		self.select_all_btn.setEnabled(False)
		self.select_all_btn.clicked.connect(self.on_select_all)
		tool_bar.addWidget(self.select_all_btn)

		self.unselect_all_btn = PushButton("全不选", self)
		self.unselect_all_btn.setEnabled(False)
		self.unselect_all_btn.clicked.connect(self.on_unselect_all)
		tool_bar.addWidget(self.unselect_all_btn)

		self.invert_select_btn = PushButton("反选", self)
		self.invert_select_btn.setEnabled(False)
		self.invert_select_btn.clicked.connect(self.on_invert_select)
		tool_bar.addWidget(self.invert_select_btn)

		self.delete_selected_btn = TransparentToolButton(FluentIcon.DELETE, self)
		self.delete_selected_btn.setToolTip("删除所选")
		self.delete_selected_btn.setEnabled(False)
		self.delete_selected_btn.clicked.connect(self.on_delete_selected)
		tool_bar.addWidget(self.delete_selected_btn)

		self.add_btn = PrimaryPushButton(FluentIcon.ADD, "新建任务", self)
		self.add_btn.clicked.connect(self.on_manual_add_clicked)
		tool_bar.addWidget(self.add_btn)

		self.home_layout.addLayout(tool_bar)

		self.scroll_area = QScrollArea(self.home_widget)
		self.scroll_area.setWidgetResizable(True)
		self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
		self.scroll_area.setStyleSheet("background: transparent;")

		self.scroll_content = QWidget()
		self.scroll_layout = QVBoxLayout(self.scroll_content)
		self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
		self.scroll_layout.setSpacing(10)
		self.scroll_layout.setContentsMargins(0, 0, 0, 0)

		# Grouped, collapsible sections by task status
		self._batch_mode = False
		self._sections: dict[str, QWidget] = {}
		self._section_layouts: dict[str, QVBoxLayout] = {}
		self._section_headers: dict[str, SubtitleLabel] = {}
		self._section_collapsed: dict[str, bool] = {}
		self._build_status_sections()

		self.scroll_area.setWidget(self.scroll_content)
		self.home_layout.addWidget(self.scroll_area)

	def _build_status_sections(self) -> None:
		# Order matters
		defs = [
			("running", "下载中"),
			("queued", "排队中"),
			("paused", "已暂停"),
			("completed", "已完成"),
			("error", "出错"),
		]
		for key, title in defs:
			container = QWidget(self.scroll_content)
			v = QVBoxLayout(container)
			v.setContentsMargins(10, 10, 10, 10)
			v.setSpacing(6)

			header = QWidget(container)
			h = QHBoxLayout(header)
			h.setContentsMargins(0, 0, 0, 0)
			h.setSpacing(8)

			lbl = SubtitleLabel(f"{title} (0)", header)
			h.addWidget(lbl)
			h.addStretch(1)
			toggle_btn = TransparentToolButton(FluentIcon.EDIT, header)
			toggle_btn.setToolTip("折叠/展开")
			toggle_btn.clicked.connect(lambda _=False, k=key: self._toggle_section(k))
			h.addWidget(toggle_btn)
			v.addWidget(header)

			content = QWidget(container)
			content_layout = QVBoxLayout(content)
			content_layout.setContentsMargins(0, 0, 0, 0)
			content_layout.setSpacing(10)
			content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
			v.addWidget(content)

			self._sections[key] = content
			self._section_layouts[key] = content_layout
			self._section_headers[key] = lbl
			self._section_collapsed[key] = False
			self.scroll_layout.addWidget(container)

	def _toggle_section(self, key: str) -> None:
		key = str(key or "").strip().lower()
		if key not in self._sections:
			return
		collapsed = not bool(self._section_collapsed.get(key, False))
		self._section_collapsed[key] = collapsed
		self._sections[key].setVisible(not collapsed)

	def _section_count(self, key: str) -> int:
		lay = self._section_layouts.get(key)
		if lay is None:
			return 0
		return sum(1 for i in range(lay.count()) if isinstance(lay.itemAt(i).widget(), DownloadItemCard))

	def _refresh_section_titles(self) -> None:
		names = {
			"running": "下载中",
			"queued": "排队中",
			"paused": "已暂停",
			"completed": "已完成",
			"error": "出错",
		}
		for k, base in names.items():
			lbl = self._section_headers.get(k)
			if lbl is None:
				continue
			lbl.setText(f"{base} ({self._section_count(k)})")

	def _bucket_for_card(self, card: DownloadItemCard) -> str:
		try:
			st = str(card.state() or "queued").lower().strip()
		except Exception:
			st = "queued"
		return st if st in self._section_layouts else "queued"

	def _add_card_to_bucket(self, card: DownloadItemCard) -> None:
		bucket = self._bucket_for_card(card)
		lay = self._section_layouts.get(bucket)
		if lay is None:
			lay = self._section_layouts.get("queued")
			bucket = "queued"
		# Remove from any previous layout
		try:
			card.setParent(None)
		except Exception:
			pass
		lay.addWidget(card)
		self._refresh_section_titles()

	def _on_card_state_changed(self, _state: str) -> None:
		card = self.sender()
		if isinstance(card, DownloadItemCard):
			self._add_card_to_bucket(card)

	def toggle_batch_mode(self) -> None:
		self._batch_mode = not bool(getattr(self, "_batch_mode", False))
		for card in self._get_all_download_cards():
			card.set_selection_mode(self._batch_mode)
		self._update_batch_action_enabled()
		InfoBar.info(
			"批量选择",
			"已开启批量选择（勾选任务后点“删除所选”）" if self._batch_mode else "已关闭批量选择",
			parent=self,
			position=InfoBarPosition.TOP_RIGHT,
		)

	def _selected_count(self) -> int:
		return sum(1 for c in self._get_all_download_cards() if c.is_selected())

	def _update_batch_action_enabled(self) -> None:
		batch = bool(getattr(self, "_batch_mode", False))
		try:
			self.select_all_btn.setEnabled(batch)
			self.unselect_all_btn.setEnabled(batch)
			self.invert_select_btn.setEnabled(batch)
		except Exception:
			pass
		try:
			self.delete_selected_btn.setEnabled(batch and self._selected_count() > 0)
		except Exception:
			pass

	def on_select_all(self) -> None:
		if not bool(getattr(self, "_batch_mode", False)):
			return
		for c in self._get_all_download_cards():
			try:
				c.selectBox.blockSignals(True)
				c.selectBox.setChecked(True)
			finally:
				try:
					c.selectBox.blockSignals(False)
				except Exception:
					pass
		self._update_batch_action_enabled()

	def on_unselect_all(self) -> None:
		if not bool(getattr(self, "_batch_mode", False)):
			return
		for c in self._get_all_download_cards():
			try:
				c.selectBox.blockSignals(True)
				c.selectBox.setChecked(False)
			finally:
				try:
					c.selectBox.blockSignals(False)
				except Exception:
					pass
		self._update_batch_action_enabled()

	def on_invert_select(self) -> None:
		if not bool(getattr(self, "_batch_mode", False)):
			return
		for c in self._get_all_download_cards():
			try:
				c.selectBox.blockSignals(True)
				c.selectBox.setChecked(not bool(c.selectBox.isChecked()))
			finally:
				try:
					c.selectBox.blockSignals(False)
				except Exception:
					pass
		self._update_batch_action_enabled()

	def on_delete_selected(self) -> None:
		cards = [c for c in self._get_all_download_cards() if c.is_selected()]
		if not cards:
			InfoBar.info("删除所选", "未选择任何任务", parent=self, position=InfoBarPosition.TOP_RIGHT)
			self._update_batch_action_enabled()
			return

		logger.debug("on_delete_selected called; selected={}", len(cards))
		self._maybe_prompt_enable_remove_delete_source_feature()
		cache_enabled = bool(config_manager.get("remove_task_ask_delete_cache") or False)
		logger.debug("remove_task_ask_delete_cache={}", cache_enabled)
		if cache_enabled or getattr(self, "_force_delete_popup", False):
			unfinished_cards: list[DownloadItemCard] = []
			for c in cards:
				try:
					st = str(c.state() or "").lower().strip()
				except Exception:
					st = ""
				if st in {"queued", "running", "paused", "error"}:
					unfinished_cards.append(c)
			cache_paths = self._collect_existing_cache_paths(unfinished_cards)
			if cache_paths and self._prompt_delete_cache_files(cache_paths, title="删除缓存文件？"):
				# Stop/remove workers first to release file handles.
				for c in unfinished_cards:
					self._remove_card_and_worker(c)
				self._delete_files_best_effort(cache_paths, success_title="已删除临时文件")
		source_enabled = bool(config_manager.get("remove_task_ask_delete_source") or False)
		logger.debug("remove_task_ask_delete_source={}", source_enabled)
		if source_enabled or getattr(self, "_force_delete_popup", False):
			paths = self._collect_existing_output_paths(cards)
			if paths and self._prompt_delete_source_files(paths, title="删除源文件？"):
				self._delete_files_best_effort(paths, success_title="已删除本地文件")

		for c in cards:
			# Some cards may already be removed above.
			try:
				self._remove_card_and_worker(c)
			except Exception:
				pass
		self._refresh_section_titles()
		self._update_batch_action_enabled()

	def on_clear_completed(self) -> None:
		cards = [c for c in self._get_all_download_cards() if c.state() == "completed"]
		if not cards:
			InfoBar.info("清理已完成", "没有已完成任务", parent=self, position=InfoBarPosition.TOP_RIGHT)
			return

		self._maybe_prompt_enable_remove_delete_source_feature()
		if bool(config_manager.get("remove_task_ask_delete_source") or False):
			paths = self._collect_existing_output_paths(cards)
			if paths and self._prompt_delete_source_files(paths, title="删除已完成的源文件？"):
				self._delete_files_best_effort(paths)

		for c in cards:
			self._remove_card_and_worker(c)
		self._refresh_section_titles()
		self._update_batch_action_enabled()

	def show_selection_dialog(self, url: str) -> None:
		# 避免重复弹出多个对话框
		if getattr(self, "_selection_dialog", None) is not None:
			try:
				if self._selection_dialog.isVisible():
					return
			except Exception:
				pass

		dialog = SelectionDialog(url, self)
		self._selection_dialog = dialog
		try:
			if dialog.exec():
				# Prefer new multi-task API (playlist)
				tasks = []
				try:
					tasks = dialog.get_download_tasks()
				except Exception:
					tasks = []

				if not tasks:
					# Backward compatibility (single)
					opts = dialog.get_download_options()
					title = "未命名任务"
					if dialog.video_info:
						title = str(dialog.video_info.get("title") or title)
						thumb_url = dialog.video_info.get("thumbnail")
					else:
						thumb_url = None
					tasks = [{"url": url, "title": title, "thumbnail": thumb_url, "opts": opts}]

				added = 0
				first_title = None
				for t in tasks:
					t_url = str(t.get("url") or "").strip()
					t_opts = t.get("opts") if isinstance(t.get("opts"), dict) else {}
					t_title = str(t.get("title") or "未命名任务")
					t_thumb = t.get("thumbnail")
					if not t_url:
						continue
					worker = download_manager.create_worker(t_url, t_opts)
					try:
						worker.error.connect(self.on_worker_error)
					except Exception:
						pass
					card = DownloadItemCard(worker, t_title, t_opts, parent=self.scroll_content)
					try:
						card.state_changed.connect(self._on_card_state_changed)
					except Exception:
						pass
					try:
						card.selection_changed.connect(lambda _=False: self._update_batch_action_enabled())
					except Exception:
						pass
					try:
						card.set_selection_mode(bool(getattr(self, "_batch_mode", False)))
					except Exception:
						pass
					if t_thumb:
						card.load_thumbnail(str(t_thumb))
					card.remove_requested.connect(self.on_remove_card)
					started = download_manager.start_worker(worker)
					if not started:
						try:
							card.statusLabel.setText("排队中...")
						except Exception:
							pass
						try:
							card.set_state("queued")
						except Exception:
							pass
					else:
						try:
							card.set_state("running")
						except Exception:
							pass
					self._add_card_to_bucket(card)
					added += 1
					if first_title is None:
						first_title = t_title

				if added > 0:
					self.switchTo(self.home_widget)
					msg = f"已添加 {added} 个任务" if added > 1 else f"任务已添加: {first_title or ''}"
					self.tray_icon.showMessage(
						"开始下载",
						msg,
						QSystemTrayIcon.Information,
						2000,
					)
			else:
				logger.info("用户取消下载")
		finally:
			self._selection_dialog = None

	def on_manual_add_clicked(self) -> None:
		"""新建任务：切换到解析页"""
		self.switchTo(self.parse_page)

	def on_pause_all(self) -> None:
		"""全部暂停"""
		download_manager.stop_all()
		for i in range(self.scroll_layout.count()):
			item = self.scroll_layout.itemAt(i)
			widget = item.widget() if item else None
			if isinstance(widget, DownloadItemCard):
				if widget.worker.isRunning():
					widget.on_action_clicked()

	def on_start_all(self) -> None:
		"""全部开始/继续（会重建已停止的 worker 以断点续传）"""
		for i in range(self.scroll_layout.count()):
			item = self.scroll_layout.itemAt(i)
			widget = item.widget() if item else None
			if isinstance(widget, DownloadItemCard):
				# 仅恢复“未运行且按钮可用”的任务（完成态 actionBtn 会被禁用）
				if (not widget.worker.isRunning()) and widget.actionBtn.isEnabled():
					widget.on_action_clicked()

	def on_clear_all(self) -> None:
		"""全部删除"""
		cards = self._get_all_download_cards()
		if not cards:
			return

		# First-use: ask whether to enable the feature (if disabled).
		logger.debug("on_clear_all called; total_cards={}", len(cards))
		self._maybe_prompt_enable_remove_delete_source_feature()

		# If enabled, prompt once for deleting cache/temp files of paused tasks.
		cache_enabled = bool(config_manager.get("remove_task_ask_delete_cache") or False)
		logger.debug("remove_task_ask_delete_cache={}", cache_enabled)
		if cache_enabled or getattr(self, "_force_delete_popup", False):
			unfinished_cards: list[DownloadItemCard] = []
			for c in cards:
				try:
					st = str(c.state() or "").lower().strip()
				except Exception:
					st = ""
				if st in {"queued", "running", "paused", "error"}:
					unfinished_cards.append(c)
			cache_paths = self._collect_existing_cache_paths(unfinished_cards)
			if cache_paths and self._prompt_delete_cache_files(cache_paths, title="删除缓存文件？"):
				# Stop/remove workers first to release file handles.
				for c in unfinished_cards:
					self._remove_card_and_worker(c)
				self._delete_files_best_effort(cache_paths, success_title="已删除临时文件")

		# If enabled, prompt once for deleting existing output files.
		source_enabled = bool(config_manager.get("remove_task_ask_delete_source") or False)
		logger.debug("remove_task_ask_delete_source={}", source_enabled)
		if source_enabled or getattr(self, "_force_delete_popup", False):
			paths = self._collect_existing_output_paths(cards)
			if paths:
				if self._prompt_delete_source_files(paths, title="删除源文件？"):
					self._delete_files_best_effort(paths, success_title="已删除本地文件")

		# Remove all cards and workers.
		for card in cards:
			try:
				self._remove_card_and_worker(card)
			except Exception:
				pass
		self._refresh_section_titles()
		self._update_batch_action_enabled()

	def on_remove_card(self, card_widget: QWidget) -> None:
		"""响应卡片的删除请求"""
		card = card_widget if isinstance(card_widget, DownloadItemCard) else None
		if card is None:
			try:
				self.scroll_layout.removeWidget(card_widget)
			except Exception:
				pass
			try:
				card_widget.deleteLater()
			except Exception:
				pass
			return

		# First-use: ask whether to enable the feature (if disabled).
		self._maybe_prompt_enable_remove_delete_source_feature()

		# Unfinished task: optionally prompt to delete cache/temp files.
		try:
			st = str(card.state() or "").lower().strip()
		except Exception:
			st = ""
		
		# 1. Cache Deletion Logic (for unfinished tasks)
		if st in {"queued", "running", "paused", "error"} and (bool(config_manager.get("remove_task_ask_delete_cache") or False) or getattr(self, "_force_delete_popup", False)):
			cache_paths = self._collect_existing_cache_paths([card])
			if cache_paths and self._prompt_delete_cache_files(cache_paths, title="删除缓存文件？"):
				# Stop/remove worker first to release file handles.
				self._remove_card_and_worker(card)
				self._delete_files_best_effort(cache_paths, success_title="已删除临时文件")
				self._refresh_section_titles()
				self._update_batch_action_enabled()
				return

		# 2. Source File Deletion Logic (for any task, if enabled)
		if bool(config_manager.get("remove_task_ask_delete_source") or False):
			paths = self._collect_existing_output_paths([card])
			if paths:
				if self._prompt_delete_source_files(paths, title="删除源文件？"):
					self._delete_files_best_effort(paths, success_title="已删除本地文件")

		self._remove_card_and_worker(card)
		self._refresh_section_titles()
		self._update_batch_action_enabled()
		logger.info("================ [Debug: End] ================")

	def _get_all_download_cards(self) -> list[DownloadItemCard]:
		cards: list[DownloadItemCard] = []
		for k, lay in self._section_layouts.items():
			for i in range(lay.count()):
				w = lay.itemAt(i).widget()
				if isinstance(w, DownloadItemCard):
					cards.append(w)
		return cards

	def _card_output_path(self, card: DownloadItemCard) -> str | None:
		p = getattr(card, "_output_path", None) or getattr(card.worker, "output_path", None)
		if isinstance(p, str):
			p = p.strip()
			return p or None
		return None

	def _collect_existing_output_paths(self, cards: Iterable[DownloadItemCard]) -> list[str]:
		paths: list[str] = []
		seen: set[str] = set()
		for card in cards:
			p = self._card_output_path(card)
			if not p:
				continue
			try:
				pp = str(Path(p).resolve())
			except Exception:
				pp = os.path.abspath(p)
			if pp in seen:
				continue
			if os.path.isfile(pp):
				seen.add(pp)
				paths.append(pp)
		return paths

	def _collect_existing_cache_paths(self, cards: Iterable[DownloadItemCard]) -> list[str]:
		"""Collect yt-dlp cache/temp files for paused tasks (best-effort).

		We only delete known sidecar/temp files next to the destination path:
		- <dest>.part, <dest>.ytdl, <dest>.tmp, <dest>.temp, <dest>.aria2
		- and <dest> itself if it exists (some setups may not use .part)
		"""

		# Step1: collect base destination paths from worker/card.
		bases: list[str] = []
		for card in cards:
			try:
				if str(card.state() or "").lower().strip() != "paused":
					continue
			except Exception:
				continue

			# Prefer all destinations observed from yt-dlp output.
			dest_paths = getattr(card.worker, "dest_paths", None)
			if isinstance(dest_paths, (set, list, tuple)):
				for p in dest_paths:
					if isinstance(p, str) and p.strip():
						bases.append(p.strip())

			# Fallbacks
			p = self._card_output_path(card)
			if not p:
				raw = getattr(card.worker, "output_path", None)
				if isinstance(raw, str) and raw.strip():
					p = raw.strip()
			if p:
				bases.append(p)

		# Step2: expand to concrete cache/temp files that actually exist.
		paths: list[str] = []
		seen: set[str] = set()
		for p in bases:
			try:
				base = str(Path(p).resolve())
			except Exception:
				base = os.path.abspath(p)
			if not base:
				continue

			# Always consider the base itself. Destination may already be a temp file like *.mp4.part.
			if base not in seen:
				seen.add(base)
				if os.path.isfile(base):
					paths.append(base)

			# Normalize: if base name contains '.part' (e.g. *.mp4.part or *.mp4.part-Frag123),
			# derive the root (e.g. *.mp4) so we can find sidecars like *.mp4.ytdl.
			dir_path = os.path.dirname(base)
			base_name = os.path.basename(base)
			root = base
			try:
				if ".part" in base_name:
					root_name = base_name.split(".part", 1)[0]
					if root_name:
						root = os.path.join(dir_path, root_name)
			except Exception:
				root = base

			# Sidecars for both base and root (common)
			for anchor in {base, root}:
				for ext in (".ytdl", ".tmp", ".temp", ".aria2"):
					c = anchor + ext
					if c not in seen:
						seen.add(c)
						if os.path.isfile(c):
							paths.append(c)

			# .part can have suffixes (e.g. .part-Frag123), so scan directory.
			try:
				if dir_path and os.path.isdir(dir_path):
					# Prefer matching by root basename (e.g. *.mp4.part*), fall back to base name.
					root_name = os.path.basename(root) or ""
					name_candidates = [n for n in (root_name, base_name) if n]
					for name in name_candidates:
						prefix = name + ".part"
						for fn in os.listdir(dir_path):
							if not isinstance(fn, str):
								continue
							if fn == name or fn.startswith(prefix):
								full = os.path.join(dir_path, fn)
								if full not in seen:
									seen.add(full)
									if os.path.isfile(full):
										paths.append(full)
			except Exception:
				pass

		return paths

	def _maybe_prompt_enable_remove_delete_source_feature(self) -> None:
		# Feature already enabled => no need to ask.
		if bool(config_manager.get("remove_task_ask_delete_source") or False):
			return
		# Prompt disabled via settings or prior "不再询问" choice.
		if not bool(config_manager.get("remove_task_ask_enable_feature") or False):
			return

		box = MessageBoxBase(self)
		box.viewLayout.addWidget(SubtitleLabel("提示", box))
		box.viewLayout.addWidget(
			CaptionLabel(
				"检测到你正在删除下载列表中的任务。\n\n"
				"是否开启：删除任务时询问是否同时删除已下载文件？\n"
				"（可在 设置 → 体验 中随时修改）",
				box,
			)
		)
		cb = QCheckBox("不再询问", box)
		cb.setTristate(False)
		box.viewLayout.addWidget(cb)
		box.yesButton.setText("开启")
		box.cancelButton.setText("关闭")

		enabled_now = bool(box.exec())
		if enabled_now:
			config_manager.set("remove_task_ask_delete_source", True)
		if cb.isChecked():
			config_manager.set("remove_task_ask_enable_feature", False)

	def _prompt_delete_source_files(self, paths: list[str], title: str = "删除源文件？") -> bool:
		if not paths:
			return False
		count = len(paths)
		preview = "\n".join(paths[:3])
		more = "" if count <= 3 else f"\n... 以及另外 {count - 3} 个文件"
		box = MessageBox(
			title,
			(
				f"将从磁盘删除 {count} 个已下载文件（不可恢复）：\n\n"
				f"{preview}{more}\n\n"
				"是否继续？"
			),
			parent=self,
		)
		box.yesButton.setText("删除文件")
		box.cancelButton.setText("仅移除列表")
		return bool(box.exec())

	def _prompt_delete_cache_files(self, paths: list[str], title: str = "删除临时文件？") -> bool:
		if not paths:
			return False
		count = len(paths)
		preview = "\n".join(paths[:3])
		more = "" if count <= 3 else f"\n... 以及另外 {count - 3} 个文件"
		box = MessageBox(
			title,
			(
				"检测到未完成任务可能存在临时文件（例如 .part / .ytdl）。\n\n"
				f"将从磁盘删除 {count} 个文件（不可恢复）：\n\n"
				f"{preview}{more}\n\n"
				"是否继续？"
			),
			parent=self,
		)
		box.yesButton.setText("删除临时文件")
		box.cancelButton.setText("仅移除列表")
		return bool(box.exec())

	def _delete_files_best_effort(self, paths: list[str], success_title: str = "已删除文件") -> None:
		ok = 0
		failed: list[str] = []
		for p in paths:
			try:
				logger.debug("attempt delete file=%s exists=%s", p, os.path.exists(p))
			except Exception:
				logger.debug("attempt delete file=%s (exists unknown)", p)
			try:
				Path(p).unlink(missing_ok=True)
				ok += 1
				logger.debug("deleted file=%s success", p)
			except TypeError:
				# Fallback for older Python where missing_ok may not exist.
				try:
					if os.path.exists(p):
						Path(p).unlink()
					ok += 1
					logger.debug("deleted file=%s success (fallback)", p)
				except Exception as e:
					failed.append(p)
					logger.exception("failed delete file=%s", p)
			except Exception as e:
				failed.append(p)
				logger.exception("failed delete file=%s", p)

		if ok:
			InfoBar.success(
				success_title,
				f"成功删除 {ok} 个文件" + (f"，失败 {len(failed)} 个" if failed else ""),
				parent=self,
				position=InfoBarPosition.TOP_RIGHT,
			)
		elif failed:
			InfoBar.error(
				"删除失败",
				"无法删除文件，请检查是否被占用/权限不足。",
				parent=self,
				position=InfoBarPosition.TOP_RIGHT,
			)

	def _remove_card_and_worker(self, card: DownloadItemCard) -> None:
		try:
			if card.worker.isRunning():
				card.worker.stop()
		except Exception:
			pass
		try:
			download_manager.remove_worker(card.worker)
		except Exception:
			pass
		# Remove from whichever section layout currently holds it.
		try:
			for lay in self._section_layouts.values():
				try:
					lay.removeWidget(card)
				except Exception:
					pass
		except Exception:
			pass
		try:
			card.deleteLater()
		except Exception:
			pass

	def _apply_concurrency(self, n: int) -> None:
		if getattr(self, "_updating_concurrent", False):
			return
		n = max(1, min(self._max_concurrent_ui, int(n)))
		try:
			old = int(config_manager.get("max_concurrent_downloads", 3) or 3)
		except Exception:
			old = 3
		old = max(1, min(self._max_concurrent_ui, old))

		# Warn only when crossing above 3.
		if old <= 3 and n > 3:
			box = MessageBox(
				"并发过高警告",
				(
					f"你将同时下载数量设置为 {n}。\n\n"
					"这会让程序同时启动更多下载线程/网络连接（以及可能的后处理/合并任务），"
					"常见风险包括：\n"
					"- CPU/磁盘占用飙升，导致界面卡顿或系统变慢\n"
					"- 网络拥塞/丢包，反而更慢，甚至更容易失败重试\n"
					"- 触发站点限速/风控，出现速度骤降或频繁报错\n\n"
					"建议：日常 2~3；网络/磁盘较强可尝试 4~6；不建议长期 >8。\n\n"
					"是否继续？"
				),
				parent=self,
			)
			box.yesButton.setText("继续")
			box.cancelButton.setText("改回 3")
			if not box.exec():
				n = 3

		config_manager.set("max_concurrent_downloads", n)
		self._updating_concurrent = True
		try:
			# Ensure the preset box can display custom values.
			text_n = str(n)
			try:
				items = [self.concurrent_box.itemText(i) for i in range(self.concurrent_box.count())]
				if text_n not in items:
					self.concurrent_box.insertItem(0, text_n)
			except Exception:
				pass
			self.concurrent_box.setCurrentText(str(n))
			try:
				self.concurrent_edit.setText("")
			except Exception:
				pass
		finally:
			self._updating_concurrent = False
		download_manager.pump()

	def on_concurrent_preset_changed(self, text: str) -> None:
		if getattr(self, "_updating_concurrent", False):
			return
		text = str(text or "").strip()
		if not text.isdigit():
			return
		try:
			n = int(text)
		except Exception:
			return
		self._apply_concurrency(n)

	def on_concurrent_custom_committed(self) -> None:
		if getattr(self, "_updating_concurrent", False):
			return
		text = ""
		try:
			text = str(self.concurrent_edit.text() or "").strip()
		except Exception:
			return
		if not text or not text.isdigit():
			return
		try:
			n = int(text)
		except Exception:
			return
		self._apply_concurrency(n)

	def on_worker_error(self, err_data: dict) -> None:
		"""统一处理 Worker 发来的结构化错误信息，并提供“复制诊断信息”。"""

		title = str(err_data.get("title") or "错误")
		content = str(err_data.get("content") or "发生未知错误")
		suggestion = str(err_data.get("suggestion") or "")
		raw_error = str(err_data.get("raw_error") or "")

		dialog_content = content
		if suggestion:
			dialog_content += f"\n\n建议操作：\n{suggestion}"

		w = MessageDialog(title, dialog_content, self)
		w.yesButton.setText("确定")
		w.cancelButton.setText("复制诊断信息")

		if w.exec():
			return

		try:
			from PySide6.QtGui import QGuiApplication
			from fluentytdl.utils.logger import LOG_DIR
		except Exception:
			QGuiApplication = None  # type: ignore[assignment]
			LOG_DIR = ""

		try:
			clipboard = QGuiApplication.clipboard() if QGuiApplication is not None else None
			if clipboard is not None:
				log_text = (
					"=== FluentYTDL Error Report ===\n"
					f"Title: {title}\n"
					f"Message: {content}\n"
					f"Suggestion: {suggestion}\n"
					f"Raw Error: {raw_error}\n"
					f"Log Dir: {LOG_DIR}\n"
					"==============================="
				)
				clipboard.setText(log_text)
				InfoBar.success(
					"已复制",
					"诊断信息已复制到剪贴板",
					parent=self,
					position=InfoBarPosition.TOP_RIGHT,
				)
		except Exception:
			pass

	def closeEvent(self, event) -> None:
		"""重写关闭事件：有任务则提示确认，否则直接退出。"""

		try:
			has_tasks = bool(download_manager.has_active_tasks())
		except Exception:
			has_tasks = False

		if has_tasks:
			w = MessageBox(
				"确认退出",
				"当前有正在下载或排队中的任务。\n\n退出将取消并停止所有任务，且不会在后台继续下载。\n\n确定要退出吗？",
				self,
			)
			w.yesButton.setText("退出")
			w.cancelButton.setText("取消")
			if not w.exec():
				event.ignore()
				return

		# No tasks (or user confirmed): exit.
		event.accept()
		self.quit_app()

	def quit_app(self) -> None:
		"""彻底退出：停止下载任务并确保无后台残留。"""

		# 1) stop clipboard monitor
		try:
			self.set_clipboard_monitor_enabled(False)
		except Exception:
			pass

		# 2) stop queued/running downloads
		all_stopped = True
		try:
			all_stopped = bool(download_manager.shutdown(grace_ms=2500))
		except Exception:
			all_stopped = False

		# 3) hide tray icon so Qt can exit cleanly
		try:
			self.tray_icon.hide()
			self.tray_icon.setContextMenu(None)
			self.tray_icon.deleteLater()
		except Exception:
			pass

		# 4) quit Qt loop
		QApplication.quit()

		# 5) last resort: ensure process exits (avoid “窗口关了但进程还在”)
		if not all_stopped:
			try:
				from PySide6.QtCore import QTimer
				import os

				QTimer.singleShot(3000, lambda: os._exit(0))
			except Exception:
				pass
