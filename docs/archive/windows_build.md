# Windows 打包（PyInstaller）

目标：将 FluentYTDL 打包为可分发的 Windows 应用（默认 `onedir`，也支持 `onefile`），并支持把 `yt-dlp` Python 内核 + FFmpeg + JS Runtime 一起带上。

## 1. 约定：内置二进制目录结构

把需要内置的可执行文件放到：

- `assets/bin/ffmpeg/ffmpeg.exe`
- `assets/bin/ffmpeg/ffprobe.exe`（可选但推荐）
- `assets/bin/js/deno.exe`（推荐）
- `assets/bin/js/qjs.exe`（可选）

说明：
- 程序在打包模式下会自动优先使用这些内置工具（无需用户手动填路径）。
- `node/bun` 体积较大，也可放到 `assets/bin/js/node.exe` / `assets/bin/js/bun.exe`，但更推荐 `deno.exe`。

### 1.1 打包后落地目录（便于查找/替换）

打包策略已简化：EXE 与 `bin` 文件夹为同级结构（Full 模式）。示例：

- `dist/FluentYTDL.exe`
- `dist/bin/ffmpeg.exe`
- `dist/bin/deno.exe`

说明：我们不再把工具嵌入到 `_internal` 子目录，而是将 `assets/bin` 原样复制到 `dist/bin`，便于用户直接替换或更新可执行文件。

## 2. 打包前准备

### 2.1 拉取内置工具（默认推荐）

为了保证在“干净电脑”上开箱即用，建议在打包前先拉取并放置内置工具（FFmpeg + deno）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/fetch_tools.ps1
```

说明：
- FFmpeg 默认下载来源：gyan.dev（essentials build）
- deno 默认下载来源：GitHub Releases（latest）

如你的环境不允许联网，或你想完全手动放置文件，可把下列环境变量置为 1 来跳过自动下载：

```powershell
$env:FLUENTYTDL_SKIP_FETCH_TOOLS = '1'
```

- 确保依赖安装：

```powershell
C:/Users/Sakura/AppData/Local/Programs/Python/Python312/python.exe -m pip install -U pyinstaller
```

- 建议本地先跑一次：

```powershell
C:/Users/Sakura/AppData/Local/Programs/Python/Python312/python.exe scripts/selftest_translator.py
```

## 3. PyInstaller 打包

- `onedir`（推荐，便于带上 ffmpeg/deno 等文件并打 zip）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1 -Flavor full
```

输出目录：`dist/`（包含 `FluentYTDL.exe`，Full 模式下还会包含 `dist/bin`）

## 3.1 ZIP 打包（推荐发布形式）

将 `dist/FluentYTDL/` 整包压缩为 zip（zip 内保持顶层文件夹 `FluentYTDL/`，其中包含主启动 `FluentYTDL.exe`）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package_zip.ps1
```

输出目录：`installer/FluentYTDL-v<version>-win64-<date>.zip`

- `onefile`（单文件，启动会更慢，且体积更大）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1 -Flavor shell
```

## 4. 图标

PyInstaller 在 Windows 需要 `.ico`。

- 放置：`assets/logo.ico`
- 若不存在，会使用默认图标。

## 5. MSI / 安装包（建议路线）

PyInstaller 负责产出 `dist/FluentYTDL/`，然后用安装器工具把这个目录打成安装包。

推荐两条路线：

- ZIP 发布（最简单）：
  - 将 `dist/FluentYTDL/` 直接压缩为 `FluentYTDL-win64.zip`

- MSI 发布（更正规）：
  - 建议使用 WiX Toolset v4
  - 将 `dist/FluentYTDL/` 作为安装源目录

> 由于 MSI 需要安装器工具链（WiX）与产品 GUID/升级策略，这里先把 PyInstaller 输出稳定下来，再补 WiX 配置模板。

## 6. 打包后自检清单（最小）

- 启动不闪退，主窗口能打开
- 托盘图标能显示（`assets/logo.png` 已被打包且路径正确）
- 下载一个小视频：
  - 若内置 FFmpeg：能正常合并音视频
  - 若内置 Deno：解析格式更完整
- 配置文件写入位置（打包后）：`~/Documents/FluentYTDL/config.json`
- 日志写入位置（打包后）：`~/Documents/FluentYTDL/logs/`
