<p align="center">
  <img src="assets/logo.png" alt="FluentYTDL Logo" width="128" height="128">
</p>

<h1 align="center">FluentYTDL</h1>

<p align="center">
  <strong>🎬 现代、流畅、强大的视频下载器</strong>
</p>

<p align="center">
  <a href="#-功能特色">功能特色</a> •
  <a href="#-快速开始">快速开始</a> •
  <a href="#-使用指南">使用指南</a> •
  <a href="#-配置说明">配置说明</a> •
  <a href="#-常见问题">常见问题</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/平台-Windows-blue?style=flat-square" alt="Platform">
  <img src="https://img.shields.io/badge/Python-3.10+-green?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/UI-Fluent%20Design-blueviolet?style=flat-square" alt="UI Framework">
  <img src="https://img.shields.io/badge/license-MIT-orange?style=flat-square" alt="License">
</p>

---

## ✨ 功能特色

### 🎯 核心能力

| 功能 | 描述 |
|------|------|
| **多平台支持** | 支持 YouTube、Bilibili、Twitter/X、抖音等 1000+ 网站 |
| **格式自由选择** | 从 360p 到 8K，从 MP3 到无损音频，任你挑选 |
| **播放列表下载** | 一键下载整个频道或播放列表，支持批量选择 |
| **智能解析** | 自动识别剪贴板链接，粘贴即下载 |
| **断点续传** | 网络中断？不怕，下次继续 |

### 🛡️ 进阶功能

| 功能 | 描述 |
|------|------|
| **Cookie 认证** | 一键从浏览器提取登录凭证，下载会员专属内容 |
| **SponsorBlock** | 自动跳过赞助广告、片头片尾，节省时间 |
| **代理支持** | 支持 HTTP/SOCKS5 代理，突破地区限制 |
| **封面嵌入** | 自动将视频封面嵌入到文件中 |
| **元数据写入** | 标题、作者、描述等信息自动写入文件 |

### 🎨 用户体验

- **Fluent Design** - 采用微软流畅设计语言，界面现代美观
- **暗色主题** - 支持深色模式，保护眼睛
- **任务管理** - 可视化下载队列，支持暂停/恢复/取消
- **实时进度** - 下载速度、剩余时间、进度一目了然

---

## 🚀 快速开始

### 方式一：下载安装包（推荐）

1. 前往 [Releases](https://github.com/your-repo/FluentYTDL/releases) 页面
2. 下载最新版本的 `.exe` 安装程序
3. 运行安装程序，按提示完成安装
4. 启动 FluentYTDL，开始使用！

### 方式二：从源码运行

```bash
# 克隆仓库
git clone https://github.com/your-repo/FluentYTDL.git
cd FluentYTDL

# 安装依赖
pip install -e .

# 运行应用
python main.py
```

### 系统要求

- **操作系统**: Windows 10/11 (64-bit)
- **Python**: 3.10 或更高版本（仅源码运行需要）
- **内存**: 4GB RAM 或更多
- **存储**: 500MB 可用空间

---

## 📖 使用指南

### 下载单个视频

1. **复制链接** - 在浏览器中复制视频链接
2. **粘贴链接** - 在 FluentYTDL 中粘贴链接（或开启剪贴板自动识别）
3. **选择格式** - 选择想要的画质和格式
4. **开始下载** - 点击下载按钮，等待完成

### 下载播放列表

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

- **可组装** - 分别选择视频流和音频流，自由组合
- **仅视频** - 只下载视频，不含音频
- **仅音频** - 只下载音频，支持多种格式

---

## ⚙️ 配置说明

### 设置页面概览

进入 **设置** 页面，可以配置以下选项：

#### 📁 下载选项
- **默认保存路径** - 设置视频保存位置

#### 🌐 网络连接
- **代理模式** - 关闭 / 系统代理 / HTTP / SOCKS5
- **自定义代理** - 输入代理地址（如 `http://127.0.0.1:7890`）

#### 🔐 Cookie 认证
用于下载需要登录的内容（如会员视频、年龄限制视频）：
1. 选择浏览器（推荐 Edge 或 Chrome）
2. 确保已在该浏览器登录 YouTube
3. 点击"提取 Cookie"
4. 等待提取完成并验证

> **注意**: Chrome 130+ 版本可能需要管理员权限

#### 🚫 SponsorBlock
自动跳过视频中的广告片段：
1. 开启 SponsorBlock 开关
2. 点击"选择类别"
3. 勾选要跳过的片段类型：
   - 赞助广告 - 付费推广内容
   - 自我推广 - 频道推广、社交媒体
   - 互动提醒 - 订阅、点赞提醒
   - 片头/片尾 - 固定的开头结尾动画

#### 🎨 后处理
- **封面嵌入** - 将视频封面嵌入到文件中
- **元数据嵌入** - 写入标题、作者、描述等信息

---

## ❓ 常见问题

### Q: 下载速度很慢？

**A**: 尝试以下方法：
1. 开启代理（如果你的网络环境需要）
2. 检查网络连接是否稳定
3. 降低同时下载的任务数

### Q: 提示"签名提取失败"？

**A**: 这通常是因为缺少 JavaScript 运行时：
1. 应用会自动下载 Deno 运行时
2. 如果自动下载失败，手动将 `deno.exe` 放入 `bin/deno/` 目录

### Q: Cookie 提取失败？

**A**: 
1. 确保目标浏览器已完全关闭
2. 确保已在该浏览器登录 YouTube
3. Chrome 130+ 需要以管理员身份运行 FluentYTDL
4. 尝试使用其他浏览器

### Q: 下载的视频没有声音？

**A**: 
1. 确保选择了"可组装"模式下的视频+音频组合
2. 或使用简易模式的预设选项
3. 检查是否安装了 FFmpeg（应用会自动下载）

### Q: 如何更新 yt-dlp？

**A**: 在设置页面的"核心组件"部分：
1. 点击"检查更新"按钮
2. 如有新版本，点击"更新"
3. 等待更新完成

---

## 🔧 技术栈

| 组件 | 技术 |
|------|------|
| UI 框架 | PySide6 + QFluentWidgets |
| 下载引擎 | yt-dlp |
| 媒体处理 | FFmpeg |
| Cookie 提取 | rookiepy |
| JS 运行时 | Deno |

---

## 📄 许可证

本项目基于 [MIT 许可证](LICENSE) 开源。

---

## 🙏 致谢

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - 强大的视频下载引擎
- [QFluentWidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) - 流畅设计 UI 组件库
- [SponsorBlock](https://sponsor.ajay.app/) - 广告跳过数据库
- [rookiepy](https://github.com/thewh1teagle/rookiepy) - 浏览器 Cookie 提取

---

<p align="center">
  Made with ❤️ by the FluentYTDL Team
</p>
