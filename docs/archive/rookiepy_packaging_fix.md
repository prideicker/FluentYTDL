# rookiepy 打包修复

## 问题诊断

**症状**：
- 本地开发环境：Cookie 提取正常 ✅
- 打包后 exe（其他电脑）：Cookie 提取失败 ❌
- Edge 已安装且登录 YouTube，浏览器已关闭

**根本原因**：
1. `pyproject.toml` 依然声明 `browser-cookie3` 而非 `rookiepy`
2. PyInstaller 打包时未包含 rookiepy 的二进制文件 (`.pyd`)
3. 缺少 PyInstaller hook 来收集 Rust 编译的扩展模块

## 解决方案

### 1. 更新依赖声明

**文件**: `pyproject.toml`

```diff
dependencies = [
  "yt-dlp[default]>=2025.11.12",
  "requests>=2.32.0",
- "browser-cookie3>=0.19.1",
+ "rookiepy>=0.5.6",
  "PySide6>=6.6.0",
  ...
]
```

### 2. 修改 PyInstaller 配置

**文件**: `FluentYTDL.spec`

```python
# -*- mode: python ; coding: utf-8 -*-

# 收集 rookiepy 的二进制文件 (.pyd)
from PyInstaller.utils.hooks import collect_dynamic_libs
rookiepy_binaries = collect_dynamic_libs('rookiepy')

a = Analysis(
    ['E:\\YouTube\\FluentYTDL\\main.py'],
    pathex=['E:\\YouTube\\FluentYTDL\\src'],
    binaries=rookiepy_binaries,  # ← 添加 rookiepy 二进制
    datas=[...],
    hiddenimports=[
        'rookiepy',           # ← 添加隐藏导入
        'rookiepy.edge',
        'rookiepy.chrome',
        'rookiepy.firefox',
        'rookiepy.brave'
    ],
    hookspath=['E:\\YouTube\\FluentYTDL\\scripts'],  # ← 添加 hook 路径
    ...
)
```

### 3. 创建 PyInstaller Hook

**文件**: `scripts/hook-rookiepy.py`

```python
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

# 收集所有动态库（.pyd 文件）
datas = collect_data_files('rookiepy', include_py_files=True)
binaries = collect_dynamic_libs('rookiepy')

# 显式添加 rookiepy 的所有子模块
hiddenimports = [
    'rookiepy',
    'rookiepy.edge',
    'rookiepy.chrome', 
    'rookiepy.firefox',
    'rookiepy.brave',
]
```

### 4. 添加验证工具

**文件**: `scripts/verify_rookiepy_dist.py`

用于验证打包后的 rookiepy 是否正常工作：

```bash
# 打包后在 dist 目录运行
FluentYTDL.exe verify_rookiepy_dist.py
```

检查项：
- ✅ rookiepy 模块导入
- ✅ .pyd 文件存在
- ✅ 各浏览器方法可用
- ✅ 功能测试（Edge Cookie 提取）

## rookiepy 技术细节

### 文件结构

```
rookiepy/
├── __init__.py              # Python 接口
├── rookiepy.pyi             # 类型提示
├── rookiepy.cp311-win_amd64.pyd  # ← 关键！Rust 编译的二进制
└── py.typed
```

### 为什么需要特殊处理

1. **Rust 编译的扩展**：rookiepy 是用 Rust 编写并编译为 `.pyd` 的二进制扩展
2. **动态加载**：`.pyd` 文件在运行时动态加载，PyInstaller 默认不收集
3. **无 Python 依赖**：`pip show rookiepy` 显示 `Requires: ` 为空，因为它是纯二进制

### PyInstaller 收集策略

```python
# 方法 1: 使用 collect_dynamic_libs (推荐)
from PyInstaller.utils.hooks import collect_dynamic_libs
binaries = collect_dynamic_libs('rookiepy')

# 方法 2: 手动指定 (备选)
import rookiepy, os
pyd_path = os.path.join(os.path.dirname(rookiepy.__file__), '*.pyd')
binaries = [(pyd_path, 'rookiepy')]
```

