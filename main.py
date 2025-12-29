from __future__ import annotations

import os
import sys
from pathlib import Path

# 解决 Windows 下 QtNetwork HTTPS 可能遇到的 OpenSSL DLL 缺失问题
# 注意：需要在导入 PySide6 相关模块之前设置 PATH
if sys.platform == "win32":
    try:
        import PySide6

        package_dir = os.path.dirname(PySide6.__file__)
        openssl_dir = os.path.join(package_dir, "openssl", "bin")
        if os.path.exists(openssl_dir):
            os.environ["PATH"] = openssl_dir + os.pathsep + os.environ.get("PATH", "")
    except (ImportError, OSError):
        pass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


def main() -> None:
    # Ensure "src" is importable when running from repo root
    root_dir = Path(__file__).resolve().parent
    src_dir = root_dir / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    # === 1. 修改缩放策略 (关键) ===
    # 如觉得太小，可改为 1.5；或删除本行让 Qt/系统自动接管。
    os.environ["QT_SCALE_FACTOR"] = "1.0"
    # 备选：启用自动 HighDPI（通常 Qt6 默认就支持，只有在特殊环境下才需要）
    # os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

    # 1. 创建应用
    app = QApplication(sys.argv)
    app.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings)

    # Set application icon from assets/logo.png if available (comprehensive replacement)
    try:
        root_dir = Path(__file__).resolve().parent
        icon_path = root_dir / "assets" / "logo.png"
        if icon_path.exists():
            from PySide6.QtGui import QIcon

            app.setWindowIcon(QIcon(str(icon_path)))
    except Exception:
        pass

    # === 2. 设置全局字体 (关键) ===
    font = QFont("Microsoft YaHei UI", 9)
    try:
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    except Exception:
        pass
    app.setFont(font)

    # Import UI after QApplication is created to avoid triggering Qt font operations
    # during module import (which can cause QFont warnings if done before app exists).
    # from fluentytdl.ui.main_window import MainWindow
    from fluentytdl.ui.reimagined_main_window import MainWindow

    # 2. 创建主窗口
    window = MainWindow()
    window.show()

    # 3. 进入事件循环
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
