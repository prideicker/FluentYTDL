# Cookie 卫士 - 集成检查清单

## ✅ 已完成的文件修改

### 1. 新增文件

- [x] `src/fluentytdl/core/cookie_sentinel.py` - 核心模块
- [x] `src/fluentytdl/ui/components/cookie_repair_dialog.py` - 修复对话框
- [x] `docs/cookie_sentinel_implementation.md` - 技术文档
- [x] `docs/cookie_sentinel_user_guide.md` - 用户指南
- [x] `tests/test_cookie_sentinel.py` - 功能测试

### 2. 修改的文件

- [x] `main.py` - 添加启动时静默刷新
- [x] `src/fluentytdl/youtube/youtube_service.py` - Cookie 路径集成
- [x] `src/fluentytdl/download/workers.py` - 错误检测信号
- [x] `src/fluentytdl/ui/components/download_card.py` - UI 修复流程

---

## 🧪 测试步骤

### 步骤 1: 运行自动化测试

```bash
cd d:\YouTube\FluentYTDL
python tests\test_cookie_sentinel.py
```

**期望输出**：
```
✅ 通过  test_imports
✅ 通过  test_sentinel_initialization
✅ 通过  test_auth_service_integration
✅ 通过  test_cookie_error_detection
✅ 通过  test_status_info
✅ 通过  test_silent_refresh_simulation

总计: 6/6 通过
🎉 所有测试通过！Cookie 卫士功能正常。
```

### 步骤 2: 验证启动流程

1. 启动应用
   ```bash
   python main.py
   ```

2. 检查日志输出（查找关键字）
   ```
   [CookieSentinel] 初始化: ...
   [CookieSentinel] 启动时静默刷新开始...
   ```

3. 确认无 UAC 弹窗（静默模式）

4. 检查文件是否生成
   ```bash
   ls bin/cookies.txt
   ```

### 步骤 3: 测试下载流程

1. 配置验证源
   - 打开设置 → 身份验证
   - 选择 Edge 浏览器
   - 点击"应用"

2. 尝试下载视频
   - 粘贴 YouTube URL
   - 点击下载
   - 观察日志中的 Cookie 状态信息

3. 检查 yt-dlp 命令
   - 日志中应包含：`--cookies "bin/cookies.txt"`

### 步骤 4: 测试错误检测

**方法 1：删除 Cookie 文件**
```bash
rm bin/cookies.txt
```

然后尝试下载会员专属视频，应弹出修复对话框。

**方法 2：使用测试 URL**

使用已知需要登录的视频：
- 会员专属视频
- 年龄限制视频
- 私有视频

### 步骤 5: 测试修复流程

1. 触发 Cookie 错误（使用步骤 4）

2. 观察对话框弹出
   - 标题："🔒 检测到 Cookie 验证失败"
   - 按钮："稍后处理"、"手动导入"、"自动修复"

3. 点击"自动修复"
   - 如果使用 Chrome，应弹出 UAC
   - Edge/Firefox 不应弹 UAC

4. 观察修复结果
   - 成功：绿色提示条 + 自动重试
   - 失败：红色提示条 + 错误消息

---

## 🔍 故障排查

### 问题 1: 测试失败

**症状**：`test_cookie_sentinel.py` 报错

**检查点**：
- [ ] rookiepy 是否安装：`pip show rookiepy`
- [ ] 路径是否正确：检查 `sys.path`
- [ ] 依赖模块是否存在：检查 `src/fluentytdl/core/` 目录

**解决**：
```bash
pip install rookiepy
```

### 问题 2: 启动时无日志输出

**症状**：看不到 `[CookieSentinel]` 日志

**检查点**：
- [ ] logger 配置是否正确
- [ ] 日志级别是否过高（应为 DEBUG 或 INFO）
- [ ] 线程是否正常启动

**解决**：
查看 `main.py` 中的线程启动代码，确认 `start()` 已调用。

### 问题 3: Cookie 未生成

**症状**：`bin/cookies.txt` 不存在

**检查点**：
- [ ] 是否配置了验证源（不能是 NONE）
- [ ] 浏览器是否已登录 YouTube
- [ ] rookiepy 是否支持该浏览器

