"""
FluentYTDL 频道管理页面

提供频道批量下载功能:
- 频道搜索/添加
- 视频列表展示
- 批量下载
- 归档管理
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal, QSize, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QListView,
    QAbstractItemView,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    CheckBox,
    FluentIcon,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    ProgressRing,
    PushButton,
    SubtitleLabel,
    TransparentToolButton,
)

from ..core.channel_service import (
    ChannelInfo,
    ChannelService,
    VideoItem,
    VideoListResult,
    channel_service,
    validate_channel_url,
)
from ..core.archive_manager import archive_manager
from ..utils.logger import get_logger

logger = get_logger("fluentytdl.ChannelPage")


class VideoItemWidget(QFrame):
    """视频项卡片"""
    
    selected_changed = Signal(bool)
    download_requested = Signal(str)  # video_url
    
    def __init__(self, video: VideoItem, parent=None):
        super().__init__(parent)
        self.video = video
        self._selected = False
        
        self._init_ui()
        self._update_downloaded_state()
    
    def _init_ui(self):
        self.setFixedHeight(56)
        self.setStyleSheet("""
            VideoItemWidget {
                background-color: transparent;
                border-radius: 6px;
            }
            VideoItemWidget:hover {
                background-color: rgba(0, 0, 0, 0.03);
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)
        
        # 复选框
        self.checkbox = CheckBox(self)
        self.checkbox.stateChanged.connect(self._on_checkbox_changed)
        layout.addWidget(self.checkbox)
        
        # 缩略图
        self.thumbLabel = QLabel(self)
        self.thumbLabel.setFixedSize(80, 45)
        self.thumbLabel.setStyleSheet("background-color: #e0e0e0; border-radius: 4px;")
        self.thumbLabel.setScaledContents(True)
        layout.addWidget(self.thumbLabel)
        
        # 加载缩略图
        if self.video.thumbnail:
            self._load_thumbnail(self.video.thumbnail)
        
        # 标题和信息
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)
        
        self.titleLabel = BodyLabel(self.video.title, self)
        self.titleLabel.setWordWrap(False)
        info_layout.addWidget(self.titleLabel)
        
        meta_text = f"{self.video.duration_text} • {self.video.upload_date[:10] if self.video.upload_date else ''}"
        self.metaLabel = CaptionLabel(meta_text, self)
        self.metaLabel.setStyleSheet("color: #888;")
        info_layout.addWidget(self.metaLabel)
        
        layout.addLayout(info_layout, 1)
        
        # 状态标签
        self.statusLabel = CaptionLabel("", self)
        layout.addWidget(self.statusLabel)
        
        # 下载按钮
        self.downloadBtn = TransparentToolButton(FluentIcon.DOWNLOAD, self)
        self.downloadBtn.setToolTip("下载此视频")
        self.downloadBtn.clicked.connect(lambda: self.download_requested.emit(self.video.url))
        layout.addWidget(self.downloadBtn)
    
    def _load_thumbnail(self, url: str):
        """异步加载缩略图"""
        try:
            manager = QNetworkAccessManager(self)
            request = QNetworkRequest(QUrl(url))
            reply = manager.get(request)
            reply.finished.connect(lambda: self._on_thumb_loaded(reply))
        except Exception:
            pass
    
    def _on_thumb_loaded(self, reply: QNetworkReply):
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = reply.readAll()
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                self.thumbLabel.setPixmap(pixmap)
        except Exception:
            pass
        finally:
            reply.deleteLater()
    
    def _update_downloaded_state(self):
        """更新下载状态"""
        if archive_manager.is_downloaded(self.video.video_id):
            self.video.is_downloaded = True
            self.statusLabel.setText("✅ 已下载")
            self.statusLabel.setStyleSheet("color: #52c41a;")
            self.downloadBtn.hide()
        else:
            self.statusLabel.setText("")
            self.downloadBtn.show()
    
    def _on_checkbox_changed(self, state):
        self._selected = state == Qt.CheckState.Checked.value
        self.selected_changed.emit(self._selected)
    
    def is_selected(self) -> bool:
        return self._selected
    
    def set_selected(self, selected: bool):
        self.checkbox.setChecked(selected)


