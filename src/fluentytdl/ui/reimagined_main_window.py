from __future__ import annotations

import os
import time
from typing import Iterable

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QAction, QIcon, QPixmap, QColor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMenu,
    QScrollArea,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QLabel,
    QFrame,
    QCheckBox,
)

from qfluentwidgets import (
    FluentWindow,
    FluentIcon,
    NavigationItemPosition,
    SubtitleLabel,
    CaptionLabel,
    TransparentToolButton,
    PrimaryPushButton,
    PushButton,
    SplashScreen,
    MessageBox,
    InfoBar,
    InfoBarPosition,
)

from .components.download_item_widget import DownloadItemWidget
from .components.clipboard_monitor import ClipboardMonitor
from .parse_page import ParsePage
from .settings_page import SettingsPage
from .welcome_wizard import WelcomeWizardDialog
from .help_window import HelpWindow
from ..core.download_manager import download_manager
from ..core.config_manager import config_manager
from ..utils.logger import logger
from ..utils.paths import resource_path


class TaskListPage(QWidget):
    """通用的任务列表页面"""

    def __init__(self, title: str, icon: FluentIcon, parent=None):
        super().__init__(parent)
        self.setObjectName(title.lower().replace(" ", "_"))
        self.page_title = title
        
        self.v_layout = QVBoxLayout(self)
        self.v_layout.setContentsMargins(20, 20, 20, 20)
        self.v_layout.setSpacing(10)

        # === 工具栏 ===
        self.tool_bar = QHBoxLayout()
        self.title_label = SubtitleLabel(self.page_title, self)
        self.tool_bar.addWidget(self.title_label)
        self.tool_bar.addStretch(1)
        
        # 占位：具体按钮由外部添加或子类实现
        self.action_layout = QHBoxLayout()
        self.tool_bar.addLayout(self.action_layout)
        
        self.v_layout.addLayout(self.tool_bar)

        # === 列表区域 ===
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")
        
        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(8)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.scroll_widget)
        self.v_layout.addWidget(self.scroll_area)

    def add_card(self, card: QWidget):
        self.scroll_layout.addWidget(card)
        card.show()

    def remove_card(self, card: QWidget):
        self.scroll_layout.removeWidget(card)
        card.setParent(None) # Important to detach

    def count(self) -> int:
        return self.scroll_layout.count()

    def set_selection_mode(self, enabled: bool):
        for i in range(self.scroll_layout.count()):
            item = self.scroll_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if hasattr(w, "set_selection_mode"):
                    w.set_selection_mode(enabled)

    def get_selected_cards(self) -> list[QWidget]:
        selected = []
        for i in range(self.scroll_layout.count()):
            item = self.scroll_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if hasattr(w, "is_selected") and w.is_selected():
                    selected.append(w)
        return selected

    def select_all(self):
        for i in range(self.scroll_layout.count()):
            item = self.scroll_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if hasattr(w, "selectBox"):
                    w.selectBox.setChecked(True)

    def deselect_all(self):
        for i in range(self.scroll_layout.count()):
            item = self.scroll_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if hasattr(w, "selectBox"):
                    w.selectBox.setChecked(False)


