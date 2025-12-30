# FluentYTDL

**一个现代、流畅、轻量的 YouTube/视频下载器。**

<!-- Badges -->
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/) [![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) [![Release](https://img.shields.io/badge/release-v0.1.0-orange.svg)](https://github.com/)

---

## ✨ 核心亮点 (Features)

- **现代化界面**：采用 Fluent Design 风格，支持深色/浅色模式（基于 QFluentWidgets）。
- **智能环境管理**：自动检测 ffmpeg/yt-dlp，支持内置或系统环境（按 `path_manager.py` 的逻辑）。
- **剪贴板监听**：复制链接自动弹出下载（参见 `clipboard_monitor.py` 的实现）。
- **格式选择**：支持 4K/8K、音频提取等（参见 `format_selector.py`）。

---

## 📥 下载与安装 (Download)

请前往仓库右侧的 **Releases** 页面下载最新版打包文件。下载后解压，直接运行 `FluentYTDL.exe` 即可，无需安装 Python。🎉

---

## 🚀 快速开始 (Usage)

简单三步：

1. 复制视频或播放列表链接（剪贴板监听会自动弹出）。
2. 在弹窗中选择清晰度与输出格式。 
3. 点击“开始下载”。

---

## 🛠️ 源码运行 (For Developers)

（面向开发者的简短说明）

- 依赖安装：`pip install -r requirements.txt`
- 启动：`python main.py`

---

## 📄 开源协议

本项目采用 **MIT License**，详见 `LICENSE` 文件。🧾

---

感谢使用 FluentYTDL！如需帮助，请查看 `docs/` 目录或打开 issue。 💬

## 📄 发癫发言
woc了这是我第一个就用那一点点鸡毛蒜皮的知识拿着AI当工具人狠狠压榨制作出来的大粪。我知道这很臭但是别怪我，你们的issue我也不一定会看，因为我会忘记，忘记这个狗屎。
其实我也不想制作答辩的，但是我我那鸡毛蒜皮的知识和对github的使用如同粪坑里的蛆虫一点一点写出来、配置出来的，我甚至github action来自动发布安装包我都蠢如猪。
我感觉我和AI像两头倔驴一样谁也不服谁，他写他的我写我的乱七八糟。
嗯，所以项目有任何稀奇古怪的BUG可以的话留下你的issue，但不必为了让我改提出issue，提点建议，BUG啥的行了，你们实在着急就fork过去我这堆答辩改改，AI注释都有写的。
看到这坨请别喷.orz
