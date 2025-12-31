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
    ImageLabel, Theme, isDarkTheme
)

import markdown

from ..utils.paths import doc_path, resource_path

# CSS for Markdown styling (Light/Dark adaptive)
MARKDOWN_CSS = """
/* Base font settings */
QTextBrowser {
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 14px;
    line-height: 1.6;
    padding: 24px;
    border: none;
    background-color: transparent;
    color: palette(text);
}

/* Headers - Fluent Style */
h1 {
    font-size: 28px;
    font-weight: 600;
    margin-bottom: 20px;
    padding-bottom: 10px;
    border-bottom: 2px solid palette(highlight);
    color: palette(text);
}
h2 {
    font-size: 22px;
    font-weight: 600;
    margin-top: 30px;
    margin-bottom: 15px;
    color: palette(text);
}
h3 {
    font-size: 18px;
    font-weight: 600;
    margin-top: 20px;
    margin-bottom: 10px;
    color: palette(text);
}

/* Text elements */
p { margin-bottom: 12px; color: palette(text); }
li { margin-bottom: 6px; color: palette(text); }
strong { font-weight: 700; color: palette(highlight); }
a { color: palette(link); text-decoration: none; }

/* Tables - Critical for Troubleshooting Guide */
table {
    border-collapse: collapse;
    width: 100%;
    margin-top: 15px;
    margin-bottom: 15px;
    border: 1px solid palette(mid);
}
th {
    background-color: palette(alternate-base);
    color: palette(text);
    padding: 10px 15px;
    border: 1px solid palette(mid);
    font-weight: 700;
    text-align: left;
}
td {
    padding: 10px 15px;
    border: 1px solid palette(mid);
    color: palette(text);
    vertical-align: top;
}

/* Code blocks */
pre {
    background-color: palette(alternate-base);
    padding: 15px;
    border-radius: 6px;
    border: 1px solid palette(mid);
    font-family: "Consolas", "Cascadia Code", monospace;
    font-size: 13px;
    color: palette(text);
    margin: 10px 0;
}
code {
    font-family: "Consolas", "Cascadia Code", monospace;
    background-color: palette(alternate-base);
    padding: 2px 6px;
    border-radius: 4px;
    color: palette(highlight);
}

/* Blockquotes */
blockquote {
    border-left: 4px solid palette(highlight);
    background-color: palette(alternate-base);
    padding: 10px 15px;
    margin: 15px 0;
    color: palette(text); 
    font-style: italic;
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
