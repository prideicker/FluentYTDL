# POT Provider 和 Cookies 载入时序修复

## 🔍 问题诊断

### 日志分析结果

根据您提供的日志，发现以下问题：

#### 1. ⚠️ POT Provider 启动延迟（关键问题）
```
16:58:47.915 | DEBUG | POT Provider 服务未运行，跳过 PO Token 注入  # 下载开始时未载入
16:58:50.927 | INFO  | POT Manager: 服务已启动 (PID: 50456)          # 3秒后才启动完成
```

**原因**：`main.py` 中 POT 服务启动有 3 秒延迟
```python
time.sleep(3)  # 延迟 3 秒，确保主界面完全渲染
```

**影响**：如果用户在程序启动后 3 秒内开始下载，POT Provider 还没准备好，导致：
- 🚫 本次下载不使用 PO Token
- 🚫 可能触发 YouTube 限速（403/429错误）
- 🚫 无法绕过机器人检测

#### 2. ⚠️ POT 服务重复停止
```
16:42:08.533 | INFO | POT Manager: 服务已停止
16:42:08.533 | INFO | POT Manager: 服务已停止  # 重复日志
```

**原因**：`stop_server()` 方法没有检查进程是否已终止，导致重复执行停止逻辑

#### 3. ✅ Cookies 载入正常
```
16:42:02.860 | INFO | [CookieSentinel] 启动时静默刷新成功：Firefox 浏览器
16:42:02.860 | INFO | [CookieSentinel] 提取了 61 个 Cookie
16:42:02.860 | INFO | ✅ Cookie Sentinel: Firefox 浏览器 (更新于 0分钟前, 59 个 YouTube Cookie)
```

**结论**：Cookie Sentinel 工作完全正常，每次下载都能正确载入 Cookies

---

## ✅ 修复方案

### 1. 减少 POT 启动延迟 (main.py)

**修改前**:
```python
time.sleep(3)  # 延迟 3 秒，确保主界面完全渲染
```

**修改后**:
```python
time.sleep(1)  # 延迟 1 秒（从3秒改为1秒，减少等待时间）

# 添加重试机制（最多3次）
for attempt in range(3):
    if pot_manager.start_server():
        logger.info("POT Provider 服务已启动")
        break
    elif attempt < 2:
        logger.debug(f"POT Provider 启动尝试 {attempt + 1} 失败，1秒后重试...")
        time.sleep(1)
    else:
        logger.warning("POT Provider 服务启动失败：已达到最大重试次数")
```

**效果**：
- ✅ 启动时间从 3 秒减少到 1-3 秒（取决于重试次数）
- ✅ 增加启动可靠性（3次重试机会）
- ✅ 用户可更快开始下载

### 2. 防止 POT 服务重复停止 (pot_manager.py)

**修改前**:
```python
def stop_server(self):
    with self._lock:
        if self._process:
            self._process.terminate()
            # ...
        logger.info("POT Manager: 服务已停止")  # 每次都输出
```

**修改后**:
```python
def stop_server(self):
    with self._lock:
        # 防止重复停止（如果进程已经不存在了）
        if not self._is_running and self._process is None:
            logger.debug("POT Manager: 服务未运行，跳过停止操作")
            return
        
        if self._process:
            # 检查进程是否已经终止
            if self._process.poll() is not None:
                logger.debug("POT Manager: 进程已终止，跳过停止操作")
                return
            # ...
```

**效果**：
- ✅ 避免重复停止日志
- ✅ 减少不必要的系统调用
- ✅ 更准确的状态管理

### 3. 提升 POT 未运行的日志级别 (youtube_service.py)

**修改前**:
```python
self._emit_log("debug", "POT Provider 服务未运行，跳过 PO Token 注入")
```

**修改后**:
```python
self._emit_log("warning", "⚠️ POT Provider 服务未运行，本次下载将不使用 PO Token（可能触发限速）")
```

**效果**：
- ✅ 用户能立即看到 POT 未载入的警告
- ✅ 理解可能的性能影响（限速、403错误）
- ✅ 提示用户等待 POT 服务启动完成

