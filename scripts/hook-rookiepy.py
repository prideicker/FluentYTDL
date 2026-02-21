"""
PyInstaller hook for rookiepy

rookiepy 是 Rust 编译的二进制包，需要确保其 .pyd 文件被包含
"""

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# 收集所有动态库（.pyd 文件）
datas = collect_data_files("rookiepy", include_py_files=True)
binaries = collect_dynamic_libs("rookiepy")

# 显式添加 rookiepy 的所有子模块
hiddenimports = [
    "rookiepy",
    "rookiepy.edge",
    "rookiepy.chrome",
    "rookiepy.firefox",
    "rookiepy.brave",
]
