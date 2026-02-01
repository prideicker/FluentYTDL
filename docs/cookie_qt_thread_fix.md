# Cookie 刷新 Qt 线程修复

## 问题描述

打包后的程序在手动刷新Cookie时，UI状态无法正确更新：
- 点击"立即刷新"按钮后，UAC提示通过
- UI卡在"刷新中..."状态
- Cookie信息无法更新
- 按钮无法恢复

## 根本原因

原实现使用 `threading.Thread` + `QTimer.singleShot(0, callback)` 进行线程间通信：

```python
def refresh_in_background():
    success, message = cookie_sentinel.force_refresh_with_uac()
    
    def update_ui():
        self.refreshCookieCard.setEnabled(True)
        # ...更新UI
    
    QTimer.singleShot(0, update_ui)  # ❌ 打包后不可靠

thread = threading.Thread(target=refresh_in_background, daemon=True)
thread.start()
```

**问题**：在PyInstaller打包的exe环境中，从Python线程调用`QTimer.singleShot()`可能失败，回调函数不会被执行。

## 解决方案

使用Qt原生的 **QThread + Signal/Slot** 机制：

### 1. 创建 CookieRefreshWorker 类

```python
class CookieRefreshWorker(QThread):
    """Cookie刷新工作线程（Qt线程，打包后可靠）"""
    finished = Signal(bool, str)  # (成功标志, 消息)
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def run(self):
        """在Qt线程中执行Cookie刷新"""
        from ..core.cookie_sentinel import cookie_sentinel
        
        success = False
        message = "未知错误"
        
        try:
            success, message = cookie_sentinel.force_refresh_with_uac()
        except Exception as e:
            success = False
            message = f"刷新异常: {str(e)}"
        
        # 发射信号（线程安全）
        self.finished.emit(success, message)
```

### 2. 修改刷新函数

#### 手动刷新（`_on_refresh_cookie_clicked`）

```python
def _on_refresh_cookie_clicked(self):
    """手动刷新 Cookie 按钮点击（Qt线程版本）"""
    # 禁用按钮
    self.refreshCookieCard.setEnabled(False)
    self.refreshCookieCard.button.setText("刷新中...")
    
    # 创建Qt工作线程
    worker = CookieRefreshWorker(self)
    
    # 连接信号（自动在主线程执行）✅
    def on_finished(success: bool, message: str):
        # 重置按钮状态
        self.refreshCookieCard.setEnabled(True)
        self.refreshCookieCard.button.setText("立即刷新")
        
        # 显示结果
        if success:
            InfoBar.success("刷新成功", message, duration=8000, parent=self)
        else:
            InfoBar.error("刷新失败", message, duration=10000, parent=self)
        
        # 更新状态显示
        self._update_cookie_status()
        
        # 清理worker
        worker.deleteLater()
    
    worker.finished.connect(on_finished)
    worker.start()
```

#### 浏览器切换（`_on_cookie_browser_changed`）

```python
def _on_cookie_browser_changed(self, index: int) -> None:
    """浏览器选择变化（Qt线程版本）"""
    # ...设置新浏览器
    
    # 创建Qt工作线程
    worker = CookieRefreshWorker(self)
    
    # 连接信号
    def on_finished(success: bool, message: str):
        if success:
            InfoBar.success("切换成功", f"已从 {name} 提取 Cookies", parent=self)
        else:
            InfoBar.error(f"{name} 提取失败", message, parent=self)
        
        self._update_cookie_status()
        worker.deleteLater()
    
    worker.finished.connect(on_finished)
    worker.start()
```

## 技术优势

### Qt信号/槽机制 vs QTimer

| 特性 | QTimer.singleShot | Qt Signal/Slot |
|------|-------------------|----------------|
| 线程安全 | ❌ 从非Qt线程调用不可靠 | ✅ 自动跨线程 |
| 打包兼容性 | ❌ exe环境可能失败 | ✅ 完全可靠 |
| 代码可读性 | 中等（嵌套函数） | ✅ 清晰（信号->槽） |
| 内存管理 | 手动 | ✅ deleteLater() |
| Qt事件循环集成 | 依赖Timer | ✅ 原生集成 |

### 信号自动跨线程机制

Qt的Signal/Slot系统自动处理跨线程调用：

1. **Worker线程**（后台）：
   ```python
   self.finished.emit(success, message)  # 在Worker线程执行
   ```

2. **Qt自动排队**：
   - 检测到跨线程信号
   - 将槽函数调用放入主线程事件队列
   - 类型：`Qt.QueuedConnection`（自动选择）

3. **主线程执行**：
   ```python
   def on_finished(success, message):
       # 这个函数在主线程执行，可以安全操作UI
       self.refreshCookieCard.setEnabled(True)
   ```

## 测试验证

### 开发环境测试
```bash
python main.py
```
1. 进入设置页
2. 点击"立即刷新"
3. 确认UAC提示后，UI应正确更新

### 打包环境测试
```bash
# 打包
scripts\build_windows.ps1

# 运行exe
dist\FluentYTDL.exe
```
1. 进入设置页
2. 点击"立即刷新"
3. 确认UAC提示后，验证：
   - ✅ 按钮恢复为"立即刷新"
   - ✅ 按钮变为可点击状态
   - ✅ InfoBar显示成功/失败消息
   - ✅ Cookie信息更新显示

### 切换浏览器测试
1. 在Cookie模式下拉框选择"自动提取"
2. 在浏览器下拉框切换不同浏览器
3. 验证每次切换后UI正确更新

## 相关文件

- `src/fluentytdl/ui/settings_page.py`: 
  - 第40-67行：CookieRefreshWorker类
  - 第920-972行：`_on_cookie_browser_changed()`
  - 第974-1030行：`_on_refresh_cookie_clicked()`

## 参考文档

- [Qt Threading Basics](https://doc.qt.io/qt-6/thread-basics.html)
- [Signals & Slots](https://doc.qt.io/qt-6/signalsandslots.html)
- [QThread Documentation](https://doc.qt.io/qt-6/qthread.html)
