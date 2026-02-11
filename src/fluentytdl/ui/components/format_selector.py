from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    CaptionLabel,
    ComboBox,
    FluentIcon,
    IconWidget,
    RadioButton,
    ScrollArea,
    SegmentedWidget,
    StrongBodyLabel,
    SubtitleLabel,
)

from .badges import QualityCellWidget


_TABLE_SELECTION_QSS = """
QTableWidget {
    background-color: transparent;
    outline: none;
    border: none;
}
QTableWidget::item {
    padding-left: 0px;
    border: 1px solid rgba(0, 0, 0, 0.06);
    margin-top: 3px;
    margin-bottom: 3px;
    margin-left: 4px;
    margin-right: 4px;
    border-radius: 6px;
}
QTableWidget::item:selected {
    background-color: #E8E8E8;
    color: #000000;
    border: 1px solid #C0C0C0;
    border-radius: 6px;
    font-weight: 600;
}
QTableWidget::item:hover {
    background-color: #F3F3F3;
    border: 1px solid rgba(0, 0, 0, 0.1);
    border-radius: 6px;
}
"""

def _format_size(value: Any) -> str:
    try:
        n = int(value)
    except Exception:
        return "-"
    if n <= 0:
        return "-"
    units = ["B", "KB", "MB", "GB"]
    x = float(n)
    for u in units:
        if x < 1024 or u == units[-1]:
            if u in ("B", "KB"):
                return f"{int(round(x))}{u}"
            return f"{x:.1f}{u}"
        x /= 1024
    return f"{n}B"

def _choose_lossless_merge_container(video_ext: str | None, audio_ext: str | None) -> str | None:
    v = str(video_ext or "").strip().lower()
    a = str(audio_ext or "").strip().lower()
    if not v or not a: return None
    if v == "webm" and a == "webm": return "webm"
    if v in {"mp4", "m4v"} and a in {"m4a", "aac", "mp4"}: return "mp4"
    return "mkv"


def _analyze_format_tags(r: dict) -> list[tuple[str, str]]:
    """Generates badge data for format details: [(text, color_style), ...]"""
    tags = []
    
    # 1. HDR
    dyn = str(r.get("dynamic_range") or "SDR").upper()
    if dyn != "SDR":
        # Usually HDR10, HLG, etc.
        tags.append((dyn, "gold"))
        
    # 2. FPS
    fps = r.get("fps")
    if fps and fps > 30:
        tags.append((f"{int(fps)}FPS", "red"))
        
    # 3. Codec
    # Video
    vc = str(r.get("vcodec") or "none").lower()
    if "av01" in vc:
        tags.append(("AV1", "blue"))
    elif "vp9" in vc:
        tags.append(("VP9", "green"))
    elif "avc1" in vc or "h264" in vc:
        # Gray for older/compatible codec
        tags.append(("H.264", "gray"))
        
    # Audio
    ac = str(r.get("acodec") or "none").lower()
    if "opus" in ac:
        tags.append(("Opus", "green"))
    elif "mp4a" in ac or "aac" in ac:
        tags.append(("AAC", "gray"))
        
    return tags


