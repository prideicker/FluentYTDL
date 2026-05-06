# -*- mode: python ; coding: utf-8 -*-
"""
FluentYTDL 更新器 PyInstaller 蓝图

独立的极简更新器，不依赖 Qt 或 fluentytdl 包。
仅包含 Python 标准库 + py7zr（7z 解压支持）。

打包命令:
    pyinstaller scripts/updater.spec

输出: dist/updater/updater.exe (onedir) 或 dist/updater.exe (onefile)
"""

import os
import sys

# ----------------------------------------------------------------------------
# 1. 入口和路径
# ----------------------------------------------------------------------------
spec_dir = SPECPATH if 'SPECPATH' in dir() else os.path.abspath(os.path.dirname(__file__))
entry_script = os.path.join(spec_dir, '..', 'src', 'fluentytdl', 'core', 'updater.py')

# ----------------------------------------------------------------------------
# 2. Hidden imports (py7zr 用于 7z 解压)
#    py7zr 有大量子模块 (compressor, archiveinfo, properties, callbacks 等)，
#    仅列几个无法在运行时成功 import。使用 collect_submodules 全量收集。
# ----------------------------------------------------------------------------
from PyInstaller.utils.hooks import collect_submodules
hiddenimports = collect_submodules('py7zr')

# ----------------------------------------------------------------------------
# 3. Analysis
# ----------------------------------------------------------------------------
a = Analysis(
    [entry_script],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6', 'PyQt5', 'PyQt6', 'tkinter', 'matplotlib',
        'numpy', 'scipy', 'pandas', 'PIL', 'cv2',
        'qfluentwidgets', 'qframelesswindow',
    ],
    noarchive=False,
    optimize=0,
)

# ----------------------------------------------------------------------------
# 4. 构建
# ----------------------------------------------------------------------------
pyz = PYZ(a.pure)

# 使用 onefile 模式：updater.exe 是单个独立文件，便于分发
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    exclude_binaries=False,
    name='updater',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 不使用 UPX，避免杀软误报
    console=False,  # 无窗口模式，日志写入 logs/updater.log
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
