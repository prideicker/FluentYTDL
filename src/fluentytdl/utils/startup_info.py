"""
FluentYTDL 启动信息日志

每次应用启动时记录软件版本、Python/Qt 版本、安装类型和所有组件版本。
便于排查问题时快速了解运行环境。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def detect_install_type() -> str:
    """检测安装类型: setup (Program Files) / full (便携) / dev (开发)。"""
    if not getattr(sys, "frozen", False):
        return "dev"

    exe_path = Path(sys.executable).resolve()
    exe_str = str(exe_path).lower()

    program_files = Path.home().parent  # fallback
    import os

    program_files = os.environ.get("ProgramFiles", "C:\\Program Files").lower()
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)").lower()

    if exe_str.startswith(program_files) or exe_str.startswith(program_files_x86):
        return "setup"
    return "full"


def _quick_detect_version(key: str, exe_path: Path) -> str:
    """快速检测组件版本，3 秒超时避免阻塞启动。"""
    if not exe_path.exists():
        return "未安装"

    import re

    cmd_map = {
        "yt-dlp": [str(exe_path), "--version"],
        "ffmpeg": [str(exe_path), "-version"],
        "deno": [str(exe_path), "--version"],
        "pot-provider": [str(exe_path), "--version"],
        "ytarchive": [str(exe_path), "--version"],
        "atomicparsley": [str(exe_path), "--version"],
    }

    cmd = cmd_map.get(key, [str(exe_path), "--version"])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        output = (result.stdout + result.stderr).strip()
        if not output:
            return "已安装 (无版本输出)"

        first_line = output.split("\n")[0].strip()

        # 各工具版本解析
        if key == "yt-dlp":
            # yt-dlp 直接输出版本号如 "2025.11.12"
            return first_line
        elif key == "ffmpeg":
            # ffmpeg version n7.1.3-40-gcddd06f3b9-20260219
            m = re.search(r"ffmpeg version ([^\s]+)", first_line)
            if m:
                raw = m.group(1).lstrip("nN")
                vm = re.match(r"(\d+(?:\.\d+)*)", raw)
                return vm.group(1) if vm else raw
        elif key == "deno":
            # deno 1.38.0 (release, x86_64-pc-windows-msvc)
            m = re.search(r"deno (\d+\.\d+\.\d+)", first_line)
            if m:
                return m.group(1)
        elif key == "pot-provider":
            m = re.search(r"(\d+\.\d+\.\d+)", first_line)
            if m:
                return m.group(1)
        elif key == "ytarchive":
            m = re.search(r"v?(\d+\.\d+\.\d+)", first_line)
            if m:
                return m.group(1)
        elif key == "atomicparsley":
            m = re.search(r"(\d{8}\.\d{6})", first_line)
            if m:
                return m.group(1)

        return first_line[:40]  # 截断避免过长
    except subprocess.TimeoutExpired:
        return "超时"
    except Exception:
        return "检测失败"


def log_startup_info() -> None:
    """记录启动版本信息到日志。"""
    from fluentytdl.utils.logger import logger

    try:
        from fluentytdl import __version__
    except ImportError:
        __version__ = "unknown"

    try:
        import PySide6

        qt_version = PySide6.QtCore.qVersion()
        pyside_version = PySide6.__version__
    except Exception:
        qt_version = "unknown"
        pyside_version = "unknown"

    install_type = detect_install_type()
    app_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()

    logger.info("=" * 50)
    logger.info(f"  FluentYTDL {__version__} 启动")
    logger.info(
        f"  Python {sys.version.split()[0]} | PySide6 {pyside_version} | Qt {qt_version}"
    )
    logger.info(f"  安装类型: {install_type} | 路径: {app_dir}")
    logger.info("-" * 50)

    # 组件版本检测
    from fluentytdl.utils.paths import frozen_app_dir as _frozen_app_dir

    if getattr(sys, "frozen", False):
        base = _frozen_app_dir() / "bin"
    else:
        base = app_dir / "assets" / "bin"

    components = [
        ("yt-dlp", "yt-dlp/yt-dlp.exe"),
        ("ffmpeg", "ffmpeg/ffmpeg.exe"),
        ("deno", "deno/deno.exe"),
        ("pot-provider", "pot-provider/bgutil-pot-provider.exe"),
        ("ytarchive", "ytarchive/ytarchive.exe"),
        ("atomicparsley", "atomicparsley/AtomicParsley.exe"),
    ]

    for key, rel_path in components:
        exe_path = base / rel_path
        version = _quick_detect_version(key, exe_path)
        logger.info(f"  {key:<16} {version}")

    logger.info("=" * 50)