class SimplePresetWidget(QWidget):
    """简易模式下的预设选项卡片"""

    presetSelected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建滚动区域
        scroll_area = ScrollArea(self)
        scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(450)  # 限制最大高度
        
        # 滚动内容容器
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: transparent;")
        self.v_layout = QVBoxLayout(content_widget)
        self.v_layout.setSpacing(12)
        self.v_layout.setContentsMargins(10, 10, 10, 10)
        
        self.btn_group = QButtonGroup(self)
        self.btn_group.buttonClicked.connect(self.presetSelected)
        
        # Define presets
        self.presets = [
            # === 推荐选项 ===
            (
                "best_mp4", 
                "🎬 最佳画质 (MP4)", 
                "推荐。自动选择最佳画质并封装为 MP4，兼容性最好。", 
                "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba",
                {"merge_output_format": "mp4"}
            ),
            (
                "best_raw", 
                "🎯 最佳画质 (原盘)", 
                "追求极致画质。通常为 WebM/MKV 格式，适合本地播放。", 
                "bestvideo*+bestaudio/best",
                {}
            ),
            # === 分辨率限制 ===
            (
                "2160p", 
                "📺 2160p 4K (MP4)", 
                "限制最高分辨率为 4K，超高清画质。", 
                "bv*[height<=2160][ext=mp4]+ba[ext=m4a]/b[height<=2160][ext=mp4]/bv*[height<=2160]+ba",
                {"merge_output_format": "mp4"}
            ),
            (
                "1440p", 
                "📺 1440p 2K (MP4)", 
                "限制最高分辨率为 2K，高清画质。", 
                "bv*[height<=1440][ext=mp4]+ba[ext=m4a]/b[height<=1440][ext=mp4]/bv*[height<=1440]+ba",
                {"merge_output_format": "mp4"}
            ),
            (
                "1080p", 
                "📺 1080p 高清 (MP4)", 
                "限制最高分辨率为 1080p，平衡画质与体积。", 
                "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba",
                {"merge_output_format": "mp4"}
            ),
            (
                "720p", 
                "📺 720p 标清 (MP4)", 
                "限制最高分辨率为 720p，适合移动设备。", 
                "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba",
                {"merge_output_format": "mp4"}
            ),
            (
                "480p", 
                "📺 480p (MP4)", 
                "限制最高分辨率为 480p，节省空间。", 
                "bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480][ext=mp4]/bv*[height<=480]+ba",
                {"merge_output_format": "mp4"}
            ),
            (
                "360p", 
                "📺 360p (MP4)", 
                "限制最高分辨率为 360p，最小体积。", 
                "bv*[height<=360][ext=mp4]+ba[ext=m4a]/b[height<=360][ext=mp4]/bv*[height<=360]+ba",
                {"merge_output_format": "mp4"}
            ),
            # === 纯音频 ===
            (
                "audio_mp3", 
                "🎵 纯音频 (MP3 - 320k)", 
                "仅下载音频并转码为 MP3。", 
                "bestaudio/best",
                {"extract_audio": True, "audio_format": "mp3", "audio_quality": "320K"}
            ),
        ]
        
        self.radios = []
        
        for i, (pid, title, desc, fmt, args) in enumerate(self.presets):
            container = QFrame(self)
            container.setStyleSheet(".QFrame { background-color: rgba(255, 255, 255, 0.05); border-radius: 6px; border: 1px solid rgba(0,0,0,0.05); }")
            h_layout = QHBoxLayout(container)
            
            rb = RadioButton(title, container)
            rb.setProperty("preset_id", pid)
            rb.setProperty("format_str", fmt)
            rb.setProperty("extra_args", args)
            
            self.btn_group.addButton(rb, i)
            self.radios.append(rb)
            
            desc_label = CaptionLabel(desc, container)
            # Make description gray
            desc_label.setStyleSheet("color: #808080;")
            desc_label.setWordWrap(True)
            
            h_layout.addWidget(rb)
            h_layout.addWidget(desc_label, 1)
            
            self.v_layout.addWidget(container)
            
        # 设置滚动区域
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)
        
        # Select first by default
        if self.radios:
            self.radios[0].setChecked(True)

    def get_current_selection(self) -> dict:
        btn = self.btn_group.checkedButton()
        if not btn: return {}
        return {
            "format": btn.property("format_str"),
            "extra": btn.property("extra_args"),
            "id": btn.property("preset_id")
        }


