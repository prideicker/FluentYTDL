import sys
import shutil
from pathlib import Path
from typing import Optional


class PathManager:
    """基于 EXE 物理路径的简洁路径管理器。

    核心逻辑：在 onefile 打包后以 `sys.executable` 的父目录为锚点，优先从该目录下的 `bin` 查找工具，
    否则回退到系统 PATH。
    """

    def __init__(self) -> None:
        self._resolve_root()
        self.bin_dir = self.root_dir / "bin"

    def _resolve_root(self) -> None:
        """Resolve the absolute root directory anchor.

        在 onefile 情况下，必须使用 `sys.executable` 的父目录作为锚点，绝对不能使用 `_MEIPASS`。
        在开发模式下，回溯到项目根（假设本文件位于 src/fluentytdl/utils/）。
        """
        if getattr(sys, "frozen", False):
            # 打包后：锁定到 EXE 所在的真实文件夹
            self.root_dir = Path(sys.executable).resolve().parent
            self.is_frozen = True
        else:
            # 开发时：项目根
            self.root_dir = Path(__file__).resolve().parents[3]
            self.is_frozen = False

    def get_tool_path(self, tool_name: str) -> Optional[Path]:
        """双重检测策略：

        1) 先查 EXE 同级的 `bin`（Full 模式）。
        2) 否则查系统 PATH（Shell 模式）。
        返回 Path 或 None。
        """
        # 策略 A: 本地 bin
        local_path = self.bin_dir / tool_name
        try:
            if local_path.exists():
                p = local_path.resolve()
                # 便于打包后调试，保留一条可观测输出
                print(f"[PathManager] Found local tool: {p}")
                return p
        except Exception:
            pass

        # 策略 B: 系统 PATH
        try:
            system_path = shutil.which(tool_name)
            if system_path:
                print(f"[PathManager] Found system tool: {system_path}")
                return Path(system_path)
        except Exception:
            pass

        # 调试信息：打印查询位置
        try:
            print(f"[PathManager] NOT FOUND. Looked in: {self.bin_dir}")
        except Exception:
            pass
        return None

