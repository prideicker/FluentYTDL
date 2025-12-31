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
    ImageLabel, Theme, isDarkTheme, SmoothScrollDelegate
)

import markdown

from ..utils.paths import doc_path, resource_path

# CSS for Markdown styling - Modern Fluent Design
# Implements: max-width, breathing room, card sections, typography hierarchy, color system
MARKDOWN_CSS = """
/* ========== Base Container ========== */
QTextBrowser {
    font-family: "Segoe UI Variable", "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 14px;
    line-height: 1.7;
    padding: 40px 60px;
    border: none;
    background-color: transparent;
    color: #333333;
}

/* ========== Content Width Constraint ========== */
/* Wrap all content in a virtual reading area */
body {
    max-width: 800px;
    margin: 0 auto;
    padding: 0 20px;
}

/* ========== Hero Section (H1) ========== */
h1 {
    font-size: 32px;
    font-weight: 700;
    margin-top: 10px;
    margin-bottom: 8px;
    padding-bottom: 0;
    border-bottom: none;
    color: #0078D4;
    letter-spacing: -0.5px;
}
/* Subtitle styling for the first paragraph after H1 */
h1 + p {
    font-size: 15px;
    color: #666666;
    margin-bottom: 30px;
    padding-bottom: 20px;
    border-bottom: 1px solid #E0E0E0;
}

/* ========== Section Headers (H2) - Card-like ========== */
h2 {
    font-size: 20px;
    font-weight: 600;
    margin-top: 40px;
    margin-bottom: 20px;
    padding: 16px 20px;
    background: linear-gradient(135deg, #F5F5F5 0%, #FAFAFA 100%);
    border-left: 4px solid #0078D4;
    border-radius: 0 8px 8px 0;
    color: #1A1A1A;
}

/* ========== Subsection Headers (H3) ========== */
h3 {
    font-size: 16px;
    font-weight: 600;
    margin-top: 28px;
    margin-bottom: 12px;
    color: #333333;
    padding-left: 12px;
    border-left: 3px solid #0078D4;
}

/* ========== Body Text ========== */
p {
    margin-bottom: 16px;
    color: #4B4B4B;
    line-height: 1.75;
}

/* ========== Lists with Breathing Room ========== */
ul, ol {
    margin: 16px 0;
    padding-left: 24px;
}
li {
    margin-bottom: 10px;
    color: #4B4B4B;
    line-height: 1.6;
}
li::marker {
    color: #0078D4;
}

/* ========== Emphasis & Links ========== */
strong {
    font-weight: 600;
    color: #0078D4;
}
em {
    font-style: italic;
    color: #555555;
}
a {
    color: #0078D4;
    text-decoration: none;
    border-bottom: 1px dotted #0078D4;
}
a:hover {
    color: #005A9E;
}

/* ========== Important Callouts (Blockquotes) ========== */
blockquote {
    margin: 20px 0;
    padding: 16px 20px;
    background: linear-gradient(135deg, #E8F4FD 0%, #F0F9FF 100%);
    border-left: 4px solid #0078D4;
    border-radius: 0 8px 8px 0;
    color: #1A1A1A;
    font-style: normal;
}
blockquote strong {
    color: #005A9E;
}

/* ========== Tables - Clean Modern Look ========== */
table {
    width: 100%;
    margin: 24px 0;
    border-collapse: separate;
    border-spacing: 0;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
th {
    background: linear-gradient(180deg, #F8F8F8 0%, #F0F0F0 100%);
    color: #1A1A1A;
    font-weight: 600;
    padding: 14px 16px;
    text-align: left;
    border-bottom: 2px solid #E0E0E0;
}
td {
    padding: 12px 16px;
    color: #4B4B4B;
    border-bottom: 1px solid #F0F0F0;
    vertical-align: top;
    line-height: 1.5;
}
tr:last-child td {
    border-bottom: none;
}
tr:hover td {
    background-color: #FAFAFA;
}

/* ========== Code Blocks ========== */
pre {
    background: linear-gradient(180deg, #2D2D2D 0%, #1E1E1E 100%);
    padding: 20px;
    border-radius: 8px;
    font-family: "Cascadia Code", "Consolas", "SF Mono", monospace;
    font-size: 13px;
    color: #D4D4D4;
    margin: 20px 0;
    overflow-x: auto;
}
code {
    font-family: "Cascadia Code", "Consolas", monospace;
    background-color: #F5F5F5;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 13px;
    color: #C41E3A;
}

/* ========== Horizontal Rules ========== */
hr {
    border: none;
    height: 1px;
    background: linear-gradient(90deg, transparent, #E0E0E0, transparent);
    margin: 40px 0;
}

/* ========== Footer/Version Info ========== */
blockquote:last-of-type {
    background: #F8F8F8;
    border-left-color: #888888;
    font-size: 12px;
    color: #888888;
    margin-top: 40px;
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

class ManualReaderWidget(QWidget):
    """The Markdown Reader Page, wrapped in a Fluent Card."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Main layout for the page with margins
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Card container to host the document
        # This provides the correct 'Layer' background (elevated from window background)
        self.card = CardWidget(self)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        
        self.browser = QTextBrowser(self.card)
        self.browser.setOpenExternalLinks(True)
        
        # Apply Fluent-style smooth scrolling overlay
        self.scrollDelegate = SmoothScrollDelegate(self.browser)
        
        # Apply CSS (ensure transparency so Card background shows)
        self.browser.document().setDefaultStyleSheet(MARKDOWN_CSS)
        # Widget style: transparent background, no border
        self.browser.setStyleSheet("background-color: transparent; border: none;")
        
        card_layout.addWidget(self.browser)
        layout.addWidget(self.card)
        
        self.load_manual()

    def load_manual(self):
        # Locate the manual file
        # Priority: localized docs/manuals/USER_MANUAL.md -> resource path
        md_path = doc_path() / "manuals" / "USER_MANUAL.md"
        
        content = "# 用户手册未找到\n\n请检查 `docs/manuals/USER_MANUAL.md` 文件是否存在。"
        if md_path.exists():
            try:
                content = md_path.read_text(encoding="utf-8")
            except Exception as e:
                content = f"# 读取错误\n\n无法读取手册文件: {e}"
        
        # Convert Markdown to HTML with extensions
        # 'extra' includes: tables, fenced_code, footnotes, attr_list, def_list, abbr
        html_content = markdown.markdown(content, extensions=['extra'])
        self.browser.setHtml(html_content)


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
