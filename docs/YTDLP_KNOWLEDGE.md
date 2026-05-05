# yt-dlp 经验知识库

> [English version](YTDLP_KNOWLEDGE_EN.md)
>
> 每条记录遵循：**症状 → 根因 → 规则 → 代码引用**

## 1. 下载失败

### 1.1 下载中 403（签名过期）

**症状**：下载中途 HTTP 403，尤其长视频

**根因**：`sleep_interval` 在请求间引入延迟；YouTube 签名 URL 的 TTL 很短（~几分钟）

**规则**：绝对不要将 `sleep_interval_min` 或 `sleep_interval_max` 设置为非零值

**代码**：`src/fluentytdl/youtube/youtube_service.py` — AntiBlockingOptions 注释

### 1.2 年龄限制 / 会员专属内容 403

**症状**：yt-dlp 返回"请登录以确认年龄"或"此视频仅限会员"

**根因**：缺少或过期的 cookies；年龄限制内容需要已认证的会话

**规则**：CookieSentinel 自动检测这些关键词并触发 cookie 刷新流程

**代码**：`src/fluentytdl/auth/cookie_sentinel.py` — `COOKIE_ERROR_KEYWORDS`

### 1.3 Bot 检测（LOGIN_REQUIRED）

**症状**：yt-dlp 提取时返回 `LOGIN_REQUIRED` 错误

**根因**：YouTube 检测到自动化访问；需要 PO Token 或新 cookies

**规则**：POT Manager 提供 PO Token；如果不可用，回退到使用设置中静态 token 的 `mweb` client

**代码**：`src/fluentytdl/youtube/youtube_service.py` — `build_ydl_options()` 中的回退逻辑

### 1.4 "页面需要重新加载"错误

**症状**：yt-dlp 返回关于页面重新加载的错误

**根因**：过期的 cookies 或会话状态

**规则**：自动检测此错误并强制刷新 DLE cookies 进行单次重试

**代码**：`src/fluentytdl/youtube/youtube_service.py` — 提取方法中的重试逻辑

### 1.5 播放列表认证检查提示

**症状**：yt-dlp 提示关于 `youtubetab:skip=authcheck`

**根因**：YouTube 播放列表需要可以跳过的认证检查

**规则**：自动检测此提示并在重试时注入 `youtubetab:skip=authcheck` 作为 extractor-arg

**代码**：`src/fluentytdl/youtube/youtube_service.py` — 播放列表重试逻辑

## 2. 格式选择

### 2.1 语言偏好覆盖失败

**症状**：格式排序中的 `-S lang:xx` 未能选择正确的音轨

**根因**：yt-dlp 的 `language_preference=10` 在 extractor_args 中覆盖了排序优先级；仅 `-S` 无法胜出

**规则**：使用 `_inject_language_into_format()` 在格式字符串的每个备选项前添加 `[language=xx]` 过滤器

**代码**：`src/fluentytdl/youtube/yt_dlp_cli.py` — `_inject_language_into_format()`

### 2.2 BCP-47 别名扩展

**症状**：语言环境变体的音轨语言匹配失败（如 `zh-CN` vs `zh-Hans`）

**根因**：YouTube 在不同上下文中使用不同的语言环境代码

**规则**：使用 `bcp47_expand_for_sort()` 在构建 format_sort 前将语言代码扩展为所有可能的别名

**代码**：`src/fluentytdl/utils/format_scorer.py`

### 2.3 web_music 客户端需要 disable_innertube

**症状**：YouTube Music URL 的格式提取失败

**根因**：`web_music` 客户端的 InnerTube 挑战处理有缺陷

**规则**：使用 `web_music` player_client 时，始终在 PO Token 请求中设置 `disable_innertube=True`

**代码**：`src/fluentytdl/yt_dlp_plugins_ext/yt_dlp_plugins/extractor/getpot_bgutil_http.py`

### 2.4 不强制 player_client

**症状**：想强制使用 `android` 或 `ios` 客户端以获取更好的格式

**根因**：Android/iOS 模拟可能返回不完整的格式列表；yt-dlp 的默认策略（tv → web_safari → android_vr）经过充分测试

**规则**：绝对不要通过 extractor_args 强制 `player_client`；信任 yt-dlp 默认值

**代码**：`src/fluentytdl/youtube/youtube_service.py` — `build_ydl_options()` 中的注释

## 3. Windows 特有问题

### 3.1 .part-Frag 文件删除失败

**症状**：yt-dlp 返回退出码 1 但下载看起来已完成

**根因**：Windows 文件锁定阻止删除 `.part-Frag` 文件；下载实际已完成

**规则**：非零退出码时，检查输出文件是否存在且大小 >= 预期总字节数的 50%

**代码**：`src/fluentytdl/download/executor.py` — 预期大小验证

### 3.2 DPAPI Cookie 锁

**症状**：浏览器 cookie 提取挂起或失败；其他浏览器功能异常

**根因**：`--cookies-from-browser` 在 Windows 上通过 DPAPI 锁定 Chrome/Edge SQLite 数据库

**规则**：绝对不要使用 `--cookies-from-browser`；始终先通过 rookiepy 提取到文件

**代码**：`src/fluentytdl/auth/auth_service.py`

### 3.3 POT 插件发现失败

**症状**：编译后的 yt-dlp.exe 找不到 PO Token 提供者

**根因**：独立编译的 yt-dlp 不通过 PYTHONPATH 发现插件

**规则**：使用基于 mtime 的增量同步，将 POT 插件 `.py` 文件同步到 `<exe-dir>/yt-dlp-plugins/bgutil-ytdlp-pot-provider/`

