from __future__ import annotations

from typing import Any
import os
import re
import subprocess
from collections import deque
import threading

from PySide6.QtCore import QThread, Signal

from .youtube_service import YoutubeServiceOptions, youtube_service
from .yt_dlp_cli import YtDlpCancelled, prepare_yt_dlp_env, resolve_yt_dlp_exe, ydl_opts_to_cli_args
from ..utils.paths import locate_runtime_tool
from ..utils.logger import logger
from ..utils.translator import translate_error


class DownloadCancelled(Exception):
    pass


class InfoExtractWorker(QThread):
    """解析工人：后台获取视频元数据 (JSON)，不下载"""

    finished = Signal(dict)
    error = Signal(dict)

    def __init__(
        self,
        url: str,
        options: YoutubeServiceOptions | None = None,
        playlist_flat: bool = False,
    ):
        super().__init__()
        self.url = url
        self.options = options
        self.playlist_flat = playlist_flat
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        try:
            if self.playlist_flat:
                info = youtube_service.extract_playlist_flat(self.url, self.options, cancel_event=self._cancel_event)
            else:
                info = youtube_service.extract_info_for_dialog_sync(self.url, self.options, cancel_event=self._cancel_event)
            if self._cancel_event.is_set():
                return
            self.finished.emit(info)
        except YtDlpCancelled:
            # Dialog closed; treat as silent cancellation.
            return
        except Exception as exc:
            logger.exception("解析失败: {}", self.url)
            self.error.emit(translate_error(exc))


class EntryDetailWorker(QThread):
    """播放列表条目深解析：获取 formats / 最高质量等信息"""

    finished = Signal(int, dict)
    error = Signal(int, str)

    def __init__(self, row: int, url: str, options: YoutubeServiceOptions | None = None):
        super().__init__()
        self.row = row
        self.url = url
        self.options = options
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        try:
            info = youtube_service.extract_video_info(self.url, self.options, cancel_event=self._cancel_event)
            if self._cancel_event.is_set():
                return
            self.finished.emit(self.row, info)
        except YtDlpCancelled:
            return
        except Exception as exc:
            self.error.emit(self.row, str(exc))


