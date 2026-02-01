# 管理员重启方案 - 完整实现

## 设计理念

参考 v2ray TUN 模式，当检测到需要管理员权限时，直接提示用户**以管理员身份重启整个程序**，而不是使用子进程UAC提权。

### 优势对比

| 方案 | 旧方案（子进程UAC） | 新方案（整体重启） |
|------|-------------------|-------------------|
| 复杂度 | 高（进程间通信、临时文件） | 低（单一进程） |
| 可靠性 | 中（打包后可能失败） | 高（系统级重启） |
| 用户体验 | 等待60秒UAC超时 | 立即重启，自动完成 |
| 权限范围 | 仅子进程 | 整个程序 |
| 兼容性 | 打包环境可能有问题 | 完美兼容 |

## 实现架构

### 1. 核心工具模块

**文件**: `src/fluentytdl/utils/admin_utils.py`

```python
def is_admin() -> bool:
    """检查当前进程是否以管理员身份运行"""
    return bool(ctypes.windll.shell32.IsUserAnAdmin())

def restart_as_admin(reason: str = "") -> bool:
    """以管理员身份重启当前程序"""
    # 使用 ShellExecuteW 请求提权
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, 
        '--admin-mode', None, 1
    )
    if ret > 32:  # 成功
        sys.exit(0)  # 退出当前进程
    return False

def get_admin_status_message() -> str:
    """获取当前管理员状态的友好消息"""
    return "✅ 当前以管理员身份运行" if is_admin() else "ℹ️ 当前以普通用户身份运行"
```

### 2. 主程序入口增强

**文件**: `main.py`

```python
# 检测管理员模式（新方案）
IS_ADMIN_MODE = "--admin-mode" in sys.argv
if IS_ADMIN_MODE:
    # 移除参数，避免传递给 Qt
    sys.argv = [arg for arg in sys.argv if arg != "--admin-mode"]
```

### 3. Cookie 刷新 Worker 增强

**文件**: `src/fluentytdl/ui/settings_page.py`

```python
class CookieRefreshWorker(QThread):
    """Cookie刷新工作线程"""
    finished = Signal(bool, str, bool)  # (成功, 消息, 需要管理员权限)
    
    def run(self):
        success, message = cookie_sentinel.force_refresh_with_uac()
        need_admin = False
        
        if not success:
            # 检测是否需要管理员权限
            if ("v130" in message or "admin" in message.lower()):
                if not is_admin():
                    need_admin = True
                    message = (
                        f"[需要管理员权限]\n\n"
                        f"{browser_name} v130+ 需要管理员权限提取 Cookie。\n\n"
                        "建议操作：\n"
                        "1. 点击「以管理员身份重启」按钮\n"
                        "2. 重启后自动完成 Cookie 提取\n\n"
                        "或切换到其他浏览器（Firefox/Brave 无需管理员权限）"
                    )
        
        self.finished.emit(success, message, need_admin)
```

### 4. UI 回调处理

**手动刷新按钮回调**:

```python
def on_finished(success: bool, message: str, need_admin: bool = False):
    if not success and need_admin:
        # 显示带重启按钮的对话框
        from qfluentwidgets import MessageBox
        
        box = MessageBox("需要管理员权限", content, self)
        box.yesButton.setText("以管理员身份重启")
        box.cancelButton.setText("取消")
        
        if box.exec():
            from ..utils.admin_utils import restart_as_admin
            restart_as_admin("提取 Chrome/Edge v130+ Cookie")
```

### 5. 主窗口管理员模式处理

**文件**: `src/fluentytdl/ui/reimagined_main_window.py`

```python
def __init__(self):
    # 检查管理员模式
    self._is_admin = is_admin()
    
    # 窗口标题添加标识
    title = "FluentYTDL Pro"
    if self._is_admin:
        title += " (管理员)"
    self.setWindowTitle(title)
    
    # 管理员模式：自动刷新 Cookie
    if self._is_admin:
        QTimer.singleShot(2000, self.on_admin_mode_cookie_refresh)

def on_admin_mode_cookie_refresh(self):
    """管理员模式启动后自动刷新Cookie"""
    success, message = cookie_sentinel.force_refresh_with_uac()
    
    if success:
        InfoBar.success(
            "Cookie提取成功",
            f"已从 {browser_name} 提取 Cookie（管理员权限）",
            duration=5000
        )
        # 自动跳转到设置页显示结果
        QTimer.singleShot(1000, lambda: self.switchTo(self.settings_interface))
```

## 用户体验流程

### 场景 1: 普通用户点击刷新 (Chrome v130+)

1. 用户点击"立即刷新"
2. 检测到需要管理员权限
3. 弹出对话框:
   ```
   ┌─────────────────────────────────────┐
   │ 需要管理员权限                       │
   ├─────────────────────────────────────┤
   │ Chrome v130+ 需要管理员权限提取     │
   │ Cookie。                            │
   │                                     │
   │ 建议操作：                          │
   │ 1. 点击「以管理员身份重启」按钮     │
   │ 2. 重启后自动完成 Cookie 提取       │
   ├─────────────────────────────────────┤
   │      [以管理员身份重启]   [取消]     │
   └─────────────────────────────────────┘
   ```
