<p align="center">
  <img src="assets/logo.png" alt="FluentYTDL Logo" width="128" height="128">
</p>

<h1 align="center">FluentYTDL</h1>

<p align="center">
  <strong>🎬 现代、流畅、强大的 YouTube 视频下载器</strong>
</p>

<p align="center">
  <a href="#-核心机制与防线">核心特性</a> •
  <a href="#-环境依赖与安装">安装配置</a> •
  <a href="#-配置手册">配置手册</a> •
  <a href="#-反学术抄袭声明">⚠️学术诚信声明</a>
</p>

<p align="center">
  <a href="https://github.com/prideicker/FluentYTDL/releases/latest">
    <img src="https://img.shields.io/github/v/release/prideicker/FluentYTDL?style=flat-square&color=blue&label=Release" alt="Release">
  </a>
  <a href="https://github.com/prideicker/FluentYTDL/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/license-GPLv3-blue.svg?style=flat-square" alt="License">
  </a>
  <img src="https://img.shields.io/badge/Python-3.10+-green?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/平台-Windows-blue?style=flat-square&logo=windows&logoColor=white" alt="Platform">
</p>

> [!WARNING] 
> **🛑 重要约束：反盗卖与学术抄袭警告**
> 1. [《品牌商标与防盗卖政策》](TRADEMARK.md)：**严禁**任何团队或个人在不更改软件名称和图标的情况下，原封不动地对本软件进行二次分发或商业售卖。（违者必追究法律责任及全网下架发函）。
> 2. [《反学术抄袭高压线声明》](ACADEMIC_HONESTY.md)：除了作者本人以外，**绝对禁止**将本开源仓库的全部或部分源码用于提交高校的期末大作业、毕业设计（毕设）。本仓库已入库所有查重系统，一旦查实学术冒充行为，将直接向涉事高校教务处发出实名违纪举报！

---

## ✨ 核心机制与防线

除了常规的最高 8K 画质解析、播放列表下载等基础功能，FluentYTDL 在底层架构上构筑了坚实的技术壁垒：

### 🛡️ 智能防风控体系 (Anti-Bot)
- 🔑 **PO Token (Proof of Origin) 解析引擎**：内置自动化 PO Token 生成机制，利用隐形后台环境绕过 YouTube 近期严格的机器流量阻断墙（Bot-Detection）。
- 🤖 **OAuth2 TV 鉴权集成**：支持通过安全的 OAuth2 TV 端点验证，搭配 Cookie 智能获取渠道，完美下载包含年龄限制或会员专属的高要求内容。
- 🍪 **Cookie 热守护与智能同步**：启动时自动侦测并同步系统浏览器（Chrome/Edge/Firefox 等）凭证，支持环境无感刷新。

### 🎞️ 全矩阵资产解析
- 📝 **完善的字幕萃取与内嵌系统**：不仅能下载视频，更支持智能合并自动翻译字幕、移除字幕区广告、选择软/硬嵌入模式，多重语言优先级设定（如：简中 > 英文）。
- 🎵 **多音轨嗅探与混合**：针对部分优质源的多语种音轨，提供精准的音轨编号分配与优选混合，满足原声与本地化双重需求。
- 🖼️ **元数据极客注入**：不遗漏任何细节，实现高质量封面、影片描述、创作者元数据的纯净写入。
- 🥽 **VR/360° 空间媒体穿透**：专业级解析 EAC 及等距柱形投影的沉浸式视频流，修正并写入空间元数据（Spatial Media Metadata），确保下载的 VR 视频在播放器内直接以沉浸模式渲染。

### ⚙️ 底层性能怪兽
- 🔥 **GPU 硬件级调度**：内置实时硬件扫描系统，按需调用 NVENC (NVIDIA), AMF (AMD), QSV (Intel) 进行转码加速。并自动做风险内存管控，避免在高压环境下（如 8K 转码）崩溃。
- 🚀 **管线化并发控制**：动态切片、合理利用带宽流的多线程并发池机制，并实现无缝的状态持久化记录机制。
- 🔄 **生命周期闭环依赖系统**：所有核心处理组件（FFmpeg, yt-dlp 引擎内核等）全部由程序自动化检测状态与滚动热更新，真正实现使用环境开箱即用（Zero-Config）。

---

## 🛠️ 环境依赖与安装

### 系统要求
| 项目 | 要求 |
|------|------|
| **操作系统** | Windows 10/11 (64-bit) |
| **Python** | 3.10 及其以上（仅源码编译/运行需求） |

### 获取方式

1. 前往本仓库唯一的源头分发点 [Releases](https://github.com/prideicker/FluentYTDL/releases) 页面获取原生态版本。
2. 下载最新版本包或运行通过源码自行构建。

*首次启动时，程序内置的同步架构会自动补全所需的 FFmpeg 和相关脚本运行环境。*

---

## ⚙️ 配置手册

可以直接在界面内的“设置”专属页修改，也可通过 `config.json` 手动进阶配置。

### 🌐 网络与反爬配置
| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `proxy_mode` | `"system"` | 路由级别代理模式 (`system` / `http` / `socks5` / `off`) |
| `cookie_mode` | `"auto"` | 认证源汲取方式：`auto` (自动无感同步)、`browser` (硬读取)、`file` |
| `cookie_browser` | `"edge"` | `auto` 模式下的首选探测目标浏览器 |
| `pot_provider_enabled`| `true` | 全局开关：是否启用内置的强效 PO Token 服务防线 |
| `auth_mode` | `"oauth2"` | 全局鉴权基准协议 |

### 🚫 SponsorBlock 广告与赞助跳过
强大的片段粉碎机，利用众包数据剥离恼人的内嵌推广。
| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `sponsorblock_enabled` | `false` | 全局启用开关 |
| `sponsorblock_categories`| `["sponsor", "selfpromo", "interaction"]` | 定义欲剔除的分类（赞助、自宣、求点赞等） |
| `sponsorblock_action` | `"remove"` | 对于匹配片段的抹杀手段 (`remove` 删除 / `mark` 仅做章节标记) |

### 📝 综合字幕引擎
| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `subtitle_enabled` | `false` | 是否开启字幕解析下载流水线 |
| `subtitle_default_languages`| `["zh-Hans", "en"]` | 多语言拉取优先级池 |
| `subtitle_embed_mode` | `"always"` | 封存进视频流的策略判定 |
| `subtitle_output_format`| `"vtt"` | 偏好分离格式 |

---

## 📄 许可证条款 (GPLv3)

本项目底层基石与应用系统均受 **[GNU General Public License v3.0 (GPLv3)](LICENSE)** 管辖约束。这赋予了你在合规范畴内无与伦比的代码研习权力，**但极大地规制了闭源牟利和洗稿行为**。

任何对此系统的二开及再次发布尝试，必须一并开源您的代码。并且，这绝不覆盖原作者的排他性商标主权声明。详情查阅本工程内随附的 [《TRADEMARK.md》](TRADEMARK.md)。

---

## 🤝 贡献规范

我们十分珍视社区中能读懂并深挖网络嗅探、硬件编码调配相关的开发者。关于环境配置、包纯净度保护等细则，参看 [CONTRIBUTING.md](CONTRIBUTING.md)。

```bash
# 执行无情且标准化的格式稽查
ruff check src/

# 面向稳健构筑的单元测试
pytest
```

---

<p align="center">
  <b>Built with ❤️ by < 原作者：见 GitHub 仓库所有者 ></b><br/>
  Powered by PySide6 & yt-dlp Ecosystem
</p>