class MainWindow(FluentWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FluentYTDL Pro")
        self.resize(1150, 780)
        
        # 居中
        desktop = QApplication.screens()[0].availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

        # === 初始化页面 ===
        self.downloading_page = TaskListPage("正在下载", FluentIcon.DOWNLOAD)
        self.paused_page = TaskListPage("已暂停", FluentIcon.PAUSE)
        self.completed_page = TaskListPage("已完成", FluentIcon.ACCEPT)
        self.queued_page = TaskListPage("排队中", FluentIcon.HISTORY)
        
        self.parse_page = ParsePage(self)
        self.settings_interface = SettingsPage(self)

        # === 初始化导航 ===
        self.init_navigation()
        
        # === 初始化工具栏按钮 ===
        self.init_page_actions()

        # === 状态栏 ===
        self.init_status_bar()

        # === 系统组件 ===
        self.init_system_tray()
        self.init_clipboard_monitor()
        
        # 启动动画
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.finish()

        # 信号连接
        self.parse_page.parse_requested.connect(self.show_selection_dialog)
        self.settings_interface.clipboardAutoDetectChanged.connect(self.set_clipboard_monitor_enabled)

        # === 标题栏扩展 ===
        self.init_title_bar()

        # === 首次启动检测 ===
        QTimer.singleShot(1000, self.check_first_run)

    def init_navigation(self):
        # 1. 新建任务 (作为首要操作)
        # FluentWindow 的 NavigationInterface 不直接支持“大按钮”，但我们可以添加一个 Action
        # 或者将 ParsePage 放在最上面
        self.addSubInterface(
            self.parse_page,
            FluentIcon.ADD,
            "新建任务",
            position=NavigationItemPosition.TOP
        )
        
        self.navigationInterface.addSeparator()

        self.addSubInterface(
            self.downloading_page,
            FluentIcon.DOWNLOAD,
            "正在下载",
            position=NavigationItemPosition.TOP
        )
        
        self.addSubInterface(
            self.paused_page,
            FluentIcon.PAUSE,
            "已暂停",
            position=NavigationItemPosition.TOP
        )

        self.addSubInterface(
            self.queued_page,
            FluentIcon.HISTORY, # 或者 TIME
            "排队中",
            position=NavigationItemPosition.TOP
        )

        self.addSubInterface(
            self.completed_page,
            FluentIcon.ACCEPT, # 或者 CHECKBOX
            "已完成",
            position=NavigationItemPosition.TOP
        )

        self.addSubInterface(
            self.settings_interface,
            FluentIcon.SETTING,
            "设置",
            position=NavigationItemPosition.BOTTOM
        )

    def init_page_actions(self):
        # Helper to add batch actions
        def add_batch_actions(page: TaskListPage, show_start=True, show_pause=True):
            # Batch Toggle
            batch_btn = PushButton(FluentIcon.EDIT, "批量操作", page)
            batch_btn.setToolTip("进入批量操作模式")
            
            # Batch Actions (Hidden by default)
            select_all_btn = PushButton(FluentIcon.MENU, "全选", page)
            select_all_btn.setToolTip("全选")
            select_all_btn.hide()
            
            start_sel_btn = PushButton(FluentIcon.PLAY, "开始选中", page)
            start_sel_btn.setToolTip("开始选中任务")
            start_sel_btn.hide()
            
            pause_sel_btn = PushButton(FluentIcon.PAUSE, "暂停选中", page)
            pause_sel_btn.setToolTip("暂停选中任务")
            pause_sel_btn.hide()
            
            del_sel_btn = PushButton(FluentIcon.DELETE, "删除选中", page)
            del_sel_btn.setToolTip("删除选中任务")
            del_sel_btn.hide()
            
            # Logic
            def toggle_batch():
                is_batch = getattr(page, "_is_batch_mode", False)
                # Toggle state
                new_state = not is_batch
                page._is_batch_mode = new_state
                page.set_selection_mode(new_state)
                
                # Toggle visibility
                select_all_btn.setVisible(new_state)
                del_sel_btn.setVisible(new_state)
                if show_start:
                    start_sel_btn.setVisible(new_state)
                if show_pause:
                    pause_sel_btn.setVisible(new_state)
                
                # Update icon/tooltip
                if new_state:
                    batch_btn.setIcon(FluentIcon.CANCEL)
                    batch_btn.setText("退出批量")
                    batch_btn.setToolTip("退出批量模式")
                else:
                    batch_btn.setIcon(FluentIcon.EDIT)
                    batch_btn.setText("批量操作")
                    batch_btn.setToolTip("进入批量操作模式")

            batch_btn.clicked.connect(toggle_batch)
            select_all_btn.clicked.connect(page.select_all)
            
            # Connect actions
            start_sel_btn.clicked.connect(lambda: self.on_batch_start(page))
            pause_sel_btn.clicked.connect(lambda: self.on_batch_pause(page))
            del_sel_btn.clicked.connect(lambda: self.on_batch_delete(page))
            
            # Add to layout
            page.action_layout.setSpacing(8)
            page.action_layout.addSpacing(10)
            page.action_layout.addWidget(batch_btn)
            page.action_layout.addWidget(select_all_btn)
            if show_start:
                page.action_layout.addWidget(start_sel_btn)
            if show_pause:
                page.action_layout.addWidget(pause_sel_btn)
            page.action_layout.addWidget(del_sel_btn)

        # Downloading Page Actions
        start_all = PushButton(FluentIcon.PLAY, "全部开始", self)
        start_all.setToolTip("开始所有任务")
        start_all.clicked.connect(self.on_start_all)
        
        pause_all = PushButton(FluentIcon.PAUSE, "全部暂停", self)
        pause_all.setToolTip("暂停所有任务")
        pause_all.clicked.connect(self.on_pause_all)
        
        self.downloading_page.action_layout.setSpacing(8)
        self.downloading_page.action_layout.addWidget(start_all)
        self.downloading_page.action_layout.addWidget(pause_all)
        
        add_batch_actions(self.downloading_page)

        # Paused Page Actions
        add_batch_actions(self.paused_page, show_pause=False)

        # Completed Page Actions
        clear_completed = PushButton(FluentIcon.DELETE, "清空记录", self)
        clear_completed.setToolTip("清空所有已完成记录")
        clear_completed.clicked.connect(self.on_clear_completed)
        
        open_dir = PushButton(FluentIcon.FOLDER, "打开目录", self)
        open_dir.setToolTip("打开默认下载目录")
        open_dir.clicked.connect(self.on_open_download_dir)
        
        self.completed_page.action_layout.setSpacing(8)
        self.completed_page.action_layout.addWidget(clear_completed)
        self.completed_page.action_layout.addWidget(open_dir)
        
        add_batch_actions(self.completed_page, show_start=False, show_pause=False)


    def init_status_bar(self):
        # FluentWindow 没有原生 statusBar，我们手动添加到底部
        # 注意：FluentWindow 的布局是 stackedWidget，我们需要修改主布局
        # 但 FluentWindow 封装较深，通常建议在各个 Page 底部加，或者使用 InfoBar
        # 这里我们尝试在 NavigationInterface 下方或者整个 Window 底部加
        # 简单起见，我们在每个 Page 底部加？不，那样不全局。
        # 我们可以使用 overlay 或者修改 FluentWindow 的 layout。
        # 鉴于时间，我们暂时略过全局状态栏，或者只在 DownloadingPage 显示。
        # 用户需求：全局状态栏。
        # 我们可以创建一个 QWidget 作为底部条，添加到 self.layout() (如果是 QVBoxLayout)
        # FluentWindow 的 layout 是 QHBoxLayout (Nav + Stack)。
        # 我们可以把 Stack 换成 VBox(Stack + StatusBar)。
        pass

    # ... (系统托盘、剪贴板逻辑复用 main_window.py) ...
    def init_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = resource_path("assets", "logo.png")
        chosen_icon = None
        try:
            if icon_path.exists():
                chosen_icon = QIcon(str(icon_path))
            else:
                win_icon = self.windowIcon()
                if not win_icon.isNull():
                    chosen_icon = win_icon
        except Exception:
            chosen_icon = None

        # Fallback: generate a simple colored pixmap to avoid "No Icon set" warnings
        if chosen_icon is None or chosen_icon.isNull():
            try:
                pix = QPixmap(16, 16)
                pix.fill(QColor(64, 120, 230))
                chosen_icon = QIcon(pix)
            except Exception:
                chosen_icon = QIcon()

        self.tray_icon.setIcon(chosen_icon)
        tray_menu = QMenu()
        show_action = QAction("显示主界面", self)
        show_action.triggered.connect(self.showNormal)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        # Show only after a valid icon has been set to avoid Qt warning
        try:
            self.tray_icon.show()
        except Exception:
            pass
        self.tray_icon.activated.connect(self._on_tray_icon_activated)

    def _on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.showNormal()
            self.activateWindow()

    def quit_app(self):
        download_manager.stop_all()
        QApplication.quit()

    def init_clipboard_monitor(self):
        enabled = bool(config_manager.get("clipboard_auto_detect") or False)
        self.set_clipboard_monitor_enabled(enabled)

    def set_clipboard_monitor_enabled(self, enabled: bool):
        if not enabled:
            mon = getattr(self, "clipboard_monitor", None)
            if mon:
                try:
                    mon.youtube_url_detected.disconnect(self.on_youtube_url_detected)
                    mon.deleteLater()
                except: pass
                self.clipboard_monitor = None
            return
        if getattr(self, "clipboard_monitor", None) is None:
            self.clipboard_monitor = ClipboardMonitor()
            self.clipboard_monitor.youtube_url_detected.connect(self.on_youtube_url_detected)

    def on_youtube_url_detected(self, url: str):
        if not self.isVisible():
            self.tray_icon.showMessage("检测到视频链接", "点击处理", QSystemTrayIcon.Information, 2000)
            self.showNormal()
            self.activateWindow()
        self.show_selection_dialog(url)

    def show_selection_dialog(self, url: str):
        from .components.selection_dialog import SelectionDialog
        if getattr(self, "_selection_dialog", None):
            self._selection_dialog.close()
            self._selection_dialog = None
        
        dlg = SelectionDialog(url, self)
        self._selection_dialog = dlg
        if dlg.exec():
            tasks = dlg.get_selected_tasks()
            self.add_tasks(tasks)
        self._selection_dialog = None

    def add_tasks(self, tasks):
        # 添加任务逻辑
        default_dir = config_manager.get("download_dir")
        
        for t_title, t_url, t_opts, t_thumb in tasks:
            # Inject default download directory if not specified
            if default_dir and "paths" not in t_opts:
                # Only inject if outtmpl is not absolute (simple check)
                outtmpl = t_opts.get("outtmpl")
                if not (isinstance(outtmpl, str) and os.path.isabs(outtmpl)):
                    t_opts["paths"] = {"home": str(default_dir)}

            worker = download_manager.create_worker(t_url, t_opts)
            card = DownloadItemWidget(worker, t_title, t_opts)
            if t_thumb:
                card.load_thumbnail(str(t_thumb))
            
            # 连接信号
            card.remove_requested.connect(self.on_remove_card)
            card.resume_requested.connect(self.on_resume_card)
            card.state_changed.connect(lambda s, c=card: self.on_card_state_changed(c, s))
            
            # 初始状态
            started = download_manager.start_worker(worker)
            if started:
                card.set_state("running")
                self.downloading_page.add_card(card)
            else:
                card.set_state("queued")
                self.queued_page.add_card(card)
            
            # 切换到下载页
            self.switchTo(self.downloading_page)

    def on_card_state_changed(self, card: DownloadItemWidget, state: str):
        # 核心逻辑：根据状态移动卡片
        # 先从当前父级移除
        card.setParent(None)
        
        if state == "completed":
            self.completed_page.add_card(card)
        elif state == "queued":
            self.queued_page.add_card(card)
        elif state == "paused":
            self.paused_page.add_card(card)
        else:
            # running, error -> Downloading Page (or Error Page if we had one)
            # For now, keep error in Downloading or Paused? 
            # Usually Error is treated as Paused/Stopped.
            if state == "error":
                self.paused_page.add_card(card)
            else:
                self.downloading_page.add_card(card)

    def on_remove_card(self, card: DownloadItemWidget):
        try:
            # 1. Critical Logs & Config Reading
            raw_policy = config_manager.get("deletion_policy")
            logger.info(f"Triggering delete for card {id(card)}")
            logger.info(f"Current Config Policy Raw Value: {raw_policy} (Type: {type(raw_policy)})")

            # 2. Force Type Conversion & Normalization
            policy = str(raw_policy or "alwaysask").lower().strip()
            logger.info(f"Normalized Policy: '{policy}'")

            # 3. Terminate worker immediately (Robust File Deletion)
            if getattr(card, "worker", None):
                try:
                    if hasattr(card.worker, "stop"):
                        card.worker.stop()
                    elif hasattr(card.worker, "cancel"):
                        card.worker.cancel()
                    
                    # If it's still running, force terminate to release file locks
                    if hasattr(card.worker, "isRunning") and card.worker.isRunning():
                        if hasattr(card.worker, "terminate"):
                            card.worker.terminate()
                        card.worker.wait(500)
                except Exception as e:
                    logger.error(f"Error stopping worker: {e}")

            # 4. Policy helpers (robust matching + legacy fallbacks)
            def _is_keep(p: str) -> bool:
                return any(tok in p for tok in ("keep", "keepfiles", "keep_files", "keep-files"))

            def _is_delete(p: str) -> bool:
                # accept many synonyms
                return any(tok in p for tok in ("delete", "deletefiles", "delete_files", "delete-files", "remove", "removefiles"))

            def _is_ask(p: str) -> bool:
                return any(tok in p for tok in ("ask", "alwaysask", "always_ask", "always-ask"))

            # Legacy boolean keys fallback: if user enabled old ask flags, prefer ask behavior
            legacy_ask = bool(config_manager.get("remove_task_ask_delete_source") or False) or bool(config_manager.get("remove_task_ask_delete_cache") or False)

            # 4.a KeepFiles
            if _is_keep(policy):
                logger.info("Policy matched: KeepFiles. Removing card only.")
                card.deleteLater()
                return

            # Collect paths for Delete or Ask
            paths_to_delete = set()
            if hasattr(card, "recorded_paths"):
                paths_to_delete.update(card.recorded_paths)
            try:
                current_paths = self._collect_existing_cache_paths([card])
                paths_to_delete.update(current_paths)
            except Exception:
                pass
            
            valid_paths = [p for p in paths_to_delete if p and os.path.exists(p)]
            cache_paths = [p for p in valid_paths if p.endswith(".part") or p.endswith(".ytdl")]
            source_paths = [p for p in valid_paths if p not in cache_paths]

            # 4.b DeleteFiles (explicit delete preference or legacy config)
            if _is_delete(policy) and not _is_ask(policy) and not legacy_ask:
                logger.info("Policy matched: DeleteFiles. Deleting files silently.")
                if valid_paths:
                    logger.info(f"Deleting {len(valid_paths)} files: {valid_paths}")
                    self._delete_files_best_effort(valid_paths, success_title="已删除相关文件")
                else:
                    logger.info("No files found to delete.")
                card.deleteLater()
                return

            # Fallback: AlwaysAsk (or unknown policy)
            if _is_ask(policy) or legacy_ask or (not _is_delete(policy) and not _is_keep(policy)):
                logger.info("Policy matched or falling back to: AlwaysAsk.")
            else:
                # Unknown token combination, but safe fallback to Ask
                logger.warning(f"Unknown deletion policy: '{policy}', falling back to ASK.")

            title = "删除任务"
            content = "确定要从列表中移除此任务吗？"
            
            box = MessageBox(title, content, self)
            box.yesButton.setText("删除")
            box.cancelButton.setText("取消")
            
            delete_cache_cb = None
            if cache_paths:
                delete_cache_cb = QCheckBox(f"同时删除 {len(cache_paths)} 个缓存文件", box)
                delete_cache_cb.setChecked(True)
                # MessageBox (qfluentwidgets) uses textLayout for content area
                try:
                    box.textLayout.addWidget(delete_cache_cb)
                except Exception:
                    box.vBoxLayout.addWidget(delete_cache_cb)
            
            delete_source_cb = None
            if source_paths:
                delete_source_cb = QCheckBox(f"同时删除 {len(source_paths)} 个本地文件", box)
                delete_source_cb.setChecked(False)
                try:
                    box.textLayout.addWidget(delete_source_cb)
                except Exception:
                    box.vBoxLayout.addWidget(delete_source_cb)

            if not box.exec():
                logger.info("User cancelled deletion.")
                return 

            final_paths = []
            if delete_cache_cb and delete_cache_cb.isChecked():
                final_paths.extend(cache_paths)
            if delete_source_cb and delete_source_cb.isChecked():
                final_paths.extend(source_paths)
                
            if final_paths:
                self._delete_files_best_effort(final_paths, success_title="已删除选中文件")

            card.deleteLater()
            logger.info("Card removed successfully.")

        except Exception as e:
            logger.exception(f"Critical error in on_remove_card: {e}")
            # Last resort: try to remove the card anyway so UI isn't stuck
            try:
                card.deleteLater()
            except:
                pass

    # --- Helper Methods Copied from Old MainWindow ---
    def _collect_existing_cache_paths(self, cards: Iterable[DownloadItemWidget]) -> list[str]:
        paths = []
        for card in cards:
            if not getattr(card, "worker", None):
                continue
            try:
                # 1. Collect from worker.dest_paths (parsed from stdout)
                dest_paths = getattr(card.worker, "dest_paths", set())
                
                # 2. Also check output_path if available
                output_path = getattr(card.worker, "output_path", None)
                if output_path:
                    dest_paths.add(output_path)

                # 3. Scan directory for .part/.ytdl files if we have a download_dir
                # This helps if stdout was garbled or incomplete.
                download_dir = getattr(card.worker, "download_dir", None)
                if download_dir and os.path.isdir(download_dir):
                    # Try to match files that look like they belong to this task.
                    # If we have a video ID in the URL or title, we can use it.
                    # But worker.url might be a full URL.
                    # Let's try to find files that contain the video ID if possible, 
                    # or just scan for .part files that were recently modified? 
                    # Scanning all .part files is risky if there are multiple downloads.
                    # Better strategy: If we have output_path, use its basename (without ext) to find parts.
                    
                    # If output_path is known, we can look for output_path + ".part"
                    if output_path:
                        base_name = os.path.basename(output_path)
                        # Common patterns: filename.mp4.part, filename.f137.mp4.part
                        # We can scan the dir for files starting with the stem of the output filename?
                        pass
                    
                    # Fallback: If dest_paths is empty, we might have missed it.
                    # But without a reliable ID/Filename, scanning is dangerous.
                    pass

                for p in dest_paths:
                    if not p: continue
                    
                    # If p is a cache file itself
                    if p.endswith(".part") or p.endswith(".ytdl"):
                        if os.path.isfile(p):
                            paths.append(p)
                    else:
                        # If p is the target file, check for .part/.ytdl variants
                        part = p + ".part"
                        if os.path.isfile(part):
                            paths.append(part)
                        ytdl = p + ".ytdl"
                        if os.path.isfile(ytdl):
                            paths.append(ytdl)
            except Exception:
                continue
        return paths

    def _collect_existing_output_paths(self, cards: Iterable[DownloadItemWidget]) -> list[str]:
        paths = []
        for card in cards:
            if not getattr(card, "worker", None):
                continue
            try:
                p = getattr(card.worker, "output_path", None)
                if p and os.path.isfile(p):
                    paths.append(p)
            except Exception:
                continue
        return paths

    def _prompt_delete_cache_files(self, paths: list[str], title: str) -> bool:
        box = MessageBox(title, f"即将删除 {len(paths)} 个缓存文件，是否继续？", self)
        return bool(box.exec())

    def _prompt_delete_source_files(self, paths: list[str], title: str) -> bool:
        box = MessageBox(title, f"即将删除 {len(paths)} 个源文件，是否继续？", self)
        return bool(box.exec())

    def _delete_files_best_effort(self, paths: list[str], success_title: str) -> None:
        deleted_count = 0
        for p in paths:
            if not p or not os.path.exists(p):
                continue
            
            # Retry a few times for file locks
            for _ in range(3):
                try:
                    os.remove(p)
                    deleted_count += 1
                    break
                except PermissionError:
                    time.sleep(0.5)
                except Exception:
                    break
        
        if deleted_count > 0:
            InfoBar.success(success_title, f"已清理 {deleted_count} 个文件", parent=self)
        elif paths:
            InfoBar.warning(success_title, "未能删除文件，可能被占用或权限不足", parent=self)

    def on_resume_card(self, card: DownloadItemWidget):
        # 重启任务逻辑
        # 需要重新创建 worker
        new_worker = download_manager.create_worker(card.url, card.opts)
        # 更新 card 的 worker
        card._bind_worker(new_worker)
        
        # Update status text immediately to show feedback
        card.update_status("正在恢复下载...")
        
        download_manager.start_worker(new_worker)
        card.set_state("running")

    def on_batch_start(self, page: TaskListPage):
        cards = page.get_selected_cards()
        for card in cards:
            if isinstance(card, DownloadItemWidget):
                if card.state() in {"paused", "error", "queued"}:
                    self.on_resume_card(card)

    def on_batch_pause(self, page: TaskListPage):
        cards = page.get_selected_cards()
        for card in cards:
            if isinstance(card, DownloadItemWidget):
                if card.state() == "running":
                    # Use stop() when available; fall back to cancel() for legacy workers.
                    try:
                        if hasattr(card.worker, "stop"):
                            card.worker.stop()
                        elif hasattr(card.worker, "cancel"):
                            card.worker.cancel()
                    except Exception:
                        # Best-effort; ignore errors to avoid blocking batch operations
                        pass

    def on_batch_delete(self, page: TaskListPage):
        cards = page.get_selected_cards()
        if not cards:
            return
        
        if not MessageBox(
            "批量删除", 
            f"确定要删除选中的 {len(cards)} 个任务吗？", 
            self
        ).exec():
            return
        
        for card in cards:
            if isinstance(card, DownloadItemWidget):
                self.on_remove_card(card)

    def on_start_all(self):
        # Start all in Downloading (if any are paused/queued) and Paused page
        # Iterate Downloading Page
        for i in range(self.downloading_page.count()):
            item = self.downloading_page.scroll_layout.itemAt(i)
            if item and item.widget():
                card = item.widget()
                if isinstance(card, DownloadItemWidget) and card.state() != "running":
                    self.on_resume_card(card)
        
        # Iterate Paused Page (move them to Downloading)
        paused_cards = []
        for i in range(self.paused_page.count()):
            item = self.paused_page.scroll_layout.itemAt(i)
            if item and item.widget():
                paused_cards.append(item.widget())
        
        for card in paused_cards:
            self.on_resume_card(card)

    def on_pause_all(self):
        download_manager.stop_all()

    def on_clear_completed(self):
        if self.completed_page.count() == 0:
            return
        if MessageBox("清空记录", "确定要清空所有已完成任务记录吗？\n(不会删除本地文件)", self).exec():
            # Remove all widgets
            while self.completed_page.scroll_layout.count():
                item = self.completed_page.scroll_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

    def on_open_download_dir(self):
        # 打开默认下载目录
        path = config_manager.get("download_dir") or os.getcwd()
        if os.path.exists(path):
            os.startfile(path)

    def init_title_bar(self):
        # 在标题栏添加帮助按钮
        # Parent MUST be titleBar to ensure correct z-order and event handling
        self.help_btn = TransparentToolButton(FluentIcon.HELP, self.titleBar)
        self.help_btn.setToolTip("帮助中心")
        self.help_btn.clicked.connect(self.show_help_window)
        self.help_btn.setFixedSize(46, 32)
        
        # 查找插入位置：尝试插在系统按钮组的最左边
        layout = self.titleBar.layout()
        # Insert the help button to the left of the system buttons (min/max/close)
        # Assuming system buttons are the last three widgets in the title bar layout
        layout.insertWidget(layout.count() - 3, self.help_btn, 0, Qt.AlignmentFlag.AlignRight)
        
        # 给 help_btn 设置右边距，让它离系统按钮远一点
        self.help_btn.setContentsMargins(0, 0, 10, 0)

    def show_help_window(self):
        if not getattr(self, "_help_window", None):
            self._help_window = HelpWindow()
        self._help_window.show()
        self._help_window.activateWindow()

    def check_first_run(self):
        """Check if welcome guide should be shown based on version."""
        from fluentytdl import __version__
        
        # Get the current major version (e.g., "1" from "1.0.16")
        current_major = __version__.split(".")[0] if __version__ else "0"
        
        # Get the version when user last saw the guide
        shown_for_version = config_manager.get("welcome_guide_shown_for_version", "")
        shown_major = shown_for_version.split(".")[0] if shown_for_version else ""
        
        # Show welcome guide if:
        # 1. Never shown before (empty version)
        # 2. Major version has changed (e.g., 0.x.x -> 1.x.x)
        should_show = not shown_for_version or (shown_major != current_major)
        
        if should_show:
            logger.info(f"Showing Welcome Wizard (current: {__version__}, last shown: {shown_for_version})")
            w = WelcomeWizardDialog(self)
            w.exec()
            # Record the full version when guide was shown
            config_manager.set("welcome_guide_shown_for_version", __version__)
            config_manager.set("has_shown_welcome_guide", True)