**代码**：`src/fluentytdl/youtube/yt_dlp_cli.py` — `sync_pot_plugins_to_ytdlp()`

### 3.4 进程树终止

**症状**：取消后遗留孤立的 yt-dlp 或 ffmpeg 进程

**根因**：`terminate()` 只杀死直接子进程，不杀死衍生的子进程

**规则**：在 Windows 上，使用 `taskkill /F /T /PID` 杀死整个进程树

**代码**：`src/fluentytdl/download/executor.py` — 进程终止逻辑

### 3.5 跨驱动器文件移动失败

**症状**：`os.replace()` 在临时目录和目标位于不同驱动器时失败

**根因**：Windows 上 `os.replace()` 无法跨驱动器移动

**规则**：在目标目录同目录下创建临时文件，避免跨驱动器移动

**代码**：`src/fluentytdl/download/workers.py` — 沙箱目录创建

## 4. 网络 / 代理

### 4.1 TUN 模式双重代理

**症状**：系统 TUN/VPN（如 V2RayN）激活时下载失败或极慢

**根因**：注入 `HTTPS_PROXY`/`HTTP_PROXY` 环境变量导致流量同时经过 TUN 和代理

**规则**：检测到 TUN 模式时，不要向 POT Manager 子进程注入代理环境变量

**代码**：`src/fluentytdl/youtube/pot_manager.py` — 代理注入逻辑

### 4.2 代理关闭覆盖

**症状**：选择"无代理"时系统代理仍被使用

**根因**：系统级代理环境变量覆盖了 yt-dlp 设置

**规则**：代理模式为"off"时，显式设置 `proxy: ""` 以覆盖任何系统代理

**代码**：`src/fluentytdl/youtube/youtube_service.py` — `NetworkOptions`

### 4.3 Localhost 代理绕过

**症状**：POT Manager 的 HTTP 请求经过 TUN 代理而非 localhost

**根因**：`urllib.request.urlopen()` 遵循系统代理设置

**规则**：对 localhost 请求使用空的 `ProxyHandler` 以绕过 TUN 模式代理

**代码**：`src/fluentytdl/youtube/pot_manager.py` — `_local_urlopen()`

## 5. Cookie 系统

### 5.1 懒清理

**症状**：新提取成功前删除了旧 cookies → 认证空白期

**根因**：急切清理在替换验证前移除了可用的 cookies

**规则**：新提取成功并验证前，绝对不要删除旧 cookies

**代码**：`src/fluentytdl/auth/cookie_sentinel.py`

### 5.2 必需的 YouTube Cookies

**症状**：部分认证 — 某些功能正常，其他不正常

**根因**：缺少必需的 cookie 字段

**规则**：验证存在：SID、HSID、SSID、SAPISID、APISID

**代码**：`src/fluentytdl/auth/cookie_cleaner.py`

### 5.3 Chromium v130+ 应用绑定加密

**症状**：较新 Chrome/Edge 上 cookie 提取静默失败

**根因**：Chromium v130+ 使用应用绑定加密，需要管理员权限解密

**规则**：检测 Chromium 版本，需要时提示管理员提权

**代码**：`src/fluentytdl/auth/cookie_manager.py`

### 5.4 JSON Cookie 文件拒绝

**症状**：用户提供 JSON 格式的 cookies，yt-dlp 忽略它们

**根因**：yt-dlp 只接受 Netscape 格式

**规则**：检测 JSON cookie 文件并给出明确的警告信息

**代码**：`src/fluentytdl/youtube/youtube_service.py`

## 6. VR 视频

### 6.1 双通道提取

**症状**：VR 视频只显示低分辨率格式

**根因**：默认客户端不暴露高分辨率 VR 格式；需要 `android_vr` 客户端

**规则**：VR 模式始终使用 `extract_vr_info_sync()` 并设置 `player_client=["android_vr"]`

**代码**：`src/fluentytdl/youtube/youtube_service.py:1229`

### 6.2 EAC 到等矩形投影转换

**症状**：VR 视频在非 VR 播放器中以错误投影播放

**根因**：部分 YouTube VR 视频使用 EAC（等角立方体贴图）投影

**规则**：如果投影为 EAC 且自动转换已启用，运行 ffmpeg `v360=eac:e` 滤镜

**代码**：`src/fluentytdl/download/features.py:308` — `VRFeature.on_post_process()`

### 6.3 VR 检测启发式

**症状**：非 VR 视频被错误检测为 VR，或 VR 视频被遗漏

**根因**：VR 检测使用多个信号：标题关键词、格式元数据、分辨率异常

**规则**：检查投影字段、标签和标题中的关键词（360、VR、vr180、equirectangular）

**代码**：`src/fluentytdl/core/video_analyzer.py`

## 7. 沙箱下载模型

### 7.1 每个任务的临时目录

**症状**：取消时部分文件污染下载目录

**根因**：直接下载到最终目录在失败时留下碎片

**规则**：每个下载在 `.fluent_temp/task_<id>/` 中运行；仅成功后才移动文件到最终目录

**代码**：`src/fluentytdl/download/workers.py` — `DownloadWorker` 中的沙箱创建

### 7.2 取消清理延迟

**症状**：取消时沙箱目录未完全删除

**根因**：进程终止后 Windows 文件锁释放需要时间

**规则**：进程杀死后等待 1 秒再清理沙箱目录

**代码**：`src/fluentytdl/download/workers.py` — 取消清理逻辑
