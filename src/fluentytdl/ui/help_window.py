from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, 
    QStackedWidget, QFrame
)

from qfluentwidgets import (
    FluentWindow, SubtitleLabel, NavigationInterface, NavigationItemPosition,
    FluentIcon, CardWidget, StrongBodyLabel, BodyLabel, PrimaryPushButton,
    ImageLabel, Theme, isDarkTheme, SmoothScrollDelegate, ScrollArea,
    SettingCardGroup, SettingCard
)

import markdown

from ..utils.paths import doc_path, resource_path

# CSS for Markdown styling - Card-Based UI (Fluent Settings Style)
# Optimized for readability with color hierarchy and DataGrid-style tables
MARKDOWN_CSS = """
/* ========== Base Container ========== */
QTextBrowser {
    font-family: "Segoe UI Variable", "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 14px;
    line-height: 1.6;
    padding: 30px 50px;
    border: none;
    background-color: transparent;
    color: #5e5e5e;  /* Secondary text color for body */
}

/* ========== Hero Title ========== */
h1 {
    font-size: 28px;
    font-weight: 600;
    margin: 0 0 8px 0;
    color: #202020;  /* Primary title color */
    letter-spacing: -0.4px;
}

/* Subtitle - immediately after H1 */
h1 + p {
    font-size: 14px;
    color: #767676;  /* Tertiary text color */
    margin: 0 0 28px 0;
    line-height: 1.5;
}

/* ========== Section Cards (H2) ========== */
h2 {
    font-size: 16px;
    font-weight: 600;
    margin: 28px 0 14px 0;
    padding: 0;
    color: #202020;
    background: none;
    border: none;
    letter-spacing: 0.1px;
}

/* ========== Step Cards (H3) - Main UI Component ========== */
h3 {
    font-size: 14px;
    font-weight: 600;
    margin: 0;
    padding: 14px 18px;
    color: #202020;
    background-color: #FAFAFA;
    border: 1px solid #E8E8E8;
    border-bottom: none;
    border-radius: 8px 8px 0 0;
}

/* Content following H3 - forms the card body */
h3 + p, h3 + ul, h3 + ol, h3 + table {
    margin: 0;
    padding: 14px 18px 18px 18px;
    background-color: #FFFFFF;
    border: 1px solid #E8E8E8;
    border-top: none;
    border-radius: 0 0 8px 8px;
    margin-bottom: 20px;
}

/* ========== Body Text ========== */
p {
    margin: 0 0 14px 0;
    color: #5e5e5e;  /* Secondary color - softer than title */
    line-height: 1.7;
    font-size: 14px;
}

/* ========== Lists ========== */
ul, ol {
    margin: 8px 0;
    padding-left: 20px;
}
li {
    margin-bottom: 8px;
    color: #5e5e5e;
    line-height: 1.65;
    font-size: 14px;
}

/* ========== InfoBar (Blockquote) - Key Tips ========== */
blockquote {
    margin: 14px 0;
    padding: 14px 18px;
    background-color: #EBF5FF;
    border-left: 3px solid #0078D4;
    border-radius: 6px;
    font-size: 13px;
    color: #202020;
    font-style: normal;
}
blockquote strong {
    color: #0078D4;
}

/* ========== DataGrid Style Tables (No vertical borders) ========== */
table {
    width: 100%;
    margin: 0;
    border-collapse: collapse;  /* Changed from separate */
    border: none;  /* Remove outer border */
    font-size: 13px;
    background-color: transparent;
}
th {
    background-color: transparent;  /* Transparent header */
    color: #767676;  /* Subtle header text */
    font-weight: 600;
    font-size: 12px;
    padding: 10px 14px;
    text-align: left;
    border-bottom: 1px solid #E0E0E0;  /* Only bottom border */
    border-top: none;
    border-left: none;
    border-right: none;
}
td {
    padding: 12px 14px;
    color: #5e5e5e;
    border-bottom: 1px solid #F0F0F0;  /* Very subtle row separator */
    border-top: none;
    border-left: none;
    border-right: none;
    vertical-align: top;
    line-height: 1.55;
}
tr:last-child td {
    border-bottom: none;
}

/* ========== Code - Styled Inline ========== */
code {
    font-family: "Cascadia Code", "Consolas", monospace;
    background-color: #F3F3F3;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
    color: #333333;
    border: none;
}

/* ========== Code Blocks ========== */
pre {
    background-color: #2D2D2D;
    padding: 16px 20px;
    border-radius: 8px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 13px;
    color: #D4D4D4;
    margin: 14px 0;
    overflow-x: auto;
}

/* ========== Horizontal Rules ========== */
hr {
    border: none;
    height: 1px;
    background-color: #EEEEEE;
    margin: 28px 0;
}

/* ========== Footer ========== */
blockquote:last-of-type {
    background-color: #FAFAFA;
    border-left-color: #CCCCCC;
    font-size: 12px;
    color: #999999;
    margin-top: 36px;
}

/* ========== Strong/Bold - Brand Color ========== */
strong {
    font-weight: 600;
    color: #0078D4;
}
"""

