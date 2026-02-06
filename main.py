from __future__ import annotations

import os
import sys
from pathlib import Path

# === 优先检测特殊模式（必须在导入任何GUI库之前） ===

# 检测管理员模式（整个程序以管理员身份运行，用于 Cookie 提取）
IS_ADMIN_MODE = "--admin-mode" in sys.argv
if IS_ADMIN_MODE:
    # 移除 --admin-mode 参数，避免传递给 Qt
    sys.argv = [arg for arg in sys.argv if arg != "--admin-mode"]

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
    from fluentytdl.core.config_manager import config_manager
    import threading

    # 2. 创建主窗口
    window = MainWindow()
    window.show()

    # === 3. 在后台线程中启动 POT Provider 服务 (完全不阻塞主界面) ===
    def start_pot_service_thread():
        import time
        time.sleep(1)  # 延迟 1 秒（从3秒改为1秒，减少等待时间）
        
        try:
            if config_manager.get("pot_provider_enabled", True):
                from fluentytdl.youtube.pot_manager import pot_manager
                from loguru import logger
                
                # 尝试启动服务（带重试）
                for attempt in range(3):
                    if pot_manager.start_server():
                        logger.info("POT Provider 服务已启动")
                        break
                    elif attempt < 2:
                        logger.debug(f"POT Provider 启动尝试 {attempt + 1} 失败，1秒后重试...")
                        time.sleep(1)
                    else:
                        logger.warning("POT Provider 服务启动失败：已达到最大重试次数")
        except Exception as e:
            try:
                from loguru import logger
                logger.warning(f"POT Provider 服务启动异常: {e}")
            except:
                pass
    
    # 在后台线程启动 POT 服务
    pot_thread = threading.Thread(target=start_pot_service_thread, daemon=True)
    pot_thread.start()

    # === 4. Cookie Sentinel: 启动时静默预提取 (Best-Effort) ===
    def start_cookie_sentinel_thread():
        import time
        time.sleep(2)  # 延迟 2 秒，不阻塞主界面
        
        try:
            from fluentytdl.auth.cookie_sentinel import cookie_sentinel
            cookie_sentinel.silent_refresh_on_startup()
        except Exception as e:
            try:
                from loguru import logger
                logger.debug(f"Cookie Sentinel 启动失败（预期行为）: {e}")
            except:
                pass
    
  # 在后台线程启动 Cookie Sentinel
    cookie_thread = threading.Thread(target=start_cookie_sentinel_thread, daemon=True, name="CookieSentinel-Startup")
    cookie_thread.start()


    # 4. 进入事件循环
    exit_code = app.exec()

    # === 5. 停止 POT Provider 服务 ===
    try:
        from fluentytdl.youtube.pot_manager import pot_manager
        pot_manager.stop_server()
    except Exception:
        pass

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
