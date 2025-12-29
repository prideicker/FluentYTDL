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

from ..utils.paths import doc_path, resource_path

# CSS for Markdown styling (Light/Dark adaptive)
MARKDOWN_CSS = """
/* Base font settings */
QTextBrowser {
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 15px;
    line-height: 1.6;
    padding: 20px;
    border: none;
    background-color: transparent;
}

/* Headers */
h1 { font-size: 28px; font-weight: 600; margin-bottom: 16px; color: palette(text); }
h2 { font-size: 22px; font-weight: 600; margin-top: 24px; margin-bottom: 12px; border-bottom: 1px solid palette(mid); padding-bottom: 6px; color: palette(text); }
h3 { font-size: 18px; font-weight: 600; margin-top: 16px; margin-bottom: 8px; color: palette(text); }

/* Text elements */
p { margin-bottom: 12px; color: palette(text); }
li { margin-bottom: 6px; color: palette(text); }
strong { font-weight: 700; color: palette(highlight); }
a { color: palette(link); text-decoration: none; }

/* Code blocks (approximated with pre/code) */
pre {
    background-color: palette(alternate-base);
    padding: 12px;
    border-radius: 6px;
    font-family: "Consolas", monospace;
    font-size: 13px;
    color: palette(text);
}
code {
    font-family: "Consolas", monospace;
    background-color: palette(alternate-base);
    padding: 2px 4px;
    border-radius: 4px;
}
blockquote {
    border-left: 4px solid palette(highlight);
    background-color: palette(alternate-base);
    padding: 8px 12px;
    margin: 12px 0;
    color: palette(text);
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
            "这是一款强大且美观的视频下载工具。\n只需 30 秒，带您快速了解核心功能。",
            FluentIcon.HOME
        )
        
        # Step 2: Dependencies
        self.step2 = WizardCard(
            "核心组件管理",
            "软件依赖 yt-dlp 和 FFmpeg 运行。\n我们会自动检查更新，您也可以在“设置 -> 核心组件”中手动管理。\n遇到问题？试试“手动导入”功能。",
            FluentIcon.SETTING
        )
        
        # Step 3: How to Download
        self.step3 = WizardCard(
            "极速下载",
            "最快的方式：\n1. 复制视频链接\n2. 软件自动识别并弹窗\n3. 点击下载\n\n记得在设置中开启“剪贴板自动识别”哦！",
            FluentIcon.PASTE
        )

        # Step 4: Cookies (Critical Tip)
        self.step_cookies = WizardCard(
            "关键提示：Cookies 设置",
            "Cookies (Netscape 格式): 用于下载会员或年龄限制视频。\n"
            "⚠️ 注意: 直接调用 Chrome/Edge 浏览器的 Cookies 通常会失败，"
            "因为 Windows 会对这些文件进行系统级加密保护。\n"
            "✅ 推荐方案: 使用浏览器插件 (如 'Get cookies.txt LOCALLY') 导出为文件，"
            "或使用 Firefox 浏览器。",
            FluentIcon.PEOPLE
        )
        
        # Step 5: Advanced
        self.step4 = WizardCard(
            "专业级控制",
            "需要特定格式？\n在解析弹窗或播放列表中，尝试点击“选择格式”。\n支持独家的 A+B 模式，随意组合视频流与音频流。",
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
    """The Markdown Reader Page."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.browser = QTextBrowser(self)
        self.browser.setOpenExternalLinks(True)
        # Apply CSS
        self.browser.document().setDefaultStyleSheet(MARKDOWN_CSS)
        
        layout.addWidget(self.browser)
        
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
        
        self.browser.setMarkdown(content)


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
