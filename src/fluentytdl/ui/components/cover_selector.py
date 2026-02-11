"""
FluentYTDL 封面选择器组件

显示视频所有可用封面（缩略图）列表，允许用户选择特定尺寸/格式下载。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    PrimaryPushButton,
    ImageLabel,
    TableWidget,
)

from ...utils.image_loader import ImageLoader


class CoverSelectorWidget(QFrame):
    """
    封面选择器组件
    
    解析并显示所有可用缩略图，提供预览和选择功能。
    """
    
    # 选中项变更信号
    selectionChanged = Signal()
    
    def __init__(self, info: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.info = info
        self._thumbnails: list[dict[str, Any]] = []
        self._selected_url: str | None = None
        self._selected_ext: str = "jpg"
        
        self._init_data()
        
        # Initialize image loader BEFORE UI setup because _init_ui calls selectRow which triggers loading
        self.image_loader = ImageLoader(self)
        self.image_loader.loaded_with_url.connect(self._on_image_loaded)
        
        self._init_ui()
        
    def _init_data(self):
        """解析缩略图数据"""
        raw_thumbs = self.info.get("thumbnails", [])
        if not raw_thumbs:
            # Fallback if no thumbnails list (rare)
            thumb = self.info.get("thumbnail")
            if thumb:
                raw_thumbs = [{"url": thumb, "id": "default", "width": 0, "height": 0}]
        
        # 整理数据
        processed = []
        for t in raw_thumbs:
            url = t.get("url")
            if not url:
                continue
                
            width = t.get("width") or 0
            height = t.get("height") or 0
            res = f"{width}x{height}" if width and height else "未知"
            t_id = t.get("id") or "unknown"
            
            # 尝试从 URL 推断格式
            ext = "jpg"
            if ".webp" in url:
                ext = "webp"
            elif ".png" in url:
                ext = "png"
            
            # 估算清晰度分数 (用于排序)
            score = (width or 0) * (height or 0)
            if "maxres" in t_id:
                score += 10000000
            
            processed.append({
                "url": url,
                "res": res,
                "width": width,
                "height": height,
                "id": t_id,
                "ext": ext,
                "score": score,
                "preference": t.get("preference", 0)
            })
            
        # 按清晰度降序排序
        processed.sort(key=lambda x: (x["score"], x["preference"]), reverse=True)
        self._thumbnails = processed
        
        if self._thumbnails:
            self._selected_url = self._thumbnails[0]["url"]

    def _init_ui(self):
        self.setObjectName("coverSelector")
        self.setStyleSheet("""
            #coverSelector {
                background-color: rgba(255, 255, 255, 0.7);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 8px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # 标题
        self.titleLabel = BodyLabel("🖼️ 封面选择", self)
        self.titleLabel.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.titleLabel)
        
        # 主内容区：左侧表格，右侧预览
        contentLayout = QHBoxLayout()
        contentLayout.setSpacing(16)
        
        # 左侧表格
        self.table = TableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["分辨率", "ID", "格式"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        
        # 填充表格
        self.table.setRowCount(len(self._thumbnails))
        for i, t in enumerate(self._thumbnails):
            # 分辨率
            res_item = QTableWidgetItem(t["res"])
            res_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, res_item)
            
            # ID
            id_item = QTableWidgetItem(t["id"])
            self.table.setItem(i, 1, id_item)
            
            # 格式
            ext_item = QTableWidgetItem(t["ext"].upper())
            ext_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, ext_item)
            
        contentLayout.addWidget(self.table, stretch=1)
        
        # 右侧预览区
        previewContainer = QFrame(self)
        previewContainer.setFixedWidth(240)
        previewContainer.setStyleSheet("background-color: rgba(0,0,0,0.03); border-radius: 8px;")
        previewLayout = QVBoxLayout(previewContainer)
        
        self.previewLabel = ImageLabel(previewContainer)
        self.previewLabel.setFixedSize(220, 124) # 16:9 ratio approx
        self.previewLabel.scaledToWidth(220)
        
        self.previewInfo = CaptionLabel("预览加载中...", previewContainer)
        self.previewInfo.setWordWrap(True)
        self.previewInfo.setAlignment(Qt.AlignCenter)
        
        previewLayout.addWidget(self.previewLabel, alignment=Qt.AlignmentFlag.AlignHCenter)
        previewLayout.addWidget(self.previewInfo, alignment=Qt.AlignmentFlag.AlignHCenter)
        previewLayout.addStretch()
        
        contentLayout.addWidget(previewContainer)
        
        layout.addLayout(contentLayout)
        
        # 选中第一行 (UI 初始化完成后再触发选择)
        if self._thumbnails:
            self.table.selectRow(0)
        
    def _on_selection_changed(self):
        rows = self.table.selectedItems()
        if not rows:
            return
            
        row = rows[0].row()
        if 0 <= row < len(self._thumbnails):
            thumb = self._thumbnails[row]
            self._selected_url = thumb["url"]
            self._selected_ext = thumb["ext"]
            
            # 更新预览信息
            self.previewInfo.setText(f"{thumb['res']} • {thumb['ext'].upper()}\n{thumb['id']}")
            
            # 加载图片
            self._load_preview(thumb["url"])
            
            self.selectionChanged.emit()
            
    def _load_preview(self, url: str):
        # 使用 ImageLoader 异步加载
        self.image_loader.load(url, allow_webp=True)
        
    def _on_image_loaded(self, url: str, pixmap: QPixmap):
        # Only update if it matches current selection
        if url != self._selected_url:
            return
            
        if pixmap and not pixmap.isNull():
            # Scale to fit
            scaled = pixmap.scaled(
                self.previewLabel.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.previewLabel.setPixmap(scaled)
        else:
            self.previewLabel.clear()
            
    def get_selected_url(self) -> str | None:
        return self._selected_url
        
    def get_selected_ext(self) -> str:
        return self._selected_ext
