# FluentYTDL 开发规则

> [English version](RULES_EN.md)

## 1. 项目身份

- **名称**：FluentYTDL — 专业 YouTube/视频下载器
- **语言**：Python 3.10+
- **UI 框架**：PySide6 (Qt6) + QFluentWidgets（Fluent 设计）
- **下载引擎**：yt-dlp CLI 子进程（非 Python API）
- **媒体处理**：FFmpeg
- **代码库**：148 个 .py 文件，~50k LOC，`src/fluentytdl/` 包
- **平台**：Windows 为主，跨平台为目标

## 2. 架构规则

### 分层架构

```
UI 层 (ui/)
  ↓ 依赖
服务层 (auth/, youtube/, download/, processing/, storage/)
  ↓ 依赖
核心基础设施 (core/)
  ↓ 依赖
基础层 (utils/, models/)
```

- **UI 绝不能直接调用 yt-dlp** — 通过 `youtube_service`
- **服务层绝不能从 ui/ 导入** — 通过 Qt Signal 通信
- **Models 自包含** — 无循环依赖

### 单例

项目广泛使用单例模式。关键单例：`config_manager`、`download_manager`、`auth_service`、`cookie_sentinel`、`youtube_service`、`pot_manager`、`task_db`。

创建新单例时，需在此列表中记录。

### Qt Signal/Slot

所有 UI-后端通信必须使用 Qt Signal/Slot 机制。绝不能在 UI 事件处理器中直接调用后端方法 — 发射信号代替。

### 六种解析模式

项目支持 6 种不同的解析模式。详见 `docs/ARCHITECTURE.md` 第 3 章：

1. **视频** — 标准单视频下载
2. **VR** — VR 视频，使用 `android_vr` 客户端，EAC 转换
3. **频道** — 频道标签页列表，懒加载
4. **播放列表** — 播放列表，批量操作
5. **字幕** — 独立字幕下载（轻量提取）
6. **封面** — 独立封面下载（直链或轻量提取）

修改下载逻辑时，必须考虑对所有 6 种模式的影响。

## 3. 代码风格

### Ruff（强制）

```toml
target-version = "py310"
line-length = 100
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501"]  # 允许长行
```

- `__init__.py` 文件中忽略 `F401`（重导出是有意的）
- isort：`known-first-party = ["fluentytdl"]`

### Pyright（建议性）

```toml
pythonVersion = "3.10"
# 很多 report* 设置已放宽 — 不要随意添加新的 type:ignore
```

### UI 规则

- **必须**使用 QFluentWidgets（FluentWindow、InfoBar 等）
- **绝不**使用原始 QMessageBox、QDialog 或 QWidget 创建新 UI
- 列表项使用 QPainter 委托（避免大量列表的 QWidget 开销）
- 暗色模式支持：使用 `CustomInfoBar`，而非原始 InfoBar

### 文件命名

- 所有 Python 文件使用 snake_case
- 建议每个文件一个类（尤其在 ui/components/ 中）
- 私有模块级函数用 `_` 前缀

## 4. yt-dlp 集成规则 [关键]

这些规则来自生产环境的惨痛教训。违反它们**必然**导致用户可见的 bug。

1. **绝不强制 `player_client`** — 信任 yt-dlp 默认策略（tv → web_safari → android_vr）
2. **绝不启用 `sleep_interval`** — 导致签名 URL 过期 → HTTP 403
3. **绝不使用 `--cookies-from-browser`** — Windows 上导致 DPAPI 文件锁
4. **语言格式注入** — `-S lang:xx` 无法覆盖 `language_preference=10`；使用 `_inject_language_into_format()`
5. **非零退出时验证文件大小** — Windows `.part-Frag` 删除失败但下载已完成
6. **同步 POT 插件到 exe 目录** — 编译后的 yt-dlp 无法通过 PYTHONPATH 发现插件
7. **TUN 模式不注入代理环境变量** — 注入 `HTTPS_PROXY` 导致双重代理
8. **web_music 需要 `disable_innertube=True`** — 该客户端的 InnerTube 挑战有缺陷
9. **BCP-47 别名扩展** — `zh-Hans` 必须匹配 `zh-CN`、`zh-SG` 等
10. **沙箱下载模型** — 每个任务一个临时目录，成功后移动，取消时清理

详见 `docs/YTDLP_KNOWLEDGE.md` 完整经验知识库。

## 5. Cookie 系统规则

- `CookieSentinel` 管理单个 `bin/cookies.txt` 的生命周期
- **懒清理**：新提取成功前绝不删除旧 cookies
- **必需 cookies**：SID、HSID、SSID、SAPISID、APISID
- **Chromium v130+**：需要管理员权限进行应用绑定加密解密
- **403 恢复**：自动检测 cookie 过期关键词，提示刷新
- **JSON cookie 文件**：拒绝并给出警告（yt-dlp 只接受 Netscape 格式）

## 6. 后处理管道顺序

1. `SponsorBlockFeature` — sponsorblock_remove/mark
2. `MetadataFeature` — FFmpegMetadata 后处理器
3. `SubtitleFeature` — 双语合并、嵌入、清理
4. `ThumbnailFeature` — 通过 AtomicParsley (MP4) > FFmpeg (MKV) > mutagen (audio) 嵌入
5. `VRFeature` — EAC→Equi 转换 + 空间元数据（仅 VR 模式）

## 7. 测试规则

- pytest >= 7.0
- 测试文件在 `tests/` 目录
- **尚无 conftest.py** — 每个测试自行设置 `sys.path`
- 2 个测试需要 GUI（QApplication）— 无法在无头 CI 中运行
- 1 个测试无断言（test_error_parser.py）— 需要修复
- CI 所有检查使用 `continue-on-error: true` — 没有阻塞合并的检查
- 添加新测试时：优先使用普通 pytest 函数而非 unittest.TestCase

## 8. 禁止事项

- **不要**在 UI 中使用原始 Qt 控件（必须使用 QFluentWidgets）
- **不要**将 yt-dlp 作为 Python 库导入（始终使用 CLI 子进程）
- **不要**使用 `cookies_from_browser`（DPAPI 锁）
- **不要**强制 sleep interval（签名 URL 过期）
- **不要**在未记录于第 2 节的情况下创建新单例
- **不要**在未更新 `pyproject.toml` 的情况下添加依赖
- **不要**提交 `config.json`、凭证、API token 或 cookies
- **不要**随意使用 `type:ignore`
- **不要**绕过沙箱下载模型进行视频下载

## 9. 关联文档

| 文档 | 用途 |
|------|------|
| `docs/ARCHITECTURE.md` | 当前架构（含 6 种解析流程详情） |
| `docs/YTDLP_KNOWLEDGE.md` | yt-dlp 经验排障知识库 |
| `docs/RULES_EN.md` | 本文档的英文版 |
| `CONTRIBUTING.md` | 贡献指南 |
| `SECURITY.md` | 安全策略 |