class DownloadWorker(QThread):
    """下载工人：执行实际下载任务

    支持进度回调与取消（Phase 3 先实现取消；暂停在后续阶段做）。
    """

    progress = Signal(dict)  # 发送 yt-dlp 的进度字典
    completed = Signal()  # 下载完成（避免与 QThread.finished 冲突）
    cancelled = Signal()  # 用户暂停/取消
    error = Signal(dict)  # 发生错误（结构化）
    status_msg = Signal(str)  # 状态文本 (正在合并/正在转换...)
    output_path_ready = Signal(str)  # 最终输出文件路径（尽力解析）

    def __init__(self, url: str, opts: dict[str, Any]):
        super().__init__()
        self.url = url
        self.opts = dict(opts)
        self.is_cancelled = False
        self.is_running = False
        self._proc: subprocess.Popen[str] | None = None
        # Best-effort output location for UI “open folder” action.
        self.output_path: str | None = None
        self.download_dir: str | None = None
        # Best-effort: all destination paths seen in yt-dlp output.
        # This is important for paused/cancelled tasks where final output_path may be unknown.
        self.dest_paths: set[str] = set()

    _re_progress_full = re.compile(
        r"^\[download\]\s+(?P<pct>\d+(?:\.\d+)?)%\s+of\s+~?(?P<total>[\d\.]+)(?P<tunit>[KMGTPE]i?B)\s+at\s+(?P<speed>[\d\.]+)(?P<sunit>[KMGTPE]i?B)/s\s+ETA\s+(?P<eta>\d{1,2}:\d{2}(?::\d{2})?)",
        re.IGNORECASE,
    )
    _re_progress_partial = re.compile(
        r"^\[download\]\s+(?P<done>[\d\.]+)(?P<unit>[KMGTPE]i?B)\s+at\s+(?P<speed>[\d\.]+)(?P<sunit>[KMGTPE]i?B)/s\s+ETA\s+(?P<eta>\d{1,2}:\d{2}(?::\d{2})?)",
        re.IGNORECASE,
    )

    @staticmethod
    def _size_to_bytes(value: str, unit: str) -> int:
        try:
            v = float(value)
        except Exception:
            return 0
        u = (unit or "").strip()
        scale = {
            "B": 1,
            "KIB": 1024,
            "MIB": 1024**2,
            "GIB": 1024**3,
            "TIB": 1024**4,
            "PIB": 1024**5,
            "EIB": 1024**6,
            # yt-dlp sometimes uses KB/MB (decimal) in some contexts
            "KB": 1000,
            "MB": 1000**2,
            "GB": 1000**3,
            "TB": 1000**4,
        }.get(u.upper(), 0)
        if scale <= 0:
            return 0
        return int(v * scale)

    @staticmethod
    def _parse_eta(eta: str) -> int | None:
        s = (eta or "").strip()
        if not s:
            return None
        try:
            parts = [int(p) for p in s.split(":")]
        except Exception:
            return None
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return None

    def run(self) -> None:
        self.is_running = True
        self.is_cancelled = False
        try:
            # 合并 YoutubeService 的基础反封锁/网络配置
            base_opts = youtube_service.build_ydl_options()
            merged = dict(base_opts)
            merged.update(self.opts)

            # Derive download directory from outtmpl (best effort).
            try:
                paths = merged.get("paths")
                outtmpl = merged.get("outtmpl")
                
                if isinstance(paths, dict) and paths.get("home"):
                    self.download_dir = os.path.abspath(str(paths.get("home")))
                elif isinstance(outtmpl, str) and outtmpl.strip():
                    parent = os.path.dirname(outtmpl)
                    if parent:
                        self.download_dir = os.path.abspath(parent)
                    else:
                        self.download_dir = os.path.abspath(os.getcwd())
                else:
                    self.download_dir = os.path.abspath(os.getcwd())
            except Exception:
                self.download_dir = os.path.abspath(os.getcwd())

            # Strip internal meta options (never pass to yt-dlp)
            for k in list(merged.keys()):
                if isinstance(k, str) and k.startswith("__fluentytdl_"):
                    merged.pop(k, None)

            try:
                yt_dlp_exe = locate_runtime_tool(
                    "yt-dlp.exe",
                    "yt-dlp/yt-dlp.exe",
                    "yt_dlp/yt-dlp.exe",
                )
            except FileNotFoundError:
                raise FileNotFoundError(
                    "未找到 yt-dlp.exe。请在设置页指定路径，或将 yt-dlp.exe 放入 _internal/yt-dlp/，或加入 PATH。"
                )

            self._download_via_exe(str(yt_dlp_exe), merged)

            # === 关键修复 ===
            # 只有在没有被用户暂停/取消的情况下，才算“真正完成”
            if not self.is_cancelled:
                self.completed.emit()
        except DownloadCancelled:
            self.status_msg.emit("任务已暂停")
            self.cancelled.emit()
        except Exception as exc:
            logger.exception("下载过程发生异常: {}", self.url)
            self.error.emit(translate_error(exc))
        finally:
            self.is_running = False

    def _download_via_exe(self, exe: str, merged_opts: dict[str, Any]) -> None:
        progress_prefix = "FLUENTYTDL|"

        # Base flags: quiet but keep progress, one line per update.
        cmd: list[str] = [
            exe,
            "--no-warnings",
            "--no-color",
            "--newline",
            "--progress",
            "-q",
            # Stable machine-readable progress line.
            "--progress-template",
            (
                "download:"
                + progress_prefix
                + "download|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.speed)s|%(progress.eta)s|%(info.vcodec)s|%(info.acodec)s|%(info.ext)s|%(progress.filename)s"
            ),
            "--progress-template",
            (
                "postprocess:"
                + progress_prefix
                + "postprocess|%(progress.status)s|%(progress.postprocessor)s"
            ),
        ]

        cmd += ydl_opts_to_cli_args(merged_opts)
        cmd.append(self.url)

        env = prepare_yt_dlp_env()

        popen_kwargs: dict[str, Any] = {}
        if os.name == "nt":
            try:
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
                si.wShowWindow = 0
                popen_kwargs["startupinfo"] = si
            except Exception:
                pass

        # Merge stdout/stderr; yt-dlp progress is typically on stderr.
        # FORCE UTF-8: yt-dlp writes utf-8 by default, we must decode it as utf-8.
        # We also set PYTHONIOENCODING to utf-8 in env to be sure.
        env["PYTHONIOENCODING"] = "utf-8"
        
        # Use binary mode to handle potential encoding issues manually
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False, # Binary mode
            # encoding="utf-8", # Removed
            # errors="replace", # Removed
            env=env,
            cwd=os.getcwd(),
            bufsize=1,
            **popen_kwargs,
        )

        tail: deque[str] = deque(maxlen=120)

        re_dest = re.compile(r"^\[download\]\s+Destination:\s+(?P<path>.+)$")
        re_merge = re.compile(r'^\[Merger\]\s+Merging formats into\s+"(?P<path>.+)"$')

        assert self._proc.stdout is not None
        for raw_bytes in self._proc.stdout:
            # Robust decoding: try UTF-8, then GBK (for Windows CN), then fallback
            try:
                line = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    line = raw_bytes.decode("gbk")
                except UnicodeDecodeError:
                    line = raw_bytes.decode("utf-8", errors="replace")

            line = line.rstrip("\r\n")
            if not line:
                continue

            tail.append(line)

            if self.is_cancelled:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
                break

            # Status hooks for merge/postprocess stages
            if line.startswith("[Merger]") or line.startswith("[ExtractAudio]") or "Merging formats" in line:
                self.status_msg.emit(line)

                # Capture final merged output path.
                m2 = re_merge.match(line)
                if m2:
                    p = (m2.group("path") or "").strip()
                    if p:
                        try:
                            p_abs = os.path.abspath(p)
                        except Exception:
                            p_abs = p
                        self.output_path = p_abs
                        try:
                            self.output_path_ready.emit(p_abs)
                        except Exception:
                            pass
                continue

            # Capture destination path (may be temp or final for muxed).
            m1 = re_dest.match(line)
            if m1:
                p = (m1.group("path") or "").strip()
                if p:
                    try:
                        p_abs = os.path.abspath(p)
                    except Exception:
                        p_abs = p

                    # Track all destinations; yt-dlp may output multiple destinations for
                    # split video/audio streams (e.g. *.f137.mp4 and *.f140.m4a).
                    try:
                        self.dest_paths.add(p_abs)
                    except Exception:
                        pass

                    # Do not overwrite a final merged path once we have it.
                    if not self.output_path:
                        self.output_path = p_abs
                        try:
                            self.output_path_ready.emit(p_abs)
                        except Exception:
                            pass
                continue

            # Structured progress-template lines
            if line.startswith(progress_prefix):
                # FLUENTYTDL|download|downloaded|total|speed|eta|vcodec|acodec|ext
                # FLUENTYTDL|postprocess|status|postprocessor
                parts = line.split("|")
                if len(parts) >= 3 and parts[1] == "download":
                    downloaded_s = parts[2] if len(parts) > 2 else ""
                    total_s = parts[3] if len(parts) > 3 else ""
                    speed_s = parts[4] if len(parts) > 4 else ""
                    eta_s = parts[5] if len(parts) > 5 else ""
                    vcodec = parts[6] if len(parts) > 6 else ""
                    acodec = parts[7] if len(parts) > 7 else ""
                    ext = parts[8] if len(parts) > 8 else ""
                    filename = parts[9] if len(parts) > 9 else ""

                    # Capture filename for cache deletion (and UI "open folder")
                    if filename and filename != "NA":
                        try:
                            p_abs = os.path.abspath(filename)
                            self.dest_paths.add(p_abs)
                            if not self.output_path:
                                self.output_path = p_abs
                                try:
                                    self.output_path_ready.emit(p_abs)
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    try:
                        downloaded = int(float(downloaded_s)) if downloaded_s and downloaded_s != "NA" else 0
                    except Exception:
                        downloaded = 0
                    try:
                        total = int(float(total_s)) if total_s and total_s != "NA" else 0
                    except Exception:
                        total = 0
                    try:
                        speed = int(float(speed_s)) if speed_s and speed_s != "NA" else 0
                    except Exception:
                        speed = 0
                    eta: int | None = None
                    if eta_s and eta_s != "NA":
                        s_eta = str(eta_s).strip()
                        if ":" in s_eta:
                            eta = self._parse_eta(s_eta)
                        else:
                            # yt-dlp progress.eta is usually seconds.
                            try:
                                eta = int(float(s_eta))
                            except Exception:
                                eta = None

                    self.progress.emit(
                        {
                            "status": "downloading",
                            "downloaded_bytes": downloaded,
                            "total_bytes": total or None,
                            "speed": speed or None,
                            "eta": eta,
                            "filename": None,
                            "info_dict": {"vcodec": vcodec, "acodec": acodec},
                        }
                    )
                    continue

                if len(parts) >= 3 and parts[1] == "postprocess":
                    status = parts[2] if len(parts) > 2 else ""
                    pp = parts[3] if len(parts) > 3 else ""
                    msg = f"后处理: {pp} ({status})" if pp and status else ("后处理中..." if status else "后处理中...")
                    self.status_msg.emit(msg)
                    continue

            # Download progress lines
            if line.startswith("[download]"):
                m = self._re_progress_full.match(line)
                if m:
                    pct = float(m.group("pct"))
                    total = self._size_to_bytes(m.group("total"), m.group("tunit"))
                    speed = self._size_to_bytes(m.group("speed"), m.group("sunit"))
                    eta = self._parse_eta(m.group("eta"))
                    downloaded = int(total * pct / 100.0) if total > 0 else 0

                    self.progress.emit(
                        {
                            "status": "downloading",
                            "downloaded_bytes": downloaded,
                            "total_bytes": total or None,
                            "speed": speed or None,
                            "eta": eta,
                            "filename": None,
                            "info_dict": {},
                        }
                    )
                    continue

                m2 = self._re_progress_partial.match(line)
                if m2:
                    downloaded = self._size_to_bytes(m2.group("done"), m2.group("unit"))
                    speed = self._size_to_bytes(m2.group("speed"), m2.group("sunit"))
                    eta = self._parse_eta(m2.group("eta"))
                    self.progress.emit(
                        {
                            "status": "downloading",
                            "downloaded_bytes": downloaded,
                            "total_bytes": None,
                            "speed": speed or None,
                            "eta": eta,
                            "filename": None,
                            "info_dict": {},
                        }
                    )
                    continue

                # Fallback: surface the raw line
                self.status_msg.emit(line)
                continue

            # Other informative lines
            if line.startswith("["):
                self.status_msg.emit(line)

        rc = None
        try:
            rc = self._proc.wait(timeout=2)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
            rc = self._proc.returncode
        finally:
            self._proc = None

        if self.is_cancelled:
            raise DownloadCancelled()

        if rc and rc != 0:
            raise RuntimeError("yt-dlp.exe 退出异常:\n" + "\n".join(tail))

    def stop(self) -> None:
        """外部调用此方法暂停/取消下载"""
        self.is_cancelled = True
        proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
