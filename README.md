<p align="center">
  <img src="assets/logo.png" alt="FluentYTDL Logo" width="128" height="128">
</p>

<h1 align="center">FluentYTDL</h1>

<p align="center">
  <strong>🎬 现代、流畅、强大的 YouTube 视频下载器</strong>
</p>

<p align="center">
  <a href="#-功能特色">功能特色</a> •
  <a href="#-环境依赖与安装">安装</a> •
  <a href="#-使用指南">使用指南</a> •
  <a href="#-配置说明">配置</a> •
  <a href="#-技术栈">技术栈</a> •
  <a href="#-致谢">致谢</a>
</p>

<p align="center">
  <a href="https://github.com/SakuraForgot/FluentYTDL/releases/latest">
    <img src="https://img.shields.io/github/v/release/SakuraForgot/FluentYTDL?style=flat-square&color=blue&label=Release" alt="Release">
  </a>
  <a href="https://github.com/SakuraForgot/FluentYTDL/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/license-GPLv3-blue.svg?style=flat-square" alt="License">
  </a>
  <img src="https://img.shields.io/badge/Python-3.10+-green?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/平台-Windows-blue?style=flat-square&logo=windows&logoColor=white" alt="Platform">
</p>

> [!WARNING]
> **🛑 重要声明**
> 1. [《品牌商标与防盗卖政策》](TRADEMARK.md)：**严禁**任何团队或个人在不更改软件名称和图标的情况下，对本软件进行二次分发或商业售卖。违者将被追究法律责任并全网下架。
> 2. [《反学术抄袭声明》](ACADEMIC_HONESTY.md)：除作者本人以外，**绝对禁止**将本仓库的全部或部分源码用于提交高校课程作业或毕业设计。本仓库已被各大查重系统收录，一经查实将向涉事高校发出实名举报。

---

## ✨ 功能特色

### 🛡️ 智能反风控体系 (Anti-Bot)

- 🔑 **PO Token 自动生成引擎** — 内置 bgutil-ytdlp-pot-provider，通过隐形后台 Deno 环境自动生成 Proof of Origin Token，突破 YouTube 的机器检测封锁
- 🤖 **OAuth2 TV 鉴权** — 通过安全的 OAuth2 TV 端点验证身份，无需手动输入密码即可下载年龄限制或会员专属内容
- 🍪 **Cookie 智能同步守护** — 启动时自动从系统浏览器（Chrome/Edge/Firefox 等）同步凭证，报错时自动刷新，支持 `auto`/`browser`/`file` 三种模式

### 📥 核心下载能力

- 🎬 **最高 8K 画质** — 自动选择最高可用画质，支持 MP4/WebM/MKV 等多种格式输出
- 📋 **播放列表批量下载** — 智能解析播放列表与频道，支持勾选式批量操作和统一/逐个格式设置
- 🎵 **多音轨嗅探与选择** — 针对多语种音轨视频，支持精准的音轨优先级设定（如中文 > 英文 > 原声）
- 🚀 **分片并发加速** — 可配置的多线程并发分片下载，充分利用带宽

### 🎞️ 全矩阵资产管理

- 📝 **完善的字幕系统** — 支持多语言字幕下载、自动翻译字幕获取、字幕广告移除、软/硬嵌入模式选择，以及 SRT/ASS/VTT/LRC 多格式输出
- 🖼️ **封面与元数据注入** — 自动嵌入高质量封面、视频描述、创作者等元数据信息
- 🚫 **SponsorBlock 集成** — 利用社区众包数据，自动移除或标记视频中的赞助片段、片头片尾、自宣内容
- 🥽 **VR/360° 视频支持** — 专业级解析 EAC 及等距柱形投影沉浸式视频，自动写入空间元数据确保 VR 播放器兼容

### ⚙️ 底层性能