class WizardCard(CardWidget):
    """Single step card for the Welcome Wizard."""
    
    def __init__(self, title: str, content: str, icon: FluentIcon, parent=None):
        super().__init__(parent)
        self.v_layout = QVBoxLayout(self)
        self.v_layout.setContentsMargins(30, 40, 30, 40)
        self.v_layout.setSpacing(20)
        self.v_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Icon Area (Placeholder for real image, using large icon for now)
        self.icon_label = ImageLabel(str(resource_path("assets", "logo.png")), self)
        self.icon_label.setFixedSize(80, 80)
        self.icon_label.setScaledContents(True)
        # Fallback if logo not found/valid, use FluentIcon
        if not resource_path("assets", "logo.png").exists():
            # We can't easily put FluentIcon in ImageLabel, so skip
            pass
            
        self.title_label = SubtitleLabel(title, self)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.content_label = BodyLabel(content, self)
        self.content_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_label.setWordWrap(True)
        self.content_label.setTextColor(QColor(120, 120, 120), QColor(150, 150, 150))
        
        self.v_layout.addStretch(1)
        self.v_layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignCenter)
        self.v_layout.addWidget(self.title_label, 0, Qt.AlignmentFlag.AlignCenter)
        self.v_layout.addWidget(self.content_label, 0, Qt.AlignmentFlag.AlignCenter)
        self.v_layout.addStretch(1)