---

## 📊 修复效果对比

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| **启动后立即下载** | ❌ POT未就绪，不使用PO Token | ✅ 1秒后就绪（3秒→1秒） |
| **POT启动失败** | ❌ 无重试，永久失败 | ✅ 自动重试3次 |
| **重复停止** | ⚠️ 重复日志 "服务已停止" | ✅ 智能检测，避免重复 |
| **POT未运行提示** | ❌ DEBUG级别（用户看不到） | ✅ WARNING级别（明显提示） |
| **Cookies载入** | ✅ 正常工作 | ✅ 正常工作（无变化） |

---

## 🔍 验证方法

### 1. 检查 POT 启动时机
启动程序后观察日志：
```
[期望看到]
[--:--:--] [INFO] POT Provider 服务已启动            # 1-3秒内出现
[不应看到]
[--:--:--] [WARNING] ⚠️ POT Provider 服务未运行...   # 如果频繁出现说明有问题
```

### 2. 检查重复停止
退出程序或停止下载时：
```
[期望看到]
[--:--:--] [INFO] POT Manager: 服务已停止           # 只出现一次
[不应看到]
[--:--:--] [INFO] POT Manager: 服务已停止           # 不应该重复
[--:--:--] [INFO] POT Manager: 服务已停止
```

### 3. 验证 POT + Cookies 组合
下载时查看日志开头：
```
[正常状态]
✅ Cookie Sentinel: Firefox 浏览器 (更新于 0分钟前, 60 个 YouTube Cookie)
🚀 Cookies 模式激活：使用 Web 默认客户端获取更完整的格式列表
🛡️ POT Provider 已激活: 端口 4416 (自动绕过机器人检测)      # ← 关键行

[异常状态]
✅ Cookie Sentinel: Firefox 浏览器 (...)
🚀 Cookies 模式激活：...
⚠️ POT Provider 服务未运行，本次下载将不使用 PO Token（可能触发限速）  # ← 问题提示
```

---

## 🎯 使用建议

### 快速下载场景
如果您经常在启动后立即开始下载：

**方案 A：等待 1-2 秒**
- 启动程序后等待 1-2 秒再添加下载任务
- 观察日志确认看到 "POT Provider 服务已启动"

**方案 B：检查状态指示**
- 未来可在 UI 添加 POT 状态指示器（绿灯=已就绪）
- 目前可在日志中确认

### 频繁启停场景
- ✅ 暂停/恢复不会重启 POT 服务（保持连接）
- ✅ 只有退出程序才会停止 POT 服务
- ✅ 修复后不会再看到重复停止日志

### 错误排查
如果仍然看到 "POT Provider 服务未运行"：
1. 检查端口 4416 是否被占用
2. 查看日志是否有 "POT Provider 服务启动失败" 错误
3. 检查 `assets/bin/pot-provider/` 目录下是否有可执行文件

---

## 📁 修改的文件

| 文件 | 修改内容 | 影响 |
|------|----------|------|
| `main.py` | 减少启动延迟（3秒→1秒）+ 重试机制 | POT更快就绪 |
| `pot_manager.py` | 防止重复停止 + 状态检查 | 避免重复日志 |
| `youtube_service.py` | POT未运行提示改为WARNING级别 | 用户可见警告 |

---

## 📌 总结

### ✅ Cookies 状态
**完全正常**，每次下载都正确载入 60+ 个 Firefox Cookie，Cookie Sentinel 工作良好。

### ⚠️ POT Provider 状态（已修复）
**之前有时序问题**：
- 启动延迟 3 秒导致快速下载时未就绪
- 重复停止导致日志混乱

**修复后**：
- ✅ 启动时间缩短到 1-3 秒
- ✅ 自动重试 3 次提高成功率
- ✅ 避免重复停止
- ✅ 明确提示 POT 未运行的情况

### 🎯 建议
启动程序后**等待 1-2 秒**再开始下载，确保 POT Provider 完全就绪，以获得最佳下载体验（绕过限速、避免 403 错误）。
