"""
日志信号处理器

将 loguru 日志通过 Qt Signal 转发，实现实时日志显示
"""
from __future__ import annotations

from loguru import logger
from PySide6.QtCore import QObject, Signal


class LogSignalHandler(QObject):
    """将 loguru 日志转发为 Qt Signal
    
    使用方式:
        handler = LogSignalHandler()
        handler.log_received.connect(your_slot)
        handler.install()
        
        # 不再需要时
        handler.uninstall()
    """
    
    # 信号: (时间, 级别, 模块, 消息)
    log_received = Signal(str, str, str, str)
    
    _instance: LogSignalHandler | None = None
    
    def __new__(cls) -> LogSignalHandler:
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._sink_id: int | None = None
        self._initialized = True
    
    def install(self, level: str = "DEBUG") -> None:
        """安装到 loguru
        
        Args:
            level: 最低日志级别，默认 DEBUG
        """
        if self._sink_id is not None:
            return  # 已安装
        
        self._sink_id = logger.add(
            self._emit_log,
            level=level,
            format="{message}",  # 我们自己解析 record
            enqueue=True,  # 异步
        )
    
    def uninstall(self) -> None:
        """从 loguru 移除"""
        if self._sink_id is not None:
            try:
                logger.remove(self._sink_id)
            except ValueError:
                pass  # sink 已被移除
            self._sink_id = None
    
    def _emit_log(self, message) -> None:
        """loguru sink 回调"""
        record = message.record
        
        time_str = record["time"].strftime("%H:%M:%S")
        level = record["level"].name
        module = record.get("name", "") or ""
        msg = record["message"]
        
        self.log_received.emit(time_str, level, module, msg)
    
    @property
    def is_installed(self) -> bool:
        """是否已安装"""
        return self._sink_id is not None


# 全局单例
log_signal_handler = LogSignalHandler()