class ChannelCard(CardWidget):
    """频道信息卡片"""
    
    refresh_requested = Signal()
    download_all_requested = Signal()
    remove_requested = Signal()
    
    def __init__(self, channel: ChannelInfo, parent=None):
        super().__init__(parent)
        self.channel = channel
        self._init_ui()
    
    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)
        
        # 头像
        self.avatarLabel = QLabel(self)
        self.avatarLabel.setFixedSize(64, 64)
        self.avatarLabel.setStyleSheet("""
            background-color: #e0e0e0;
            border-radius: 32px;
        """)
        self.avatarLabel.setScaledContents(True)
        layout.addWidget(self.avatarLabel)
        
        if self.channel.thumbnail:
            self._load_avatar(self.channel.thumbnail)
        
        # 频道信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        
        self.nameLabel = SubtitleLabel(self.channel.name, self)
        info_layout.addWidget(self.nameLabel)
        
        handle_text = f"@{self.channel.handle}" if self.channel.handle else ""
        meta_text = f"{handle_text} • {self.channel.subscriber_text} 订阅"
        self.metaLabel = CaptionLabel(meta_text, self)
        self.metaLabel.setStyleSheet("color: #666;")
        info_layout.addWidget(self.metaLabel)
        
        # 归档统计
        downloaded_count = archive_manager.get_channel_download_count(self.channel.channel_id)
        self.archiveLabel = CaptionLabel(f"已归档 {downloaded_count} 个视频", self)
        info_layout.addWidget(self.archiveLabel)
        
        layout.addLayout(info_layout, 1)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        self.downloadBtn = PrimaryPushButton(FluentIcon.DOWNLOAD, "下载全部", self)
        self.downloadBtn.clicked.connect(self.download_all_requested)
        btn_layout.addWidget(self.downloadBtn)
        
        self.refreshBtn = PushButton(FluentIcon.SYNC, "检查更新", self)
        self.refreshBtn.clicked.connect(self.refresh_requested)
        btn_layout.addWidget(self.refreshBtn)
        
        self.removeBtn = TransparentToolButton(FluentIcon.DELETE, self)
        self.removeBtn.setToolTip("移除频道")
        self.removeBtn.clicked.connect(self.remove_requested)
        btn_layout.addWidget(self.removeBtn)
        
        layout.addLayout(btn_layout)
    
    def _load_avatar(self, url: str):
        """异步加载头像"""
        try:
            manager = QNetworkAccessManager(self)
            request = QNetworkRequest(QUrl(url))
            reply = manager.get(request)
            reply.finished.connect(lambda: self._on_avatar_loaded(reply))
        except Exception:
            pass
    
    def _on_avatar_loaded(self, reply: QNetworkReply):
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = reply.readAll()
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                self.avatarLabel.setPixmap(pixmap)
        except Exception:
            pass
        finally:
            reply.deleteLater()
    
    def update_archive_count(self):
        """更新归档统计"""
        count = archive_manager.get_channel_download_count(self.channel.channel_id)
        self.archiveLabel.setText(f"已归档 {count} 个视频")