class VideoFormatSelectorWidget(QWidget):
    """
    Encapsulates the logic for selecting video/audio formats.
    Supports "Simple" (presets) and "Advanced" (table) modes.
    """
    
    selectionChanged = Signal()

    def __init__(self, info: dict[str, Any], parent=None):
        super().__init__(parent)
        self.info = info
        
        # State for advanced mode
        self._rows: list[dict[str, Any]] = []
        self._selected_video_id: str | None = None
        self._selected_audio_id: str | None = None
        self._selected_muxed_id: str | None = None
        
        self._current_mode = "simple"
        
        self._init_ui()
        self._build_rows(info)
        self._refresh_table()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # Mode Switcher
        self.view_switcher = SegmentedWidget(self)
        self.view_switcher.addItem("simple", "简易模式")
        self.view_switcher.addItem("advanced", "专业模式")
        self.view_switcher.setCurrentItem("simple")
        self.view_switcher.currentItemChanged.connect(self._on_mode_changed)
        layout.addWidget(self.view_switcher)
        
        # Stack
        self.stack = QStackedWidget(self)
        layout.addWidget(self.stack)
        
        # Page 1: Simple
        self.simple_widget = SimplePresetWidget(self)
        self.simple_widget.presetSelected.connect(self.selectionChanged)
        self.stack.addWidget(self.simple_widget)
        
        # Page 2: Advanced
        self.advanced_widget = QWidget(self)
        adv_layout = QVBoxLayout(self.advanced_widget)
        adv_layout.setContentsMargins(0, 0, 0, 0)
        adv_layout.setSpacing(10)
        
        # Mode Combo
        form_layout = QHBoxLayout()
        form_layout.addWidget(CaptionLabel("下载模式:", self.advanced_widget))
        self.mode_combo = ComboBox(self.advanced_widget)
        self.mode_combo.addItems(["音视频（可组装）", "音视频（整合流）", "仅视频", "仅音频"])
        self.mode_combo.currentIndexChanged.connect(self._refresh_table)
        form_layout.addWidget(self.mode_combo, 1)
        adv_layout.addLayout(form_layout)
        
        self.hint_label = CaptionLabel(
            "提示：可组装模式仅显示分离流，分别点选“视频”和“音频”即可组装。", 
            self.advanced_widget
        )
        adv_layout.addWidget(self.hint_label)
        
        # --- Tables Area ---
        
        # 1. Single Table (for modes 1, 2, 3)
        self.table = self._create_table()
        self.table.cellClicked.connect(self._on_table_clicked)
        adv_layout.addWidget(self.table)
        
        # 2. Split Container (for mode 0)
        self.split_container = QWidget(self.advanced_widget)
        split_layout = QVBoxLayout(self.split_container)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(10)
        
        # Video Section
        self.video_container = QFrame(self.split_container)
        self.video_container.setStyleSheet(".QFrame { background-color: rgba(255, 255, 255, 0.03); border: 1px solid rgba(0, 0, 0, 0.05); border-radius: 8px; }")
        v_layout = QVBoxLayout(self.video_container)
        v_layout.setContentsMargins(8, 8, 8, 8)
        v_layout.addWidget(StrongBodyLabel("视频流", self.video_container))
        self.video_table = self._create_table()
        self.video_table.cellClicked.connect(self._on_video_table_clicked)
        v_layout.addWidget(self.video_table)
        split_layout.addWidget(self.video_container)
        
        # Audio Section
        self.audio_container = QFrame(self.split_container)
        self.audio_container.setStyleSheet(".QFrame { background-color: rgba(255, 255, 255, 0.03); border: 1px solid rgba(0, 0, 0, 0.05); border-radius: 8px; }")
        a_layout = QVBoxLayout(self.audio_container)
        a_layout.setContentsMargins(8, 8, 8, 8)
        a_layout.addWidget(StrongBodyLabel("音频流", self.audio_container))
        self.audio_table = self._create_table()
        self.audio_table.cellClicked.connect(self._on_audio_table_clicked)
        a_layout.addWidget(self.audio_table)
        split_layout.addWidget(self.audio_container)
        
        adv_layout.addWidget(self.split_container)
        
        self.selection_label = CaptionLabel("未选择", self.advanced_widget)
        adv_layout.addWidget(self.selection_label)
        
        self.stack.addWidget(self.advanced_widget)

    def _create_table(self):
        t = QTableWidget(self.advanced_widget)
        t.setStyleSheet(_TABLE_SELECTION_QSS)
        t.setColumnCount(3)
        t.setHorizontalHeaderLabels(["类型", "质量", "详情"])
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        t.verticalHeader().setVisible(False)
        t.setAlternatingRowColors(True)
        t.setShowGrid(False)
        t.setWordWrap(False)
        try:
            t.verticalHeader().setDefaultSectionSize(42)
            t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
            t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            t.setColumnWidth(0, 60)
            t.setColumnWidth(1, 130)
        except: pass
        return t

    def _on_mode_changed(self, routeKey: str):
        self._current_mode = routeKey
        self.stack.setCurrentIndex(0 if routeKey == "simple" else 1)

    def _build_rows(self, info: dict[str, Any]):
        formats = info.get("formats") or []
        if not isinstance(formats, list): return

        candidates = []
        for f in formats:
            if not isinstance(f, dict): continue
            fid = str(f.get("format_id") or "").strip()
            if not fid: continue
            
            vcodec = str(f.get("vcodec") or "none")
            acodec = str(f.get("acodec") or "none")
            ext = str(f.get("ext") or "-")
            height = int(f.get("height") or 0)
            
            kind = "unknown"
            if vcodec != "none" and acodec != "none": kind = "muxed"
            elif vcodec != "none" and acodec == "none": kind = "video"
            elif vcodec == "none" and acodec != "none": kind = "audio"
            else: continue
            
            if kind in ("muxed", "video") and height and height < 144: continue
            
            candidates.append({
                "kind": kind, "format_id": fid, "ext": ext, "height": height,
                "vcodec": vcodec, "acodec": acodec,
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "fps": f.get("fps"), "abr": f.get("abr"),
                "dynamic_range": f.get("dynamic_range")
            })
            
        # Sort: muxed first, then video, then audio. Within kind, by height desc.
        candidates.sort(key=lambda x: (
            0 if x["kind"]=="muxed" else 1 if x["kind"]=="video" else 2, 
            -int(x.get("height") or 0)
        ))
        self._rows = candidates

    def _refresh_table(self):
        mode = self.mode_combo.currentIndex()
        self.hint_label.setVisible(mode == 0)
        
        # Clear incompatible selections
        if mode == 0: self._selected_muxed_id = None
        if mode == 1: 
            self._selected_video_id = None
            self._selected_audio_id = None
        if mode in (2, 3): 
            self._selected_muxed_id = None
            if mode == 2: self._selected_audio_id = None
            else: self._selected_video_id = None
            
        if mode == 0:
            # Split View
            self.table.hide()
            self.split_container.show()
            
            video_rows = [r for r in self._rows if r["kind"] == "video"]
            audio_rows = [r for r in self._rows if r["kind"] == "audio"]
            
            self._populate_table(self.video_table, video_rows, self._selected_video_id)
            self._populate_table(self.audio_table, audio_rows, self._selected_audio_id)
            
        else:
            # Single View
            self.split_container.hide()
            self.table.show()
            
            view_rows = []
            for r in self._rows:
                k = r["kind"]
                if mode == 1:
                    if k == "muxed": view_rows.append(r)
                elif mode == 2:
                    if k == "video": view_rows.append(r)
                elif mode == 3:
                    if k == "audio": view_rows.append(r)
            
            sel_id = self._selected_muxed_id
            if mode == 2: sel_id = self._selected_video_id
            elif mode == 3: sel_id = self._selected_audio_id
            
            self._populate_table(self.table, view_rows, sel_id)

        self._update_label()
        self.selectionChanged.emit()

    def _populate_table(self, table: QTableWidget, rows: list[dict], selected_id: str | None):
        table.setRowCount(len(rows))
        table.setProperty("_rows", rows)
        
        for i, r in enumerate(rows):
            kind = r["kind"]
            
            icon = FluentIcon.VIDEO if kind in ("muxed", "video") else FluentIcon.MUSIC
            
            # Use a widget to ensure centering
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            iw = IconWidget(icon)
            iw.setFixedSize(16, 16)
            layout.addWidget(iw)
            
            item0 = QTableWidgetItem("")
            table.setItem(i, 0, item0)
            table.setCellWidget(i, 0, container)
            
            q_text = f"{r.get('height')}p" if r.get("height") else f"{int(r.get('abr') or 0)}kbps"
            # Badges for Quality Column (only HDR)
            q_badges = []
            if r.get("dynamic_range") and "HDR" in str(r.get("dynamic_range")):
                q_badges.append(("HDR", "blue"))
            
            q_w = QualityCellWidget(q_badges, q_text, parent=table, alignment=Qt.AlignmentFlag.AlignCenter)
            table.setCellWidget(i, 1, q_w)
            
            # Detail Column: Tags + Size/Ext
            detail_tags = _analyze_format_tags(r)
            
            sz = _format_size(r.get("filesize"))
            ext = r.get("ext")
            
            # Construct main text for details
            detail_text = f"{ext} • {sz}"
            
            # Use QualityCellWidget for Details too
            # We want left alignment generally for details but user requested centered visuals earlier.
            # However, for badges flow, Left or Center?
            # User said "center alignment to achieve visual optimization" previously.
            # Let's keep Center for consistency.
            d_w = QualityCellWidget(detail_tags, detail_text, parent=table, alignment=Qt.AlignmentFlag.AlignCenter)
            
            item2 = QTableWidgetItem("")
            table.setItem(i, 2, item2)
            table.setCellWidget(i, 2, d_w)
            
        self._highlight_table_rows(table, {selected_id} if selected_id else set())

    def _highlight_table_rows(self, table: QTableWidget, selected_ids: set[str]):
        rows = table.property("_rows") or []
        for i in range(table.rowCount()):
            # Reset style
            for j in range(3):
                it = table.item(i, j)
                if it: 
                    it.setBackground(QBrush())
                    it.setForeground(QBrush()) # Default
            
            if i < len(rows):
                fid = rows[i]["format_id"]
                if fid in selected_ids and fid:
                    for j in range(3):
                        it = table.item(i, j)
                        if it: 
                            it.setBackground(QColor("#E8E8E8"))
                            it.setForeground(QColor(0,0,0))

    def _on_table_clicked(self, row, col):
        rows = self.table.property("_rows")
        if not rows or row >= len(rows): return
        
        r = rows[row]
        fid = r["format_id"]
        mode = self.mode_combo.currentIndex()
        
        if mode == 1: self._selected_muxed_id = fid
        elif mode == 2: self._selected_video_id = fid
        elif mode == 3: self._selected_audio_id = fid
        
        self._highlight_table_rows(self.table, {fid})
        self._update_label()
        self.selectionChanged.emit()

    def _on_video_table_clicked(self, row, col):
        rows = self.video_table.property("_rows")
        if not rows or row >= len(rows): return
        self._selected_video_id = rows[row]["format_id"]
        self._highlight_table_rows(self.video_table, {self._selected_video_id})
        self._update_label()
        self.selectionChanged.emit()

    def _on_audio_table_clicked(self, row, col):
        rows = self.audio_table.property("_rows")
        if not rows or row >= len(rows): return
        self._selected_audio_id = rows[row]["format_id"]
        self._highlight_table_rows(self.audio_table, {self._selected_audio_id})
        self._update_label()
        self.selectionChanged.emit()

    def _update_highlight(self):
        # Deprecated by _highlight_table_rows but kept for safety if called elsewhere (unlikely)
        pass

    def _update_label(self):
        mode = self.mode_combo.currentIndex()
        label = self.selection_label
        
        if mode == 1:
            label.setText("已选：整合流" if self._selected_muxed_id else "请选择：整合流")
        elif mode == 2:
            label.setText("已选：视频流" if self._selected_video_id else "请选择：视频流")
        elif mode == 3:
            label.setText("已选：音频流" if self._selected_audio_id else "请选择：音频流")
        else:
            if self._selected_video_id and self._selected_audio_id:
                label.setText("已选：视频流 + 音频流")
            elif self._selected_video_id:
                label.setText("已选：视频流（将自动匹配最佳音频）")
            elif self._selected_audio_id:
                label.setText("已选：音频流（请再选择一个视频流）")
            else:
                label.setText("未选择")

    def get_selection_result(self) -> dict:
        """Returns {format: str, extra_opts: dict} or {} if invalid."""
        # Fix: Use self._current_mode instead of accessing routeKey() on items directly
        if getattr(self, "_current_mode", "simple") == "simple":
            sel = self.simple_widget.get_current_selection()
            if not sel: return {}
            return {"format": sel["format"], "extra_opts": sel["extra"]}
        else:
            # Advanced
            v = self._selected_video_id
            a = self._selected_audio_id
            m = self._selected_muxed_id
            
            opts = {}
            if m:
                opts["format"] = m
            elif v and a:
                opts["format"] = f"{v}+{a}"
                # Find ext to decide container
                vext = next((r["ext"] for r in self._rows if r["format_id"]==v), "mp4")
                aext = next((r["ext"] for r in self._rows if r["format_id"]==a), "m4a")
                merge = _choose_lossless_merge_container(vext, aext)
                if merge: opts["merge_output_format"] = merge
            elif v:
                opts["format"] = v
            elif a:
                opts["format"] = a
            else:
                return {} # Nothing
                
            return {"format": opts["format"], "extra_opts": opts.get("merge_output_format") and {"merge_output_format": opts["merge_output_format"]} or {}}

    def get_summary_text(self) -> str:
        """Returns a human-readable summary of the current selection."""
        if getattr(self, "_current_mode", "simple") == "simple":
            # Simple mode: use the checked radio button text
            btn = self.simple_widget.btn_group.checkedButton()
            return btn.text() if btn else "未选择"
        else:
            # Advanced mode: use the label text
            return self.selection_label.text().replace("已选：", "")