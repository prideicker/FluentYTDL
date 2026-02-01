# Cookie 错误处理改进

## 问题分析

在全新 Win11 测试环境中发现：
1. ✅ UI 线程通信正常（按钮能恢复）
2. ❌ Cookie 提取失败（浏览器未安装/未登录）
3. ❌ 错误消息不够友好，用户不知道如何解决

## 改进内容

### 1. 增强错误信息（CookieRefreshWorker）

**位置**: `src/fluentytdl/ui/settings_page.py` (第43-103行)

```python
class CookieRefreshWorker(QThread):
    def run(self):
        # 原始提取
        success, message = cookie_sentinel.force_refresh_with_uac()
        
        # 增强错误信息
        if not success:
            status = auth_service.last_status
            
            # 检测具体错误类型并给出友好提示
            if "未找到" in message or "not found" in message.lower():
                message = (
                    f"无法从 {browser_name} 提取 Cookie\n\n"
                    "可能的原因：\n"
                    f"1. {browser_name} 未安装或未登录 YouTube\n"
                    f"2. {browser_name} Cookie 数据库被锁定（请关闭浏览器）\n"
                    "3. 浏览器版本不兼容\n\n"
                    "建议：\n"
                    "• 确保已在浏览器中登录 YouTube\n"
                    "• 完全关闭浏览器后重试\n"
                    "• 尝试切换到其他浏览器（如 Edge）"
                )
```

### 2. 改进 AuthService 错误消息

**位置**: `src/fluentytdl/core/auth_service.py` (第560-580行)

```python
if not cookies:
    browser_display = BROWSER_SOURCES.get(browser, browser.capitalize())
    self._last_status = AuthStatus(
        valid=False,
        message=(
            f"无法从 {browser_display} 提取 Cookie\n\n"
            "可能的原因：\n"
            f"1. {browser_display} 未安装\n"
            f"2. 未在 {browser_display} 中登录 YouTube\n"
            f"3. {browser_display} 正在运行（Cookie 数据库被锁定）\n\n"
            "建议：\n"
            "• 确保已在浏览器中登录 YouTube\n"
            "• 完全关闭浏览器后重试\n"
            "• 尝试使用其他浏览器（如 Edge）"
        ),
    )
```

### 3. 多行错误消息支持

**位置**: `src/fluentytdl/ui/settings_page.py`

#### 手动刷新 (第1053-1076行)
```python
def on_finished(success: bool, message: str):
    if not success:
        # 将第一行作为标题，其余作为内容
        lines = message.split('\n')
        if len(lines) > 1:
            title = lines[0]
            content = '\n'.join(lines[1:])
        else:
            title = "Cookie 刷新失败"
            content = message
        
        InfoBar.error(
            title,
            content,
            duration=15000,  # 错误消息显示更久，方便用户阅读
            parent=self
        )
```

#### 浏览器切换 (第998-1017行)
```python
def on_finished(success: bool, message: str):
    if not success:
        lines = message.split('\n')
        if len(lines) > 1:
            title = f"{name} - {lines[0]}"
            content = '\n'.join(lines[1:])
        else:
            title = f"{name} 提取失败"
            content = message
        
        InfoBar.error(title, content, duration=15000, parent=self)
```

## 用户体验改进

### 之前
```
❌ 刷新失败
   未找到 youtube 的 Cookie，请确保已登录
```

### 现在
```
❌ 无法从 Edge 提取 Cookie

   可能的原因：
   1. Edge 未安装或未登录 YouTube
   2. Edge Cookie 数据库被锁定（请关闭浏览器）
   3. 浏览器版本不兼容

   建议：
   • 确保已在浏览器中登录 YouTube
   • 完全关闭浏览器后重试
   • 尝试切换到其他浏览器（如 Edge）
```

## 错误类型覆盖

| 错误类型 | 检测关键词 | 友好提示 |
|---------|-----------|---------|
| 浏览器未安装/未登录 | "未找到", "not found" | 详细原因 + 操作建议 |
| Cookie 解密失败 | "decrypt", "解密" | rookiepy已知问题，建议换浏览器 |
| 权限不足 | "权限", "permission" | UAC授权指引 |
| 用户取消UAC | "拒绝", "denied" | 说明需要点击"是" |

## 测试场景

### 场景 1: 全新Win11系统（无浏览器Cookie）
1. 打开程序，设置页选择"自动提取"
2. 选择"Edge"
3. 点击"立即刷新"

**预期结果**：
```
❌ 无法从 Edge 提取 Cookie

   可能的原因：
   1. Edge 未安装或未登录 YouTube
   2. Edge Cookie 数据库被锁定（请关闭浏览器）
   ...
```

### 场景 2: 浏览器已安装但未登录
1. 有浏览器但未登录YouTube
2. 点击刷新

**预期结果**：同场景1

### 场景 3: 浏览器正在运行
1. 打开Edge并访问YouTube
2. 不关闭浏览器，点击刷新

**预期结果**：
- 如果成功提取：显示成功
- 如果锁定：显示"Cookie 数据库被锁定"提示

### 场景 4: Chrome v130+ 需要UAC
1. 选择Chrome
2. 点击刷新，弹出UAC

**情况A - 用户点击"是"**：
```
✅ Cookie 已更新（Chrome）
   提取了 42 个 Cookie
   (通过管理员权限)
```

**情况B - 用户点击"否"**：
```
❌ 用户取消了管理员权限授权

   Chrome (v130+) 需要管理员权限才能提取 Cookie
   请在 UAC 弹窗中点击「是」以允许提取
```

## 相关文件

- `src/fluentytdl/ui/settings_page.py`:
  - 第43-103行: CookieRefreshWorker（错误增强）
  - 第1053-1076行: 手动刷新错误显示
  - 第998-1017行: 浏览器切换错误显示

- `src/fluentytdl/core/auth_service.py`:
  - 第560-580行: rookiepy提取失败的友好错误

- `src/fluentytdl/core/cookie_sentinel.py`:
  - 第118-217行: 强制刷新逻辑（已有完整错误处理）

## 打包测试

```powershell
# 1. 重新打包
scripts\build_windows.ps1

# 2. 在全新 Win11 测试
dist\FluentYTDL.exe

# 3. 验证错误提示
- 启动时：查看是否有友好提示
- 手动刷新：查看错误消息是否详细
- 按钮状态：确认能正常恢复
```

## 后续优化方向

1. **浏览器检测**：在选择浏览器前检测是否安装
2. **Cookie预检**：显示浏览器登录状态
3. **一键登录**：提供快速打开浏览器登录的按钮
4. **多浏览器回退**：自动尝试其他浏览器