class ChannelPage(QWidget):
    """频道管理页面"""
    
    download_requested = Signal(list)  # [(title, url, opts, thumb), ...]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("channelPage")
        
        self._current_channel: ChannelInfo | None = None
        self._videos: list[VideoItem] = []
        self._video_widgets: list[VideoItemWidget] = []
        
        self._init_ui()
        self._connect_signals()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        # === 标题栏 ===
        header = QHBoxLayout()
        self.titleLabel = SubtitleLabel("📺 频道管理", self)
        header.addWidget(self.titleLabel)
        header.addStretch()
        layout.addLayout(header)
        
        # === 添加频道输入 ===
        input_card = CardWidget(self)
        input_layout = QHBoxLayout(input_card)
        input_layout.setContentsMargins(16, 12, 16, 12)
        
        self.urlInput = LineEdit(self)
        self.urlInput.setPlaceholderText("输入频道 URL 或 @handle...")
        self.urlInput.setClearButtonEnabled(True)
        self.urlInput.returnPressed.connect(self._on_add_channel)
        input_layout.addWidget(self.urlInput, 1)
        
        self.addBtn = PrimaryPushButton(FluentIcon.ADD, "添加频道", self)
        self.addBtn.clicked.connect(self._on_add_channel)
        input_layout.addWidget(self.addBtn)
        
        layout.addWidget(input_card)
        
        # === 加载指示器 ===
        self.loadingWidget = QWidget(self)
        loading_layout = QHBoxLayout(self.loadingWidget)
        loading_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loadingRing = ProgressRing(self)
        self.loadingRing.setFixedSize(32, 32)
        loading_layout.addWidget(self.loadingRing)
        self.loadingLabel = BodyLabel("加载中...", self)
        loading_layout.addWidget(self.loadingLabel)
        self.loadingWidget.hide()
        layout.addWidget(self.loadingWidget)
        
        # === 频道卡片 ===
        self.channelCardPlaceholder = QWidget(self)
        self.channelCardLayout = QVBoxLayout(self.channelCardPlaceholder)
        self.channelCardLayout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.channelCardPlaceholder)
        
        # === 视频列表工具栏 ===
        self.videoToolbar = QWidget(self)
        toolbar_layout = QHBoxLayout(self.videoToolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        
        self.selectAllBtn = PushButton(FluentIcon.CHECKBOX, "全选", self)
        self.selectAllBtn.clicked.connect(self._on_select_all)
        toolbar_layout.addWidget(self.selectAllBtn)
        
        self.downloadSelectedBtn = PushButton(FluentIcon.DOWNLOAD, "下载选中", self)
        self.downloadSelectedBtn.clicked.connect(self._on_download_selected)
        toolbar_layout.addWidget(self.downloadSelectedBtn)
        
        toolbar_layout.addStretch()
        
        self.videoCountLabel = CaptionLabel("", self)
        toolbar_layout.addWidget(self.videoCountLabel)
        
        self.videoToolbar.hide()
        layout.addWidget(self.videoToolbar)
        
        # === 视频列表 ===
        self.videoScrollArea = QScrollArea(self)
        self.videoScrollArea.setWidgetResizable(True)
        self.videoScrollArea.setFrameShape(QFrame.Shape.NoFrame)
        self.videoScrollArea.setStyleSheet("background: transparent;")
        
        self.videoListWidget = QWidget()
        self.videoListWidget.setStyleSheet("background: transparent;")
        self.videoListLayout = QVBoxLayout(self.videoListWidget)
        self.videoListLayout.setContentsMargins(0, 0, 0, 0)
        self.videoListLayout.setSpacing(4)
        self.videoListLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.videoScrollArea.setWidget(self.videoListWidget)
        self.videoScrollArea.hide()
        layout.addWidget(self.videoScrollArea, 1)
        
        # === 空状态 ===
        self.emptyWidget = QWidget(self)
        empty_layout = QVBoxLayout(self.emptyWidget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.emptyIcon = IconWidget(FluentIcon.PEOPLE, self)
        self.emptyIcon.setFixedSize(64, 64)
        empty_layout.addWidget(self.emptyIcon, 0, Qt.AlignmentFlag.AlignHCenter)
        
        self.emptyLabel = BodyLabel("添加一个 YouTube 频道开始批量下载", self)
        self.emptyLabel.setStyleSheet("color: #888;")
        empty_layout.addWidget(self.emptyLabel, 0, Qt.AlignmentFlag.AlignHCenter)
        
        layout.addWidget(self.emptyWidget, 1)
    
    def _connect_signals(self):
        channel_service.channel_loaded.connect(self._on_channel_loaded)
        channel_service.videos_loaded.connect(self._on_videos_loaded)
        channel_service.error.connect(self._on_error)
    
    def _on_add_channel(self):
        """添加频道"""
        url = self.urlInput.text().strip()
        if not url:
            return
        
        # 验证 URL
        is_valid, identifier = validate_channel_url(url)
        if not is_valid and not url.startswith("@"):
            InfoBar.warning(
                "无效的频道链接",
                "请输入有效的 YouTube 频道 URL 或 @handle",
                parent=self,
            )
            return
        
        # 显示加载
        self.loadingWidget.show()
        self.emptyWidget.hide()
        self.addBtn.setEnabled(False)
        
        # 加载频道
        channel_service.load_channel(url)
    
    def _on_channel_loaded(self, channel: ChannelInfo):
        """频道加载完成"""
        self._current_channel = channel
        
        # 隐藏加载
        self.loadingWidget.hide()
        self.addBtn.setEnabled(True)
        self.urlInput.clear()
        
        # 清除旧卡片
        while self.channelCardLayout.count():
            item = self.channelCardLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 显示频道卡片
        card = ChannelCard(channel, self)
        card.download_all_requested.connect(self._on_download_all)
        card.refresh_requested.connect(self._on_refresh_videos)
        card.remove_requested.connect(self._on_remove_channel)
        self.channelCardLayout.addWidget(card)
        
        # 加载视频列表
        self.loadingLabel.setText("正在加载视频列表...")
        self.loadingWidget.show()
        channel_service.load_videos(channel.url)
    
    def _on_videos_loaded(self, result: VideoListResult):
        """视频列表加载完成"""
        self.loadingWidget.hide()
        self._videos = result.videos
        
        # 更新下载状态
        for video in self._videos:
            video.is_downloaded = archive_manager.is_downloaded(video.video_id)
        
        # 清除旧列表
        self._clear_video_list()
        
        # 显示视频列表
        self._video_widgets = []
        for video in self._videos:
            widget = VideoItemWidget(video, self)
            widget.download_requested.connect(self._on_single_download)
            self._video_widgets.append(widget)
            self.videoListLayout.addWidget(widget)
        
        # 更新 UI
        self.videoToolbar.show()
        self.videoScrollArea.show()
        self.emptyWidget.hide()
        
        new_count = len([v for v in self._videos if not v.is_downloaded])
        self.videoCountLabel.setText(f"共 {len(self._videos)} 个视频，{new_count} 个未下载")
    
    def _on_error(self, error: str):
        """错误处理"""
        self.loadingWidget.hide()
        self.addBtn.setEnabled(True)
        self.emptyWidget.show()
        
        InfoBar.error("加载失败", error, parent=self)
    
    def _on_refresh_videos(self):
        """刷新视频列表"""
        if self._current_channel:
            self.loadingLabel.setText("正在刷新...")
            self.loadingWidget.show()
            channel_service.load_videos(self._current_channel.url)
    
    def _on_remove_channel(self):
        """移除频道"""
        self._current_channel = None
        self._videos = []
        self._clear_video_list()
        
        while self.channelCardLayout.count():
            item = self.channelCardLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.videoToolbar.hide()
        self.videoScrollArea.hide()
        self.emptyWidget.show()

    def _clear_video_list(self):
        """清除视频列表"""
        while self.videoListLayout.count():
            item = self.videoListLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._video_widgets = []

    def _on_select_all(self):
        """全选/全不选"""
        if not self._video_widgets:
            return
        
        all_selected = all(w.is_selected() for w in self._video_widgets)
        new_state = not all_selected
        
        for w in self._video_widgets:
            w.set_selected(new_state)

    def _on_download_selected(self):
        """下载选中"""
        selected_tasks = []
        for w in self._video_widgets:
            if w.is_selected() and not w.video.is_downloaded:
                # 构建任务信息: (title, url, opts, thumb)
                selected_tasks.append((w.video.title, w.video.url, {}, w.video.thumbnail))
        
        if selected_tasks:
            self.download_requested.emit(selected_tasks)
            InfoBar.success("已添加任务", f"成功添加 {len(selected_tasks)} 个下载任务", parent=self)
        else:
            InfoBar.warning("未选中", "请先选择未下载的视频", parent=self)

    def _on_single_download(self, url: str):
        """单视频下载"""
        # 寻找对应的视频详情
        for v in self._videos:
            if v.url == url:
                self.download_requested.emit([(v.title, v.url, {}, v.thumbnail)])
                InfoBar.success("已添加任务", v.title, parent=self)
                break

    def _on_download_all(self):
        """下载全部未下载"""
        tasks = []
        for v in self._videos:
            if not archive_manager.is_downloaded(v.video_id):
                tasks.append((v.title, v.url, {}, v.thumbnail))
        
        if tasks:
            self.download_requested.emit(tasks)
            InfoBar.success("已添加全部", f"成功添加 {len(tasks)} 个下载任务", parent=self)
        else:
            InfoBar.info("无新任务", "该频道的视频均已归档", parent=self)
