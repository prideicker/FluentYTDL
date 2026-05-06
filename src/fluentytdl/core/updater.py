"""
FluentYTDL 独立更新器

Telegram 风格的独立更新器，由主程序在下载完 app-core 更新后启动。
主程序退出后，updater 等待进程释放，替换文件，然后重启主程序。

用法:
    python updater.py --pid <PID> --archive <7z路径> --dest <应用目录> --exe <exe名>

打包:
    PyInstaller 打包为 updater.exe，随应用一起分发。
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

# Windows API 常量
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
INFINITE = 0xFFFFFFFF
MOVEFILE_REPLACE_EXISTING = 0x1
MOVEFILE_DELAY_UNTIL_REBOOT = 0x4

# ─── 文件日志 ─────────────────────────────────────────────

_logger: logging.Logger | None = None


def _init_log(dest_dir: Path) -> None:
    """初始化文件日志（console=False 时 stderr 不可见）。"""
    global _logger
    log_dir = dest_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _logger = logging.getLogger("updater")
    _logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(
        log_dir / "updater.log", encoding="utf-8", mode="w"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [updater] %(message)s", datefmt="%H:%M:%S")
    )
    _logger.addHandler(handler)


def log(msg: str) -> None:
    """日志输出到文件 + stderr（双通道，确保可追溯）。"""
    if _logger:
        _logger.info(msg)
    try:
        print(f"[updater] {msg}", file=sys.stderr, flush=True)
    except Exception:
        pass


def wait_for_process(pid: int, timeout: int = 30) -> bool:
    """等待指定 PID 的进程退出。

    Windows: 使用 ctypes 调用 OpenProcess + WaitForSingleObject。
    其他平台: 轮询 /proc 或 psutil。

    Returns:
        True 如果进程已退出，False 如果超时。
    """
    if sys.platform == "win32":
        return _wait_windows(pid, timeout)
    return _wait_polling(pid, timeout)


def _wait_windows(pid: int, timeout: int) -> bool:
    """Windows: 使用 WaitForSingleObject 等待进程退出。"""
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    # PROCESS_SYNCHRONIZE = 0x00100000
    handle = kernel32.OpenProcess(0x00100000, False, pid)
    if not handle:
        # 进程不存在，视为已退出
        log(f"进程 {pid} 不存在或已退出")
        return True

    try:
        timeout_ms = timeout * 1000 if timeout > 0 else INFINITE
        result = kernel32.WaitForSingleObject(handle, timeout_ms)
        if result == WAIT_OBJECT_0:
            log(f"进程 {pid} 已退出")
            return True
        elif result == WAIT_TIMEOUT:
            log(f"等待进程 {pid} 超时 ({timeout}s)")
            return False
        else:
            log(f"WaitForSingleObject 返回异常值: {result}")
            return False
    finally:
        kernel32.CloseHandle(handle)


def _wait_polling(pid: int, timeout: int) -> bool:
    """跨平台回退: 轮询检查进程是否存在。"""
    deadline = time.time() + timeout if timeout > 0 else float("inf")
    while time.time() < deadline:
        try:
            os.kill(pid, 0)  # 检查进程是否存在
            time.sleep(0.5)
        except OSError:
            log(f"进程 {pid} 已退出")
            return True
    log(f"等待进程 {pid} 超时 ({timeout}s)")
    return False


def extract_archive(archive_path: Path, dest_dir: Path) -> None:
    """解压归档文件到目标目录。

    支持 .7z（通过 py7zr 或系统 7z）和 .zip。
    """
    if archive_path.suffix == ".7z":
        _extract_7z(archive_path, dest_dir)
    elif archive_path.suffix == ".zip":
        _extract_zip(archive_path, dest_dir)
    else:
        raise ValueError(f"不支持的归档格式: {archive_path.suffix}")


def _extract_7z(archive_path: Path, dest_dir: Path) -> None:
    """解压 7z 文件。优先使用 py7zr，回退到系统 7z CLI。"""
    # 尝试 py7zr
    try:
        import py7zr

        with py7zr.SevenZipFile(archive_path, "r") as archive:
            archive.extractall(dest_dir)
        log("通过 py7zr 解压完成")
        return
    except ImportError:
        log("py7zr 未安装，尝试系统 7z")
    except Exception as e:
        log(f"py7zr 解压失败: {e}，尝试系统 7z")

    # 回退到系统 7z
    sevenzip = shutil.which("7z") or shutil.which("7za")
    if sevenzip:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.run(
            [sevenzip, "x", str(archive_path), f"-o{dest_dir}", "-aoa", "-y"],
            check=True,
            capture_output=True,
            **kwargs,
        )
        log("通过系统 7z 解压完成")
        return

    raise RuntimeError("无法解压 7z 文件: py7zr 未安装且系统中未找到 7z")


def _extract_zip(archive_path: Path, dest_dir: Path) -> None:
    """解压 zip 文件。"""
    with zipfile.ZipFile(archive_path) as zf:
        zf.extractall(dest_dir)
    log("通过 zipfile 解压完成")


def self_delete(exe_path: Path) -> None:
    """延迟自删除。通过 cmd 命令在短暂延迟后删除自身。"""
    if sys.platform != "win32":
        try:
            exe_path.unlink(missing_ok=True)
        except Exception:
            pass
        return

    # Windows: 用 cmd /c 延迟删除（ping 是一种可靠的 sleep 替代）
    cmd = f'ping -n 2 127.0.0.1 >nul & del /f /q "{exe_path}"'
    subprocess.Popen(
        ["cmd", "/c", cmd],
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def request_admin_if_needed(app_dir: Path) -> bool:
    """检测是否需要管理员权限（Program Files 目录），如需要则提权重启。

    Returns:
        True 如果已提权并启动了新的 updater 进程（当前进程应退出）。
        False 如果不需要提权或提权失败。
    """
    if sys.platform != "win32":
        return False

    # 检测是否在 Program Files 目录下
    app_dir_str = str(app_dir).lower()
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files").lower()
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)").lower()
    local_app_data = os.environ.get("LOCALAPPDATA", "").lower()

    # 如果在用户目录下（便携版），不需要提权
    if local_app_data and app_dir_str.startswith(local_app_data):
        return False

    # 如果在 Program Files 下，需要提权
    if app_dir_str.startswith(program_files) or app_dir_str.startswith(program_files_x86):
        log("检测到 Program Files 目录，尝试请求管理员权限...")
        return _elevate_self()

    return False


def _elevate_self() -> bool:
    """使用 ShellExecuteW 的 runas verb 提权重启自身。"""
    try:
        # 重新构建命令行参数
        args = " ".join(sys.argv[1:])
        exe = sys.executable
        if getattr(sys, "frozen", False):
            exe = sys.executable
        else:
            exe = f'"{exe}" "{__file__}"'

        shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
        ret = shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable if getattr(sys, "frozen", False) else sys.executable,
            f'"{__file__}" {args}' if not getattr(sys, "frozen", False) else args,
            None,
            0,  # SW_HIDE — 不显示窗口
        )
        if ret > 32:
            log("已启动管理员权限进程，当前进程退出")
            return True
        else:
            log(f"ShellExecuteW 返回 {ret}，提权失败")
            return False
    except Exception as e:
        log(f"提权失败: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="FluentYTDL 独立更新器")
    parser.add_argument("--pid", type=int, required=True, help="主进程 PID")
    parser.add_argument("--archive", required=True, help="更新归档文件路径 (7z/zip)")
    parser.add_argument("--dest", required=True, help="应用安装目录")
    parser.add_argument("--exe", default="FluentYTDL.exe", help="主程序可执行文件名")
    parser.add_argument("--timeout", type=int, default=30, help="等待进程退出的超时秒数")
    args = parser.parse_args()

    archive_path = Path(args.archive)
    dest_dir = Path(args.dest)
    exe_name = args.exe
    exe_path = dest_dir / exe_name

    # 初始化文件日志（console=False 后 stderr 不可见）
    _init_log(dest_dir)

    log("=" * 50)
    log("FluentYTDL 更新器启动")
    log(f"  PID: {args.pid}")
    log(f"  归档: {archive_path}")
    log(f"  目标: {dest_dir}")
    log(f"  可执行文件: {exe_name}")
    log("=" * 50)

    # 验证归档文件存在
    if not archive_path.exists():
        log(f"错误: 归档文件不存在: {archive_path}")
        return 1

    # 验证目标目录存在
    if not dest_dir.exists():
        log(f"错误: 目标目录不存在: {dest_dir}")
        return 1

    # 检查是否需要管理员权限（Program Files 场景）
    if request_admin_if_needed(dest_dir):
        # 已启动提权进程，当前进程退出
        return 0

    # 等待主进程退出
    log("等待主进程退出...")
    if not wait_for_process(args.pid, args.timeout):
        log("警告: 等待超时，尝试继续替换...")

    # 额外等待一小段时间，确保文件句柄释放
    time.sleep(0.5)

    # 清理旧备份
    internal_dir = dest_dir / "_internal"
    internal_old = dest_dir / "_internal_old"
    exe_old = exe_path.with_suffix(".exe.old")

    if internal_old.exists():
        log("清理旧备份目录 _internal_old/ ...")
        shutil.rmtree(internal_old, ignore_errors=True)

    # 重命名旧目录
    if internal_dir.exists():
        log("重命名 _internal/ → _internal_old/ ...")
        try:
            internal_dir.rename(internal_old)
        except OSError as e:
            log(f"重命名 _internal 失败: {e}")
            return 1

    # 重命名旧 exe
    if exe_path.exists():
        log(f"重命名 {exe_name} → {exe_name}.old ...")
        try:
            if exe_old.exists():
                exe_old.unlink(missing_ok=True)
            exe_path.rename(exe_old)
        except OSError as e:
            log(f"重命名 {exe_name} 失败: {e}")
            # 回滚 _internal 重命名
            if internal_old.exists() and not internal_dir.exists():
                internal_old.rename(internal_dir)
            return 1

    # 解压新版本
    log("解压新版本...")
    try:
        extract_archive(archive_path, dest_dir)
    except Exception as e:
        log(f"解压失败: {e}")
        # 回滚
        if internal_old.exists() and not internal_dir.exists():
            internal_old.rename(internal_dir)
        if exe_old.exists() and not exe_path.exists():
            exe_old.rename(exe_path)
        return 1

    # 优先启动新版本（不被清理阻塞）
    log(f"启动新版本: {exe_path}")
    if not exe_path.exists():
        log(f"错误: 新版本 {exe_path} 不存在")
        return 1

    if sys.platform == "win32":
        # 使用 ShellExecuteW 启动 GUI 应用（等同于双击 exe，最可靠）
        # subprocess.Popen + DETACHED_PROCESS 从 windowed 进程启动 GUI 不可靠
        ret = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[union-attr]
            None, "open", str(exe_path), None, str(dest_dir), 1,  # SW_SHOWNORMAL
        )
        if ret <= 32:
            log(f"错误: ShellExecuteW 返回 {ret}，启动新版本失败")
            return 1
        log(f"✓ ShellExecuteW 成功 (ret={ret})")
    else:
        subprocess.Popen([str(exe_path)], cwd=str(dest_dir))

    # 等待新版本进程初始化后再清理旧文件（best-effort）
    # 即使清理失败，主程序启动时也会兜底清理
    log("等待 2 秒后清理旧文件...")
    time.sleep(2)

    log("清理旧文件...")
    if internal_old.exists():
        try:
            shutil.rmtree(internal_old, ignore_errors=True)
            log("✓ _internal_old/ 已删除")
        except Exception as e:
            log(f"⚠ _internal_old/ 清理失败（主程序启动时会重试）: {e}")
    if exe_old.exists():
        try:
            exe_old.unlink(missing_ok=True)
            log("✓ .exe.old 已删除")
        except OSError as e:
            log(f"⚠ .exe.old 清理失败（主程序启动时会重试）: {e}")

    # 删除归档文件
    try:
        archive_path.unlink(missing_ok=True)
        log("✓ 归档文件已删除")
    except OSError:
        pass

    # 自删除
    log("更新完成，自删除...")
    if getattr(sys, "frozen", False):
        self_delete(Path(sys.executable))
    else:
        self_delete(Path(__file__).resolve())

    log("更新器退出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