## 测试验证

### 本地测试

```bash
# 检查本地 rookiepy
python scripts/check_rookiepy.py
```

**预期输出**：
```
✅ rookiepy 导入成功
✅ rookiepy.edge 可用
✅ rookiepy.chrome 可用
⚠️  提取失败: Chrome cookies from version v130 can be decrypted only when running as admin
   （这是正常的，需要管理员权限）
```

### 打包测试

```bash
# 1. 打包
scripts\build_windows.ps1

# 2. 进入打包目录
cd dist\FluentYTDL_build_*

# 3. 验证 rookiepy
.\FluentYTDL.exe verify_rookiepy_dist.py
```

**预期输出**：
```
1. 检查 rookiepy 导入...
   ✅ 导入成功
   ✅ 找到 .pyd 文件:
      - rookiepy.cp311-win_amd64.pyd (2345.6 KB)

2. 检查浏览器支持...
   ✅ Edge 支持
   ✅ Chrome 支持
   ✅ Firefox 支持
   ✅ Brave 支持

3. 功能测试 (Edge)...
   ✅ 功能正常（需要管理员权限，这是预期行为）

✅ rookiepy 验证通过！
```

### 全新 Win11 测试

1. 将打包后的整个文件夹复制到测试电脑
2. 确保 Edge 已安装并登录 YouTube
3. 完全关闭 Edge 浏览器
4. 运行 `FluentYTDL.exe`
5. 进入设置页，选择"自动提取" → "Edge"
6. 点击"立即刷新"

**预期结果**：
- 如果 Edge < v130：直接提取成功
- 如果 Edge >= v130：弹出 UAC，点"是"后提取成功

## 常见问题

### Q: 为什么本地能用，打包后不行？

**A**: 本地环境中 Python 可以找到 site-packages 中的 `.pyd` 文件，但打包后需要显式告诉 PyInstaller 包含这些二进制文件。

### Q: hiddenimports 够用吗？

**A**: 不够。`hiddenimports` 只处理 Python 代码导入，不会收集二进制扩展（`.pyd`, `.so`, `.dll`）。必须使用 `binaries` 参数或 `collect_dynamic_libs()`。

### Q: 为什么需要 hook 文件？

**A**: Hook 文件让 PyInstaller 知道如何正确处理特定包。rookiepy 作为 Rust 扩展需要特殊处理，hook 文件提供了标准化的收集方法。

### Q: 如何确认 .pyd 文件被打包？

**A**: 
1. 解压打包后的 exe（如果是 onefile）或检查 `_internal` 目录
2. 查找 `rookiepy.cp311-win_amd64.pyd` 文件
3. 运行 `verify_rookiepy_dist.py` 验证脚本

### Q: 其他电脑需要安装 Python 吗？

**A**: 不需要。PyInstaller 打包后包含了 Python 运行时和所有依赖（包括 rookiepy 的二进制文件）。

## 相关文件修改清单

- ✅ `pyproject.toml`: browser-cookie3 → rookiepy
- ✅ `FluentYTDL.spec`: 添加 rookiepy 二进制收集
- ✅ `scripts/hook-rookiepy.py`: PyInstaller hook
- ✅ `scripts/check_rookiepy.py`: 本地验证脚本
- ✅ `scripts/verify_rookiepy_dist.py`: 打包后验证脚本
- ✅ `scripts/build_windows.ps1`: 自动复制验证脚本

## 参考文档

- [PyInstaller Manual - Hooks](https://pyinstaller.org/en/stable/hooks.html)
- [PyInstaller - Collecting Dynamic Libraries](https://pyinstaller.org/en/stable/hooks.html#collect-dynamic-libs)
- [rookiepy GitHub](https://github.com/thewh1teagle/rookie)
