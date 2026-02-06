# 格式降级问题修复文档

## 问题描述

### 现象
用户报告在频繁启停下载/暂停操作时，出现**跳过视频下载转向音频下载**的问题。

### 日志分析
```
ERROR: [download] Got error: EOF occurred in violation of protocol (_ssl.c:1007). Giving up after 10 retries
FLUENTYTDL|download|179619576|368045857|...|av01.0.09M.08|none|mp4|...  # 视频流下载
FLUENTYTDL|download|203329162|368045857|...|none|mp4a.40.2|m4a|...      # 切换到音频流！
```

### 根本原因

1. **格式选择器降级机制**：
   - 用户选择的格式字符串：`bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4] / bv*[height<=1080]+ba/b[height<=1080]`
   - 格式字符串中有多个 `/` 分隔的选项（降级路径）
   - 当第一个选项（视频+音频组合）遇到网络错误失败时，yt-dlp自动降级到第二个选项
   - 最后一个选项 `b[height<=1080]` 没有明确视频标识，可能被解析为纯音频

2. **SSL网络错误**：
   - 视频流下载到 50% 时遇到 `EOF occurred in violation of protocol (_ssl.c:1007)`
   - yt-dlp重试10次后放弃，触发格式降级机制

3. **格式字符串解析问题**：
   - 原格式字符串中有**空格+斜杠+空格** (`  /  `)，可能导致解析不一致
   - 最后的 `b[height<=1080]` 缺少 `*` 通配符，降级时可能匹配不到合适的视频流

## 修复方案

### 1. 格式选择器优化 (`format_selector.py`)

**修改前**：
```python
"bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4] / bv*[height<=1080]+ba/b[height<=1080]"
```

**修改后**：
```python
"bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba"
```

**改进点**：
- ✅ 移除空格分隔符（统一使用紧凑格式）
- ✅ 移除最后的 `b[height<=1080]` 模糊选项
- ✅ 确保所有降级选项都明确包含视频流（`bv*` 或 `b[...]`）
- ✅ 降级顺序更合理：MP4组合 → Muxed MP4 → 任意编码组合

### 2. 格式验证机制 (`workers.py`)

**新增功能**：
```python
self._original_format: str | None = None  # 保存原始格式选择
self._ssl_error_count = 0                 # SSL错误计数器
```

**新增验证方法**：
```python
def _validate_format_selection(self, format_str: str | None) -> str | None:
    """验证格式选择，防止自动降级到纯音频"""
    # 检测纯音频关键词：bestaudio, ba, aac, mp3, opus...
    # 检测视频关键词：bv, video, mp4, webm, h264, av01...
    # 如果格式只有音频没有视频，发出警告
```

**实时监控**（进度追踪中）：
```python
# 在下载进度中检测 vcodec 和 acodec
if vcodec in ("", "NA", "none") and acodec not in ("", "NA", "none"):
    # 原本选择了视频，但现在只下载音频！
    logger.warning("[FormatDownload] 🔴 格式降级警告！")
    self.status_msg.emit("⚠️ 检测到格式降级：原始选择了视频，但现在仅下载音频！")
```

### 3. SSL错误检测与提示

```python
has_ssl_error = "EOF occurred in violation of protocol" in error_text or "_ssl.c" in error_text
if has_ssl_error:
    self._ssl_error_count += 1
    logger.warning("检测到SSL错误 (第 {} 次)", self._ssl_error_count)
    self.status_msg.emit("⚠️ 检测到网络SSL错误，建议检查网络连接后重试")
```

## 修复效果

### 改进前
1. 遇到网络错误 → 自动降级到 `b[height<=1080]`
2. `b[height<=1080]` 匹配失败 → 继续降级（可能到纯音频）
3. 用户不知道发生了格式降级，误认为是下载逻辑错误

### 改进后
1. ✅ 格式字符串更精确，降级路径明确保留视频流
2. ✅ 实时监控 vcodec/acodec，检测到纯音频下载时立即警告
3. ✅ SSL错误专门检测，提示用户网络问题而不是格式问题
4. ✅ 保存原始格式选择，用于错误诊断和恢复

## 用户指引

### 遇到格式降级时
1. **检查网络连接**：SSL错误通常是网络抖动或防火墙导致
2. **重新选择格式**：如果格式已降级，建议清除任务重新添加
3. **使用断点续传**：启用"断点续传"功能（默认已启用），避免重新下载

### 推荐设置
- ✅ 启用断点续传（`enable_resume: true`）
- ✅ 使用简易模式预设（已优化格式字符串）
- ✅ 专业模式下避免使用纯音频格式（除非明确需要）

## 技术细节

### yt-dlp格式选择器语法
```
format_spec := selector [ "/" selector ] ...
selector    := field_filter [ "+" field_filter ] ...
field_filter := field operator value
```

### 降级顺序（从左到右）
1. `bv*[height<=1080][ext=mp4]+ba[ext=m4a]` - 优先：MP4视频 + M4A音频
2. `b[height<=1080][ext=mp4]` - 次选：1080p Muxed MP4
3. `bv*[height<=1080]+ba` - 最后：任意编码的视频+音频组合

### 关键修复点
- 移除 `b[height<=1080]` 末尾无编码限制的选项（可能被误解析为纯音频）
- 所有降级选项都明确包含视频标识（`bv*` 或 `b[ext=mp4]`）
- 运行时验证实际下载的codec，检测格式降级

## 相关文件

| 文件 | 修改内容 |
|------|----------|
| `src/fluentytdl/download/workers.py` | 添加格式验证、SSL错误检测、运行时监控 |
| `src/fluentytdl/ui/components/format_selector.py` | 优化格式字符串，移除降级路径中的歧义选项 |

## 测试建议

1. **模拟网络抖动**：使用网络限速工具测试断点续传
2. **验证格式保持**：启停下载多次，确认格式不变
3. **日志监控**：观察 `[FormatDownload]` 和 `[FormatValidator]` 日志

## 版本信息

- **修复版本**：1.0.20
- **修复日期**：2026-02-05
- **相关Issue**：频繁启停下载暂停操作导致格式降级

---

**⚠️ 重要提示**：此修复主要解决格式选择器的降级逻辑问题。网络环境不稳定时仍可能触发降级，但现在系统会明确提示用户。
