from __future__ import annotations

import os
import sys
import tempfile

from loguru import logger

# 1. 确定日志存储路径
# 优先使用项目根目录下的 logs 文件夹
# 在开发环境中，根目录是 src 的上级；在打包后，我们需要一个可写路径
if getattr(sys, "frozen", False):
    # 【打包后】使用用户文档目录，因为 Program Files 通常不可写
    # C:/Users/Name/Documents/FluentYTDL/logs
    LOG_DIR = os.path.join(os.path.expanduser("~"), "Documents", "FluentYTDL", "logs")
else:
    # 【开发环境】使用项目根目录下的 logs
    # 假设当前文件在 src/fluentytdl/utils/logger.py -> 上3级是根目录
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    LOG_DIR = os.path.join(BASE_DIR, "logs")

if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR)
    except Exception:
        # 极端情况：无权限创建目录，降级为临时目录
        LOG_DIR = os.path.join(tempfile.gettempdir(), "FluentYTDL_logs")
        os.makedirs(LOG_DIR, exist_ok=True)


# 2. 重置 logger 配置
logger.remove()


# 3. 配置控制台输出 (开发调试用)
# level="INFO" 表示只显示 INFO, WARNING, ERROR, CRITICAL
_console_sink = getattr(sys, "__stderr__", None) or sys.stderr
if _console_sink is not None:
    logger.add(
        _console_sink,
        level="INFO",
        format=(
            "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        ),
    )


# 4. 配置文件输出 (排查问题用)
# level="DEBUG" 记录所有细节
# rotation="00:00" 每天午夜轮转新文件
# retention="7 days" 只保留最近7天的日志
# compression="zip" 旧日志自动压缩
logger.add(
    os.path.join(LOG_DIR, "app_{time:YYYY-MM-DD}.log"),
    level="DEBUG",
    rotation="00:00",
    retention="7 days",
    compression="zip",
    encoding="utf-8",
    enqueue=True,  # 异步写入，不阻塞主线程
    backtrace=True,  # 记录异常堆栈
    diagnose=True,  # 诊断模式
)


# 5. 全局异常捕获钩子
# 这样即使程序崩溃（Crash），也能在日志里看到原因
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical("Uncaught exception")


sys.excepthook = handle_exception


# 导出 logger 供其他模块使用
def get_logger(*_args, **_kwargs):
    return logger