- 🔥 **GPU 硬件加速** — 自动检测系统 GPU，按需调用 NVENC (NVIDIA)、AMF (AMD)、QSV (Intel) 进行转码加速，内置内存风险管控
- 🔄 **组件自动更新** — FFmpeg、yt-dlp 等核心组件由程序自动检测版本并滚动热更新，真正开箱即用
- 💾 **任务持久化** — 下载任务状态实时写入数据库，异常退出后重启可自动恢复
- 🖥️ **磁盘空间检测** — 下载前自动检测目标磁盘剩余空间，避免因空间不足导致下载中断

### 🎨 用户体验

- 💎 **Fluent Design** — 采用微软流畅设计语言，界面现代美观
- 🌙 **深色/浅色主题** — 支持自动跟随系统、手动切换深色或浅色模式
- 📊 **任务管理** — 可视化下载队列，支持暂停/恢复/取消
- ⚡ **实时进度** — 下载速度、剩余时间、进度条一目了然

---

## 🛠️ 环境依赖与安装

### 系统要求

| 项目 | 要求 |
|------|------|
| **操作系统** | Windows 10/11 (64-bit) |
| **Python** | 3.10 或更高版本（仅源码运行需要） |
| **内存** | 4GB RAM 或更多 |
| **存储** | 500MB 可用空间 |

### 方式一：下载安装包（推荐）