class WelcomeGuideWidget(QWidget):
    """The Quick Start Wizard Page."""
    
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(40, 40, 40, 40)
        
        # Stack for steps
        self.stack = QStackedWidget(self)
        
        # Step 1: Welcome
        self.step1 = WizardCard(
            "欢迎使用 FluentYTDL Pro",
            "分享精彩，从未如此简单。\n全能、极速、现代化的视频下载工具。\n只需一分钟，带您解锁最佳使用姿势。",
            FluentIcon.HOME
        )
        
        # Step 2: Dependencies
        self.step2 = WizardCard(
            "准备工作与依赖",
            "1. 核心组件: 软件已内置 yt-dlp、FFmpeg 和 deno，开箱即用。\n"
            "2. 关键建议: 强烈推荐安装 Firefox 浏览器 并登录 YouTube 账号，\n"
            "这是目前最稳定、免配置的下载方案。",
            FluentIcon.SETTING
        )
        
        # Step 3: How to Download
        self.step3 = WizardCard(
            "两种下载姿势",
            "• 懒人模式: 在设置中开启“剪贴板自动识别”，复制链接即刻弹窗（推荐！）。\n"
            "• 手动模式: 在主页搜索栏粘贴链接，回车即可。",
            FluentIcon.PASTE
        )

        # Step 4: Cookies (Critical Tip)
        self.step_cookies = WizardCard(
            "解锁限制与 Cookie",
            "遇到“需要登录”或“会员视频”？\n"
            "✅ Firefox 用户: 软件通常能自动读取无需配置。\n"
            "🔄 其他浏览器: 请使用插件 ('Get cookies.txt LOCALLY') 导出 Netscape 格式文件，并在设置中手动导入。",
            FluentIcon.PEOPLE
        )
        
        # Step 5: Advanced
        self.step4 = WizardCard(
            "简易与专业并行",
            "• 默认智能选择最佳画质。\n"
            "• 专家模式: 解析后点击“选择格式”，体验独家 A+B 模式 —— \n"
            "随意组合 4K 视频流与 Hi-Res 音频流，定制您的完美文件。",
            FluentIcon.VIDEO
        )
        
        self.stack.addWidget(self.step1)
        self.stack.addWidget(self.step2)
        self.stack.addWidget(self.step3)
        self.stack.addWidget(self.step_cookies)
        self.stack.addWidget(self.step4)
        
        self.layout.addWidget(self.stack, 1)
        
        # Navigation Buttons
        btn_layout = QHBoxLayout()
        self.skip_btn = PrimaryPushButton("跳过引导", self)
        self.skip_btn.clicked.connect(self.finished)
        # Style skip button to look less prominent? No, keep it standard for now.
        
        self.prev_btn = PrimaryPushButton("上一步", self)
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self._prev_step)
        
        self.next_btn = PrimaryPushButton("下一步", self)
        self.next_btn.clicked.connect(self._next_step)
        
        btn_layout.addWidget(self.skip_btn)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.prev_btn)
        btn_layout.addWidget(self.next_btn)
        
        self.layout.addLayout(btn_layout)

    def _prev_step(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
        self._update_buttons()

    def _next_step(self):
        idx = self.stack.currentIndex()
        if idx < self.stack.count() - 1:
            self.stack.setCurrentIndex(idx + 1)
        else:
            self.finished.emit()
        self._update_buttons()

    def _update_buttons(self):
        idx = self.stack.currentIndex()
        total = self.stack.count()
        
        self.prev_btn.setEnabled(idx > 0)
        
        if idx == total - 1:
            self.next_btn.setText("开始使用")
        else:
            self.next_btn.setText("下一步")

class ManualReaderWidget(ScrollArea):
    """User Manual Page built with native Fluent UI components."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.view)
        self.vBoxLayout.setContentsMargins(36, 20, 36, 36)
        self.vBoxLayout.setSpacing(20)
        
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setObjectName("manualScrollArea")
        
        self._initUI()
    
    def _initUI(self):
        # ========== Hero Section ==========
        self.titleLabel = SubtitleLabel("FluentYTDL Pro 用户指南", self.view)
        self.subtitleLabel = BodyLabel("从入门到精通的完整操作手册", self.view)
        self.subtitleLabel.setTextColor(QColor(118, 118, 118), QColor(150, 150, 150))
        
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.subtitleLabel)
        self.vBoxLayout.addSpacing(10)
        
        # ========== Quick Start Group ==========
        self.quickStartGroup = SettingCardGroup("快速入门", self.view)
        
        self.envCard = SettingCard(
            FluentIcon.DEVELOPER_TOOLS,
            "环境准备",
            "软件内置核心组件（yt-dlp、FFmpeg、Deno），开箱即用。推荐使用 Firefox 登录 YouTube。",
            self.quickStartGroup
        )
        self.lazyModeCard = SettingCard(
            FluentIcon.PASTE,
            "懒人模式",
            "在 设置 → 自动化 中开启「剪贴板自动识别」，复制链接即可自动弹出解析窗口。",
            self.quickStartGroup
        )
        self.downloadCard = SettingCard(
            FluentIcon.DOWNLOAD,
            "确认下载",
            "点击弹窗中的「下载」按钮，默认自动选择最佳画质。",
            self.quickStartGroup
        )
        
        self.quickStartGroup.addSettingCard(self.envCard)
        self.quickStartGroup.addSettingCard(self.lazyModeCard)
        self.quickStartGroup.addSettingCard(self.downloadCard)
        self.vBoxLayout.addWidget(self.quickStartGroup)
        
        # ========== Core Features Group ==========
        self.coreGroup = SettingCardGroup("核心功能", self.view)
        
        self.basicDownloadCard = SettingCard(
            FluentIcon.LINK,
            "基本下载",
            "支持视频、播放列表、频道页链接。粘贴链接后回车即可解析。",
            self.coreGroup
        )
        self.abModeCard = SettingCard(
            FluentIcon.MIX_VOLUMES,
            "A+B 专业模式",
            "在解析弹窗中点击「选择格式」，可自由组合视频流（如 4K）和音频流（如 Hi-Res）。",
            self.coreGroup
        )
        self.batchCard = SettingCard(
            FluentIcon.CHECKBOX,
            "批量管理",
            "在下载列表中使用「批量选择」，一键暂停、开始或删除多个任务。",
            self.coreGroup
        )
        
        self.coreGroup.addSettingCard(self.basicDownloadCard)
        self.coreGroup.addSettingCard(self.abModeCard)
        self.coreGroup.addSettingCard(self.batchCard)
        self.vBoxLayout.addWidget(self.coreGroup)
        
        # ========== Advanced Settings Group ==========
        self.advancedGroup = SettingCardGroup("高级配置", self.view)
        
        self.updateSourceCard = SettingCard(
            FluentIcon.GLOBE,
            "组件更新源",
            "在 设置 → 核心组件 中可选择 GitHub（官方）或 GHProxy（加速镜像）。",
            self.advancedGroup
        )
        self.jsRuntimeCard = SettingCard(
            FluentIcon.CODE,
            "JavaScript 运行时",
            "yt-dlp 需要 JS 运行时解密参数。软件内置 Deno 支持，也可指定 Node/Bun 路径。",
            self.advancedGroup
        )
        self.poTokenCard = SettingCard(
            FluentIcon.FINGERPRINT,
            "PO Token（实验性）",
            "用于通过 YouTube 的 Proof of Origin 验证。在高级设置中可粘贴 Token。",
            self.advancedGroup
        )
        
        self.advancedGroup.addSettingCard(self.updateSourceCard)
        self.advancedGroup.addSettingCard(self.jsRuntimeCard)
        self.advancedGroup.addSettingCard(self.poTokenCard)
        self.vBoxLayout.addWidget(self.advancedGroup)
        
        # ========== Troubleshooting Group ==========
        self.troubleGroup = SettingCardGroup("错误查询手册", self.view)
        
        self.error403Card = SettingCard(
            FluentIcon.CANCEL,
            "HTTP 403 / 访问被拒",
            "IP 被风控。解决：更新 Cookies（推荐 Firefox）、更换代理节点、等待 30 分钟。",
            self.troubleGroup
        )
        self.errorFFmpegCard = SettingCard(
            FluentIcon.DEVELOPER_TOOLS,
            "ffmpeg not found",
            "缺少 FFmpeg 组件。解决：在 设置 → 核心组件 中点击「检查更新」。",
            self.troubleGroup
        )
        self.errorTimeoutCard = SettingCard(
            FluentIcon.CLOUD,
            "timed out / 网络超时",
            "无法连接到 YouTube。解决：检查代理软件是否开启「系统代理」模式。",
            self.troubleGroup
        )
        self.errorLoginCard = SettingCard(
            FluentIcon.PEOPLE,
            "Sign in / private / 需要登录",
            "视频需要账号权限。解决：必须导入有效的 Cookies。",
            self.troubleGroup
        )
        
        self.troubleGroup.addSettingCard(self.error403Card)
        self.troubleGroup.addSettingCard(self.errorFFmpegCard)
        self.troubleGroup.addSettingCard(self.errorTimeoutCard)
        self.troubleGroup.addSettingCard(self.errorLoginCard)
        self.vBoxLayout.addWidget(self.troubleGroup)
        
        # ========== Footer ==========
        self.vBoxLayout.addStretch(1)


class HelpWindow(FluentWindow):
    """Independent Help Center Window."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("帮助中心")
        self.resize(900, 650)
        
        # Center on screen
        desktop = self.screen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

        # Init interfaces
        self.guide_interface = WelcomeGuideWidget(self)
        self.guide_interface.setObjectName("welcomeGuideInterface")
        self.guide_interface.finished.connect(self.close) # Guide finished -> close help window (if opened as modal) or just stay? 
        # If opened from main menu, "Start Using" should probably just switch to manual or close.
        # Let's make it switch to manual for now, or just close if it was a standalone dialog.
        # Modified logic: "Finished" signal is mostly for the startup wizard mode.
        
        self.manual_interface = ManualReaderWidget(self)
        self.manual_interface.setObjectName("manual_interface")

        # Add to nav
        self.addSubInterface(
            self.guide_interface,
            FluentIcon.COMPLETED, # Use a 'check' or 'rocket' icon
            "快速入门",
            position=NavigationItemPosition.TOP
        )
        
        self.addSubInterface(
            self.manual_interface,
            FluentIcon.BOOK_SHELF,
            "用户手册",
            position=NavigationItemPosition.TOP
        )

        # Default to guide
        self.stackedWidget.setCurrentWidget(self.guide_interface)
