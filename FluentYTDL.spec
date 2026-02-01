# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import copy_metadata

datas = [('E:\\YouTube\\FluentYTDL\\docs', 'docs'), ('E:\\YouTube\\FluentYTDL\\assets\\logo.ico', 'assets'), ('E:\\YouTube\\FluentYTDL\\assets\\logo.png', 'assets')]
hiddenimports = []
datas += copy_metadata('rookiepy')
hiddenimports += collect_submodules('fluentytdl')
hiddenimports += collect_submodules('rookiepy')


a = Analysis(
    ['E:\\YouTube\\FluentYTDL\\main.py'],
    pathex=['E:\\YouTube\\FluentYTDL\\src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FluentYTDL',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='E:\\YouTube\\FluentYTDL\\build\\version_info.txt',
    icon=['E:\\YouTube\\FluentYTDL\\assets\\logo.ico'],
)