1. 前往 [Releases](https://github.com/SakuraForgot/FluentYTDL/releases) 页面
2. 下载最新版本的 `*-setup.exe` 安装程序或 `*-full.7z` 便携包
3. 运行安装程序按提示完成安装，或解压便携包到任意位置
4. 启动 FluentYTDL，开始使用！

> **⚠️ 注意：** 请务必从本仓库的 [Releases](https://github.com/SakuraForgot/FluentYTDL/releases) 页面获取，这是唯一合法的分发渠道。任何第三方下载站均非授权来源。

### 方式二：从源码运行

```bash
# 克隆仓库
git clone https://github.com/SakuraForgot/FluentYTDL.git
cd FluentYTDL

# 安装依赖
pip install -e .

# 运行应用
python main.py
```

> **💡 提示：** FFmpeg 和 Deno 运行时会在首次启动时**自动下载**，无需手动安装。如果自动下载失败，请手动将对应文件放入 `bin/` 目录。

---

## 🚀 使用指南

### 基础用法

1. **复制链接** — 在浏览器中复制 YouTube 视频链接
2. **粘贴链接** — 在 FluentYTDL 中粘贴链接
3. **选择格式** — 选择想要的画质和格式
4. **开始下载** — 点击下载按钮，等待完成

### 播放列表下载

1. 复制播放列表或频道链接
2. 粘贴后，应用会自动识别为播放列表
3. 在列表中勾选要下载的视频
4. 为选中的视频统一设置格式（或逐个设置）
5. 点击批量下载

### 格式选择指南

#### 简易模式（推荐新手）

| 预设 | 说明 | 适用场景 |
|------|------|----------|
| 🎬 最佳画质 (MP4) | 自动选择最高画质，输出 MP4 | 通用场景 |
| 🎯 最佳画质 (原盘) | 保持原始格式，可能是 WebM | 追求极致画质 |
| 📺 1080p 高清 | 限制最高 1080p | 节省空间 |
| 📺 720p 标清 | 限制最高 720p | 手机观看 |
| 🎵 纯音频 (MP3) | 仅下载音频 | 听歌、播客 |

#### 专业模式

- **可组装** — 分别选择视频流和音频流，自由组合
- **仅视频** — 只下载视频，不含音频
- **仅音频** — 只下载音频，支持多种格式

---

## 高级功能

### 🔥 GPU 加速转码

FluentYTDL 能自动检测系统 GPU 并使用硬件加速进行视频转码，大幅提升处理速度。

支持的硬件编码器：

| GPU 厂商 | 编码器 |
|----------|--------|
| NVIDIA | NVENC (H.264 / H.265) |
| AMD | AMF (H.264 / H.265) |
| Intel | QSV (H.264 / H.265) |

> **⚙️ 如何启用：** 进入 **设置** → **后处理** 页面，开启 GPU 加速开关。应用会自动检测并选择最佳编码器。

### 📝 字幕下载与管理

FluentYTDL 内置完整的字幕处理流水线，支持丰富的定制选项：

- **多语言优先级** — 可设定语言优先级池（如 `zh-Hans` → `en`），自动按优先级拉取
- **自动翻译字幕** — 当官方字幕缺失时，可获取 YouTube 自动生成的翻译字幕
- **字幕广告过滤** — 可选移除字幕流中的推广信息
- **灵活嵌入策略** — 支持软嵌入（soft，保留独立轨道）或外部文件（external）两种方式
- **多格式输出** — 支持 SRT、ASS、VTT、LRC 格式

### 🥽 VR 视频下载

支持下载 YouTube 360°/180° VR 视频，最高可达 8K 分辨率。

- 自动识别 VR 视频格式（EAC / 等距柱形投影）
- 自动修正并注入 VR 空间元数据（Spatial Media Metadata）
- 确保 VR 播放器正确以沉浸模式渲染

> **⚠️ 注意：** 高分辨率 VR 视频文件体积较大（8K 可达 10GB+），请确保有足够的磁盘空间。

### 🛡️ PO Token 反风控机制

YouTube 近期大幅强化了对非浏览器客户端的机器检测。FluentYTDL 内置了 `bgutil-ytdlp-pot-provider` 插件：

- 利用 Deno 运行时模拟浏览器环境，自动生成合法的 PO Token
- 全流程自动化，无需用户手动干预
- 可通过 `pot_provider_enabled` 配置全局开关

---

## ⚙️ 配置说明

进入 **设置** 页面，可以配置以下选项。也可以直接编辑应用数据目录下的 `config.json`。

### 📁 下载选项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `download_dir` | `string` | `~/Downloads/FluentYTDL` | 默认下载保存路径 |
| `max_concurrent_downloads` | `int` | `3` | 最大同时下载任务数 |
| `concurrent_fragments` | `int` | `4` | 单任务分片并发数 |
| `clipboard_auto_detect` | `bool` | `false` | 自动识别剪贴板链接 |
| `deletion_policy` | `string` | `"AlwaysAsk"` | 删除策略：`KeepFiles` / `DeleteFiles` / `AlwaysAsk` |

### 🌐 网络连接

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `proxy_mode` | `string` | `"system"` | 代理模式：`off` / `system` / `http` / `socks5` |
| `proxy_url` | `string` | `"127.0.0.1:7890"` | 自定义代理地址 |

### 🔐 认证与 Cookie

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `auth_mode` | `string` | `"oauth2"` | 全局鉴权模式：`oauth2` / `cookie` |
| `cookie_mode` | `string` | `"auto"` | 提取方式：`auto`（自动同步）/ `browser`（直接读取）/ `file`（手动导入） |
| `cookie_browser` | `string` | `"edge"` | 提取源浏览器：`chrome` / `edge` / `firefox` |
| `pot_provider_enabled` | `bool` | `true` | 是否启用内置 PO Token 自动获取服务 |

> **⚠️ 注意：** Chrome 130+ 版本可能需要以管理员身份运行 FluentYTDL 才能提取 Cookie。

### 🚫 SponsorBlock

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `sponsorblock_enabled` | `bool` | `false` | 启用广告跳过 |
| `sponsorblock_categories` | `list` | `["sponsor", "selfpromo", "interaction"]` | 跳过的类别 |
| `sponsorblock_action` | `string` | `"remove"` | 处理方式：`remove`（移除）/ `mark`（标记为章节） |

### 📝 字幕配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `subtitle_enabled` | `bool` | `false` | 是否启用字幕下载 |
| `subtitle_default_languages` | `list` | `["zh-Hans", "en"]` | 字幕语言优先级 |
| `subtitle_embed_type` | `string` | `"soft"` | 嵌入类型：`soft` / `external` |
| `subtitle_embed_mode` | `string` | `"always"` | 嵌入策略：`always` / `never` / `ask` |
| `subtitle_output_format` | `string` | `"vtt"` | 输出格式：`srt` / `ass` / `vtt` / `lrc` |
| `subtitle_enable_auto_captions` | `bool` | `true` | 是否获取自动生成字幕 |
| `subtitle_remove_ads` | `bool` | `false` | 是否移除字幕中的广告 |
| `subtitle_quality_check` | `bool` | `true` | 是否启用字幕质量检查 |

### 🎵 音频偏好

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `preferred_audio_languages` | `list` | `["zh-Hans", "en", "orig"]` | 音轨语言优先级 |
| `audio_multistream_default_count` | `int` | `1` | 多音轨视频默认选择条数（0=无限制） |

### 🎨 后处理与外观

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `embed_thumbnail` | `bool` | `true` | 嵌入视频封面 |
| `embed_metadata` | `bool` | `true` | 嵌入元数据信息 |
| `theme_mode` | `string` | `"Auto"` | 主题模式：`Light` / `Dark` / `Auto` |
| `check_updates_on_startup` | `bool` | `true` | 启动时检查组件更新 |

---

## 🔧 技术栈

| 组件 | 技术 | 用途 |
|------|------|------|
| UI 框架 | PySide6 + QFluentWidgets | 流畅设计用户界面 |
| 下载引擎 | yt-dlp | 视频解析与下载 |
| 媒体处理 | FFmpeg | 转码、合并、封装 |
| Cookie 提取 | rookiepy | 跨浏览器凭证同步 |
| JS 运行时 | Deno | PO Token 生成环境 |
| 图像处理 | Pillow | 封面处理与缩放 |
| 网络请求 | requests | HTTP 通信 |
| 系统监控 | psutil | 硬件检测与进程管理 |
| 日志框架 | loguru | 结构化日志记录 |
| VR 元数据 | Google Spatial Media | 空间媒体元数据注入 |
| 内嵌浏览器 | pywebview | OAuth2 认证窗口 |
| 文档渲染 | markdown | 更新日志渲染 |

---

## 🤝 贡献指南

欢迎贡献！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详细的贡献流程。

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行代码检查
ruff check src/

# 运行测试
pytest
```

> **📏 代码风格：** 项目使用 [Ruff](https://github.com/astral-sh/ruff) 进行代码检查和格式化，请在提交前运行 `ruff check` 确保代码风格一致。

---

## 📄 许可证

本项目基于 [GNU General Public License v3.0 (GPLv3)](LICENSE) 开源。

这意味着你可以自由地学习、修改和分发本项目的代码，但任何基于本项目的衍生作品**必须同样以 GPLv3 协议开源**。详细的品牌使用限制请参阅 [TRADEMARK.md](TRADEMARK.md)。

---

## 🙏 致谢

FluentYTDL 的诞生离不开以下优秀的开源项目和服务：

| 项目 | 简介 |
|------|------|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 强大的视频下载引擎 |
| [PySide6](https://doc.qt.io/qtforpython-6/) | Qt for Python 官方绑定 |
| [QFluentWidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) | 流畅设计 UI 组件库 |
| [FFmpeg](https://ffmpeg.org/) | 全能多媒体处理工具 |
| [Deno](https://deno.com/) | 安全的 JavaScript/TypeScript 运行时 |
| [rookiepy](https://github.com/thewh1teagle/rookiepy) | 跨平台浏览器 Cookie 提取 |
| [SponsorBlock](https://sponsor.ajay.app/) | 社区驱动的广告跳过数据库 |
| [loguru](https://github.com/Delgan/loguru) | 优雅的 Python 日志框架 |
| [Pillow](https://github.com/python-pillow/Pillow) | Python 图像处理库 |
| [requests](https://github.com/psf/requests) | 简洁优雅的 HTTP 请求库 |
| [psutil](https://github.com/giampaolo/psutil) | 跨平台系统进程与资源监控 |
| [Spatial Media](https://github.com/google/spatial-media) | Google VR 空间媒体元数据工具 |
| [PyInstaller](https://github.com/pyinstaller/pyinstaller) | Python 应用打包工具 |
| [Shields.io](https://shields.io/) | 开源项目徽章服务 |

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/SakuraForgot">SakuraForgot</a>
</p>