4. 用户点击"以管理员身份重启"
5. 弹出 UAC 对话框，用户点击"是"
6. 程序以管理员身份重新启动
7. 窗口标题显示 "FluentYTDL Pro (管理员)"
8. 2秒后自动提取 Cookie
9. 提取成功，自动跳转到设置页

### 场景 2: 已经是管理员身份

1. 启动程序，标题显示 "FluentYTDL Pro (管理员)"
2. 2秒后自动提取 Cookie（无需 UAC 弹窗）
3. 提取成功提示
4. 自动跳转到设置页显示状态

### 场景 3: Firefox/Brave（无需管理员）

1. 普通用户启动即可
2. 点击刷新直接提取成功
3. 无需任何额外操作

## 技术细节

### Windows UAC 提权

```python
ctypes.windll.shell32.ShellExecuteW(
    None,           # hwnd: 父窗口句柄
    "runas",        # lpOperation: 请求管理员权限
    sys.executable, # lpFile: 要运行的程序
    '--admin-mode', # lpParameters: 参数
    None,           # lpDirectory: 工作目录
    1               # nShowCmd: SW_SHOWNORMAL
)
```

返回值:
- `> 32`: 成功
- `≤ 32`: 失败或用户取消

### 参数传递

- `--admin-mode`: 标识这是管理员模式启动
- 在 `main.py` 中检测并移除此参数
- 启动后在主窗口自动执行 Cookie 提取

### 进程生命周期

```
[普通进程]
    ↓ 用户点击"以管理员身份重启"
    ↓ ShellExecuteW("runas")
    ↓ 弹出 UAC
    ↓ 用户点击"是"
[管理员进程] (新进程)
    ↓ 检测 --admin-mode
    ↓ 启动 GUI
    ↓ 2秒后自动刷新 Cookie
    ↓ 提取成功
    ↓ 跳转设置页
```

旧进程在请求成功后会调用 `sys.exit(0)` 退出。

## 测试验证

### 本地测试

```bash
# 1. 测试权限检测
python scripts/test_admin_restart.py

# 2. 普通用户启动程序
python main.py

# 3. 进入设置页，选择 Chrome/Edge
# 4. 点击"立即刷新"
# 5. 如果需要管理员权限，点击"以管理员身份重启"
# 6. UAC 确认后，程序重启并自动提取
```

### 打包测试

```powershell
# 1. 打包
scripts\build_windows.ps1

# 2. 运行 exe
dist\FluentYTDL_build_*\FluentYTDL.exe

# 3. 测试重启功能
```

### 验证点

- [ ] 普通用户运行，标题显示 "FluentYTDL Pro"
- [ ] 管理员运行，标题显示 "FluentYTDL Pro (管理员)"
- [ ] 点击重启按钮后弹出 UAC
- [ ] UAC 确认后程序重新启动
- [ ] 管理员模式自动刷新 Cookie
- [ ] 刷新成功后跳转设置页
- [ ] Cookie 信息正确显示

## 与旧方案对比

### 旧方案 (子进程 UAC)

```python
# elevated_extractor.py 作为子进程运行
def _run_elevated_extractor():
    # 1. ShellExecuteW 启动子进程
    # 2. 子进程提取 Cookie 写入临时文件
    # 3. 主进程读取临时文件
    # 4. 清理临时文件
    
# 问题：
# - 进程间通信复杂
# - 临时文件管理
# - 打包后路径问题
# - 60秒超时等待
```

### 新方案 (整体重启)

```python
# admin_utils.py 重启整个程序
def restart_as_admin():
    # 1. ShellExecuteW 重启程序
    # 2. 添加 --admin-mode 参数
    # 3. 退出当前进程
    
# main.py 检测管理员模式
if '--admin-mode' in sys.argv:
    # 启动管理员模式
    
# MainWindow 自动刷新
if is_admin():
    QTimer.singleShot(2000, self.on_admin_mode_cookie_refresh)

# 优势：
# - 单一进程，无通信问题
# - 无临时文件
# - 完美兼容打包
# - 即时完成
```

## 相关文件

- `src/fluentytdl/utils/admin_utils.py`: 管理员权限工具
- `src/fluentytdl/ui/settings_page.py`: Cookie 刷新 UI
- `src/fluentytdl/ui/reimagined_main_window.py`: 主窗口管理员模式处理
- `main.py`: 入口参数检测
- `scripts/test_admin_restart.py`: 测试脚本

## 未来优化方向

1. **记住用户选择**: 首次提示后记住用户是否愿意以管理员身份运行
2. **启动时检测**: 如果检测到 Chrome v130+，启动时就提示以管理员身份运行
3. **右键菜单**: 在 exe 上添加"以管理员身份运行"快捷方式
4. **配置选项**: 添加"总是以管理员身份运行"选项