**解决**：
1. 手动测试 rookiepy：
   ```python
   import rookiepy
   cookies = rookiepy.edge([".youtube.com"])
   print(len(cookies))
   ```

2. 如果失败，改用手动导入方式

### 问题 4: 修复对话框未弹出

**症状**：Cookie 失效但没有对话框

**检查点**：
- [ ] `cookie_error_detected` 信号是否连接
- [ ] `detect_cookie_error()` 是否返回 True
- [ ] stderr 输出是否包含关键字

**调试**：
在 `workers.py` 中添加打印：
```python
print(f"[DEBUG] Error detection: {cookie_sentinel.detect_cookie_error(error_text)}")
print(f"[DEBUG] Error text: {error_text[:200]}")
```

### 问题 5: UAC 提权失败

**症状**：点击"自动修复"后无反应

**检查点**：
- [ ] `elevated_extractor.py` 是否存在
- [ ] ShellExecuteW 返回值（应 > 32）
- [ ] 临时文件路径是否正确

**调试**：
检查临时文件：
```bash
type %TEMP%\fluentytdl_elevated.log
type %TEMP%\fluentytdl_elevated_cookies.txt
```

---

## 📋 代码审查清单

### 类型检查

- [ ] 所有类型注解正确（`str | None`, `Path`, etc.）
- [ ] 返回值类型匹配
- [ ] 异常处理完整

### 线程安全

- [ ] `_update_lock` 正确使用
- [ ] 单例模式无竞态条件
- [ ] Signal/Slot 线程安全

### 错误处理

- [ ] 所有外部调用都有 try-except
- [ ] 异常消息友好可读
- [ ] 不会因子模块失败而崩溃

### 用户体验

- [ ] 启动时无阻塞（异步线程）
- [ ] 错误提示清晰明确
- [ ] 修复流程流畅连贯

### 性能

- [ ] Cookie 文件缓存有效（5 分钟）
- [ ] 避免频繁浏览器访问
- [ ] yt-dlp 启动速度提升

---

## 🚀 部署检查

### 开发环境

- [ ] 所有测试通过
- [ ] 日志输出正常
- [ ] UI 交互流畅

### 打包环境（PyInstaller）

- [ ] `elevated_extractor.py` 包含在打包中
- [ ] `bin/cookies.txt` 路径正确解析
- [ ] UAC 提权正常工作

### 用户环境

- [ ] 提供清晰的设置指引
- [ ] 错误消息易于理解
- [ ] 支持手动导入备用方案

---

## 📝 文档检查

- [ ] 技术文档完整（`cookie_sentinel_implementation.md`）
- [ ] 用户指南易懂（`cookie_sentinel_user_guide.md`）
- [ ] 代码注释充分
- [ ] 测试脚本可运行

---

## ✅ 最终验收

### 功能验收

- [ ] 启动时静默刷新工作正常
- [ ] 下载时使用统一 Cookie 文件
- [ ] 错误自动检测触发修复
- [ ] 修复成功后自动重试

### 性能验收

- [ ] 启动时间无明显增加（< 0.5 秒）
- [ ] yt-dlp 启动速度提升（无浏览器访问）
- [ ] Cookie 缓存有效减少重复提取

### 用户体验验收

- [ ] 无频繁 UAC 弹窗（除主动修复）
- [ ] 错误提示友好清晰
- [ ] 修复流程简单直观

### 兼容性验收

- [ ] Edge 浏览器正常
- [ ] Firefox 浏览器正常
- [ ] Chrome 浏览器（UAC）正常
- [ ] 手动导入方式正常

---

## 🎯 交付物清单

### 代码文件
- [x] `cookie_sentinel.py`
- [x] `cookie_repair_dialog.py`
- [x] 修改后的 `main.py`
- [x] 修改后的 `youtube_service.py`
- [x] 修改后的 `workers.py`
- [x] 修改后的 `download_card.py`

### 文档文件
- [x] 技术实现文档
- [x] 用户使用指南
- [x] 测试脚本

### 测试验证
- [ ] 运行 `test_cookie_sentinel.py` 并通过
- [ ] 手动测试所有关键场景
- [ ] 性能基准测试

---

**准备就绪！** 可以开始集成测试了。🚀
