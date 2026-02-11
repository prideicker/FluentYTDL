from __future__ import annotations

from typing import Any
import os
import re
import subprocess
from collections import deque
import threading

from PySide6.QtCore import QThread, Signal

from ..youtube.youtube_service import YoutubeServiceOptions, youtube_service
from ..youtube.yt_dlp_cli import YtDlpCancelled, prepare_yt_dlp_env, ydl_opts_to_cli_args
from ..core.config_manager import config_manager
from ..processing.thumbnail_embed import can_embed_thumbnail, get_unsupported_formats_warning
from ..processing.thumbnail_embedder import thumbnail_embedder
from ..utils.paths import locate_runtime_tool
from ..utils.logger import logger
from ..utils.translator import translate_error
from ..utils.spatialmedia import metadata_utils
from ..core.hardware_manager import hardware_manager, RiskLevel


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


class VRInfoExtractWorker(QThread):
    """VR 解析工人：使用 android_vr 客户端获取 VR 视频元数据"""

    finished = Signal(dict)
    error = Signal(dict)

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        try:
            info = youtube_service.extract_vr_info_sync(self.url, cancel_event=self._cancel_event)
            if self._cancel_event.is_set():
                return
            self.finished.emit(info)
        except YtDlpCancelled:
            return
        except Exception as exc:
            logger.exception("VR 解析失败: {}", self.url)
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
    cookie_error_detected = Signal(str)  # Cookie 错误检测（触发修复流程）
    thumbnail_embed_warning = Signal(str)  # 封面嵌入警告（格式不支持时）

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
        self.dest_paths: set[str] = set()        # 格式选择状态追踪（防止格式自动降级到音频）
        self._original_format: str | None = None
        self._ssl_error_count = 0
        self._format_warning_shown = False  # 防止重复警告
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
            
            # 保存原始格式选择（用于错误恢复）
            self._original_format = merged.get("format")
            if self._original_format:
                logger.info("原始格式选择已保存: {}", self._original_format)
            
            # DEBUG: 记录音频处理相关选项
            logger.debug("DownloadWorker options - postprocessors: {}", merged.get("postprocessors"))
            logger.debug("DownloadWorker options - addmetadata: {}", merged.get("addmetadata"))
            logger.debug("DownloadWorker options - writethumbnail: {}", merged.get("writethumbnail"))

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

            # === 埋点：记录字幕相关选项（合并 base_opts 后）===
            logger.info("[SubEmbed] === 字幕选项追踪（合并后） ===")
            logger.info("[SubEmbed] embedsubtitles  = {}", merged.get("embedsubtitles"))
            logger.info("[SubEmbed] writesubtitles   = {}", merged.get("writesubtitles"))
            logger.info("[SubEmbed] writeautomaticsub= {}", merged.get("writeautomaticsub"))
            logger.info("[SubEmbed] subtitleslangs   = {}", merged.get("subtitleslangs"))
            logger.info("[SubEmbed] convertsubtitles = {}", merged.get("convertsubtitles"))
            logger.info("[SubEmbed] merge_output_fmt = {}", merged.get("merge_output_format"))
            logger.info("[SubEmbed] format           = {}", merged.get("format"))

            logger.info("[SubEmbed] format           = {}", merged.get("format"))

            # [VR Fix] 将内部 VR 标记转换为标准的 extractor_args
            if merged.get("__fluentytdl_use_android_vr"):
                logger.info("[VR] 正在配置 android_vr 客户端参数...")
                ext_args = merged.get("extractor_args")
                if not isinstance(ext_args, dict):
                    ext_args = {}
                
                # VR 模式下，移除 POT Provider 相关的 extractor_args（不兼容）
                if "youtubepot-bgutilhttp" in ext_args:
                    logger.warning("[VR] 移除 POT Provider 配置（android_vr 客户端不兼容 POT）")
                    ext_args.pop("youtubepot-bgutilhttp", None)
                
                # VR 模式下，移除 cookies（android_vr 客户端需要纯净环境）
                if merged.get("cookiefile"):
                    logger.warning("[VR] 移除 Cookie 配置（android_vr 客户端使用模拟环境）")
                    merged.pop("cookiefile", None)
                
                # 确保 youtube 键存在
                yt_args = ext_args.get("youtube")
                if not isinstance(yt_args, dict):
                    yt_args = {}
                
                # 设置 player_client
                yt_args["player_client"] = "android_vr"
                
                ext_args["youtube"] = yt_args
                merged["extractor_args"] = ext_args
                
                # 调试日志：输出最终的 extractor_args
                logger.info("[VR] extractor_args 已设置: {}", merged.get("extractor_args"))

            # Strip internal meta options (never pass to yt-dlp)
            for k in list(merged.keys()):
                if isinstance(k, str) and k.startswith("__fluentytdl_"):
                    merged.pop(k, None)

            # === 字幕嵌入安全网 ===
            # 当 embedsubtitles 为 True 时，确保容器格式支持字幕嵌入
            # MP4/MKV 都支持字幕嵌入，只有 WebM 不支持 SRT/ASS
            if merged.get("embedsubtitles"):
                fmt = (merged.get("merge_output_format") or "").lower()
                if fmt == "webm":
                    merged["merge_output_format"] = "mkv"
                    logger.info("[SubEmbed] WebM → MKV（WebM 不支持字幕嵌入）")
                elif not fmt:
                    merged["merge_output_format"] = "mkv"
                    logger.info("[SubEmbed] 未指定容器 → MKV（确保字幕嵌入兼容）")
                else:
                    logger.info("[SubEmbed] 容器 {} 支持字幕嵌入，保持不变", fmt)
            else:
                logger.warning("[SubEmbed] ⚠️ embedsubtitles=False → yt-dlp 不会嵌入字幕！")

            # === Phase 2: 断点续传支持 ===
            from ..core.config_manager import config_manager as cfg_mgr
            if cfg_mgr.get("enable_resume", True):
                merged["continuedl"] = True  # 继续下载部分文件

            # ========== VR 格式专用客户端 ==========
            # VR 模式下所有格式来自 android_vr 客户端，无需格式兼容性检查
            if merged.pop("__fluentytdl_use_android_vr", False):
                logger.info("🥽 VR 模式: 使用 android_vr 客户端下载")
                # 清理不需要的内部标记
                merged.pop("__android_vr_format_ids", None)
                # 设置 extractor_args，覆盖默认客户端
                merged["extractor_args"] = {
                    "youtube": {
                        "player_client": ["android_vr"],
                    }
                }
                # android_vr 不支持 cookies，需要禁用
                merged.pop("cookiefile", None)
                merged.pop("cookiesfrombrowser", None)
                logger.warning("⚠️ android_vr 客户端不支持 Cookies，本次下载将不使用 Cookies")


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
            "--ignore-config",  # 忽略外部 yt-dlp 配置文件，确保只使用应用内设置
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
        
        # 记录完整命令（关键调试信息）
        logger.info("[SubEmbed] === 最终 yt-dlp 命令 ===")
        # 分行输出关键字幕/容器参数
        cmd_str = ' '.join(cmd)
        
        # 特殊处理 --extractor-args，可能有多个
        extractor_args_indices = [i for i, x in enumerate(cmd) if x == '--extractor-args']
        if extractor_args_indices:
            for idx in extractor_args_indices:
                val = cmd[idx + 1] if idx + 1 < len(cmd) else '?'
                logger.info("[SubEmbed] CLI: --extractor-args {}", val)
        
        # 处理其他参数
        for flag in ['--embed-subs', '--write-sub', '--write-auto-sub', '--sub-langs',
                      '--convert-subs', '--merge-output-format', '-f', '--cookies']:
            if flag in cmd_str:
                idx = cmd.index(flag) if flag in cmd else -1
                if idx >= 0:
                    # 带参数的 flag
                    if flag in ('-f', '--sub-langs', '--convert-subs', '--merge-output-format', '--cookies'):
                        val = cmd[idx + 1] if idx + 1 < len(cmd) else '?'
                        logger.info("[SubEmbed] CLI: {} {}", flag, val)
                    else:
                        logger.info("[SubEmbed] CLI: {}", flag)
        
        has_embed = '--embed-subs' in cmd
        has_merge = '--merge-output-format' in cmd
        has_extractor_args = '--extractor-args' in cmd
        has_cookies = '--cookies' in cmd
        logger.info("[SubEmbed] --embed-subs: {}  --merge-output-format: {}  --extractor-args: {} (数量: {})  --cookies: {}", 
                    has_embed, has_merge, has_extractor_args, len(extractor_args_indices), has_cookies)
        if not has_embed:
            logger.warning("[SubEmbed] ⚠️ 命令中没有 --embed-subs！字幕将不会被嵌入到视频中！")
        if not has_extractor_args:
            logger.warning("[VR] ⚠️ 命令中没有 --extractor-args！可能使用了错误的客户端！")
        elif not any('youtube:' in cmd[idx+1] for idx in extractor_args_indices if idx+1 < len(cmd)):
            logger.warning("[VR] ⚠️ 命令中没有 youtube 的 extractor-args！VR 客户端未配置！")
        logger.debug("yt-dlp full command: {}", cmd_str)

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
            # bufsize=1 removed - line buffering not supported in binary mode
            **popen_kwargs,
        )

        tail: deque[str] = deque(maxlen=120)

        re_dest = re.compile(r"^\[download\]\s+Destination:\s+(?P<path>.+)$")
        # yt-dlp 合并输出格式：[Merger] Merging formats into xxx.mp4（路径可能有引号也可能没有）
        re_merge = re.compile(r'^\[Merger\]\s+Merging formats into\s+"?(?P<path>[^"]+)"?$')
        re_extract_audio = re.compile(r'^\[ExtractAudio\]\s+Destination:\s+(?P<path>.+)$')

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

            # 捕获字幕下载信息 (当 skip_download=True 时尤为重要)
            if "Writing video subtitles to:" in line:
                self.status_msg.emit("正在下载字幕...")
                try:
                    # 格式通常为: [info] Writing video subtitles to: <filename>
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        path = parts[1].strip()
                        if path:
                            self.dest_paths.add(path)
                            self.output_path_ready.emit(path)
                            # 模拟进度更新，让 UI 显示活跃状态
                            self.progress.emit({
                                "status": "downloading",
                                "filename": os.path.basename(path),
                                "downloaded_bytes": 100,
                                "total_bytes": 100,
                                "percent": 100.0
                            })
                except Exception:
                    pass

            # 捕获字幕转换信息
            if "[FFmpegSubtitlesConvertor]" in line:
                self.status_msg.emit("正在转换字幕格式...")

            if self.is_cancelled:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
                break

            # Status hooks for merge/postprocess stages
            if line.startswith("[Merger]") or line.startswith("[ExtractAudio]") or "Merging formats" in line:
                self.status_msg.emit(line)
                logger.debug("捕获到合并/后处理行: {}", line)

                # Capture final merged output path
                m2 = re_merge.match(line)
                if m2:
                    p = (m2.group("path") or "").strip()
                    logger.info("匹配到合并输出路径: {}", p)
                    if p:
                        try:
                            p_abs = os.path.abspath(p)
                        except Exception:
                            p_abs = p
                        self.output_path = p_abs
                        logger.info("更新 output_path 为合并后的文件: {}", p_abs)
                        try:
                            self.output_path_ready.emit(p_abs)
                        except Exception:
                            pass
                else:
                    logger.debug("未匹配合并正则，行内容: {}", repr(line))
                
                # Capture audio extraction output path
                m3 = re_extract_audio.match(line)
                if m3:
                    p = (m3.group("path") or "").strip()
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
                    parts[8] if len(parts) > 8 else ""
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

                    # === 格式验证：检测是否降级到纯音频 ===
                    # 注意：对于 bv*+ba 格式，yt-dlp 会分别下载视频和音频流，
                    # 在音频流下载阶段看到 vcodec=none 是正常的，不应该警告
                    if not self._format_warning_shown and self._original_format and total > 0:
                        pct = (downloaded / total) * 100.0
                        # 只有当原始选择包含视频格式（bv），但当前是纯音频且进度超过50%时才警告
                        if ("bv" in self._original_format.lower() and 
                            vcodec in ("", "NA", "none") and 
                            acodec not in ("", "NA", "none") and 
                            pct > 50.0):
                            logger.warning("[FormatDownload] 🔴 格式降级警告！")
                            logger.warning("[FormatDownload] 原始选择: {}", self._original_format)
                            logger.warning("[FormatDownload] 当前下载: vcodec={}, acodec={}", vcodec, acodec)
                            self.status_msg.emit("⚠️ 检测到格式降级：原始选择了视频，但现在仅下载音频！请检查网络或重新选择格式")
                            self._format_warning_shown = True  # 只警告一次

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
                    
                    # 友好的后处理器名称映射
                    pp_names = {
                        "MoveFiles": "移动文件",
                        "Merger": "合并音视频",
                        "FFmpegMerger": "合并音视频",
                        "EmbedThumbnail": "嵌入封面",
                        "FFmpegMetadata": "嵌入元数据",
                        "FFmpegThumbnailsConvertor": "转换封面格式",
                        "FFmpegExtractAudio": "提取音频",
                        "FFmpegVideoConvertor": "转换视频格式",
                        "FFmpegEmbedSubtitle": "嵌入字幕",
                        "SponsorBlock": "跳过赞助片段",
                        "ModifyChapters": "修改章节",
                    }
                    pp_display = pp_names.get(pp, pp) if pp else "处理"
                    
                    status_names = {
                        "started": "开始",
                        "processing": "处理中",
                        "finished": "完成",
                    }
                    status_display = status_names.get(status, status) if status else ""
                    
                    if pp_display and status_display:
                        msg = f"后处理: {pp_display} ({status_display})"
                    elif pp_display:
                        msg = f"后处理: {pp_display}..."
                    else:
                        msg = "后处理中..."
                    
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

            # Other informative lines - 特殊处理字幕相关信息
            if line.startswith("["):
                # 检测字幕下载
                if "subtitles" in line.lower() or "subtitle" in line.lower():
                    if "Writing" in line and "subtitles" in line:
                        # [info] Writing video subtitles to: xxx.zh-Hans.srt
                        self.status_msg.emit("📝 正在下载字幕...")
                        logger.info("字幕下载: {}", line)
                    elif "Downloading" in line and "subtitle" in line:
                        self.status_msg.emit("📝 正在下载字幕...")
                        logger.info("字幕下载: {}", line)
                    else:
                        self.status_msg.emit(line)
                else:
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
            error_text = "\n".join(tail)
            
            # === SSL错误和格式降级检测 ===
            has_ssl_error = "EOF occurred in violation of protocol" in error_text or "_ssl.c" in error_text
            has_format_fallback = "[download] ERROR:" in error_text and ("Requested format" in error_text or "format" in error_text.lower())
            
            if has_ssl_error:
                self._ssl_error_count += 1
                logger.warning("检测到SSL错误 (第 {} 次): {}", self._ssl_error_count, error_text[-200:])
                
                # SSL错误通常是网络抖动导致，建议用户重试，不要修改格式
                self.status_msg.emit("⚠️ 检测到网络SSL错误，建议检查网络连接后重试")
                
            if has_format_fallback:
                logger.warning("检测到格式降级！原始格式: {}", self._original_format)
                # 发出警告但不中断，让用户看到真实的降级原因
                self.status_msg.emit("⚠️ 原始格式不可用，yt-dlp正在选择备选格式")
            
            # Cookie 错误检测：在抛出异常前检查是否为 Cookie 问题
            try:
                from ..auth.cookie_sentinel import cookie_sentinel
                if cookie_sentinel.detect_cookie_error(error_text):
                    # 发送 Cookie 错误信号（供 UI 拦截）
                    self.cookie_error_detected.emit(error_text)
                    logger.warning("[CookieSentinel] 检测到 Cookie 相关错误")
            except Exception as e:
                logger.debug(f"Cookie 错误检测失败: {e}")
            
            raise RuntimeError("yt-dlp.exe 退出异常:\n" + error_text)
        
        # 执行封面嵌入后处理（使用外置工具）
        self._embed_thumbnail_postprocess(merged_opts)
        
        # 执行字幕后处理（验证、双语合并）
        self._subtitle_postprocess(merged_opts)

        # 执行 VR 后处理（EAC 转码 + 元数据注入）
        self._vr_postprocess(merged_opts)
        
        # 清理遗留的缩略图文件
        self._cleanup_thumbnail_files(merged_opts)
        
        # 清理遗留的字幕文件（嵌入成功且用户不需要外置文件时）
        self._cleanup_subtitle_files(merged_opts)

    def stop(self) -> None:
        """外部调用此方法暂停/取消下载"""
        self.is_cancelled = True
        proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
    
    def _validate_format_selection(self, format_str: str | None) -> str | None:
        """
        验证格式选择，防止自动降级到纯音频
        
        yt-dlp 的格式选择器会在优先选项失败时自动降级，但这可能导致从
        视频+音频降级到纯音频。此方法检测并警告这种情况。
        
        Args:
            format_str: yt-dlp format 参数字符串
            
        Returns:
            原始格式字符串或经过验证的格式字符串
        """
        if not format_str or not isinstance(format_str, str):
            return format_str
        
        # 检测纯音频格式的指示器
        audio_only_keywords = [
            "bestaudio",  # 纯最佳音频
            "ba",         # 音频流简写（如果没有视频部分）
            "aac",        # 音频编码
            "mp3",        # 音频格式
            "opus",       # 音频编码
            "vorbis",     # 音频编码
        ]
        
        # 检测视频格式的指示器  
        video_keywords = ["bv", "video", "mp4", "webm", "mkv", "h264", "h265", "av01", "vp9"]
        
        fmt_lower = format_str.lower()
        
        # 如果格式包含视频指示符，说明包含视频流，是安全的
        if any(kw in fmt_lower for kw in video_keywords):
            logger.debug("[FormatValidator] 格式包含视频流: {}", format_str)
            return format_str
        
        # 如果格式只有音频指示符且没有视频指示符，这是问题
        if any(kw in fmt_lower for kw in audio_only_keywords):
            logger.warning("[FormatValidator] ⚠️ 检测到纯音频格式! 原始格式: {}", self._original_format)
            logger.warning("[FormatValidator] 当前格式: {}", format_str)
            self.status_msg.emit("⚠️ 警告：下载格式已降级为纯音频！如果需要视频，请重新选择格式后重试")
            return format_str
        
        logger.debug("[FormatValidator] 格式验证完成: {}", format_str)
        return format_str
    
    def _embed_thumbnail_postprocess(self, opts: dict[str, Any]) -> None:
        """使用外置工具执行封面嵌入后处理"""
        # 检查是否启用了封面嵌入
        embed_thumbnail = config_manager.get("embed_thumbnail", True)
        logger.info("封面嵌入后处理开始 - embed_thumbnail={}", embed_thumbnail)
        
        if not embed_thumbnail:
            logger.debug("封面嵌入未启用，跳过后处理")
            return
        
        # 检查是否有下载封面
        if not opts.get("writethumbnail"):
            logger.debug("未下载封面，跳过嵌入")
            return
        
        logger.info("output_path: {}", self.output_path)
        logger.info("dest_paths: {}", self.dest_paths)
        
        # 首先尝试找到最终合并的文件
        # 问题：使用 -q 静默模式时，[Merger] 行被抑制，output_path 可能仍是分片文件
        final_output = self._find_final_merged_file()
        if final_output:
            logger.info("找到最终合并文件: {}", final_output)
            self.output_path = final_output
        
        # 收集需要处理的视频文件和对应的封面文件
        files_to_process: list[tuple[str, str]] = []  # (video_path, thumbnail_path)
        
        # 检查主输出路径
        if self.output_path and os.path.exists(self.output_path):
            logger.info("检查主输出路径: {}", self.output_path)
            thumb_path = self._find_thumbnail_file(self.output_path)
            if thumb_path:
                logger.info("找到封面文件: {}", thumb_path)
                files_to_process.append((self.output_path, thumb_path))
            else:
                logger.warning("未找到封面文件 for: {}", self.output_path)
        
        # 检查所有捕获的目标路径（排除分片文件）
        for dest_path in self.dest_paths:
            # 跳过分片文件（.f数字.扩展名）
            if re.search(r'\.[fF]\d+\.\w+$', dest_path):
                logger.debug("跳过分片文件: {}", dest_path)
                continue
            if os.path.exists(dest_path) and dest_path != self.output_path:
                logger.info("检查目标路径: {}", dest_path)
                thumb_path = self._find_thumbnail_file(dest_path)
                if thumb_path:
                    logger.info("找到封面文件: {}", thumb_path)
                    files_to_process.append((dest_path, thumb_path))
                else:
                    logger.debug("未找到封面文件 for: {}", dest_path)
        
        if not files_to_process:
            logger.warning("常规方法未找到需要嵌入封面的文件，尝试备用方案...")
            
            # 备用方案：直接扫描输出目录
            output_dir = None
            if self.output_path:
                output_dir = os.path.dirname(self.output_path)
            elif self.dest_paths:
                output_dir = os.path.dirname(next(iter(self.dest_paths)))
            
            if output_dir and os.path.exists(output_dir):
                logger.info("扫描输出目录: {}", output_dir)
                # 查找所有视频文件和封面文件
                video_files = []
                thumb_files = []
                video_exts = {'.mp4', '.mkv', '.webm', '.avi', '.mov', '.m4a', '.mp3', '.flac', '.opus'}
                thumb_exts = {'.jpg', '.jpeg', '.png', '.webp'}
                
                for f in os.listdir(output_dir):
                    full_path = os.path.join(output_dir, f)
                    if not os.path.isfile(full_path):
                        continue
                    ext = os.path.splitext(f)[1].lower()
                    # 排除分片文件
                    if re.search(r'\.[fF]\d+\.\w+$', f):
                        continue
                    if ext in video_exts:
                        video_files.append(full_path)
                        logger.debug("发现视频文件: {}", f)
                    elif ext in thumb_exts:
                        thumb_files.append(full_path)
                        logger.debug("发现封面文件: {}", f)
                
                # 匹配视频和封面（通过基础文件名）
                for video_path in video_files:
                    video_base = os.path.splitext(os.path.basename(video_path))[0]
                    for thumb_path in thumb_files:
                        thumb_base = os.path.splitext(os.path.basename(thumb_path))[0]
                        if video_base == thumb_base:
                            logger.info("备用方案匹配成功: {} + {}", 
                                       os.path.basename(video_path), 
                                       os.path.basename(thumb_path))
                            files_to_process.append((video_path, thumb_path))
                            # 更新 output_path
                            self.output_path = video_path
                            break
        
        if not files_to_process:
            logger.warning("未找到需要嵌入封面的文件 - 可能封面文件命名不匹配")
            logger.info("尝试列出输出目录的文件...")
            if self.output_path:
                try:
                    output_dir = os.path.dirname(self.output_path)
                    output_base = os.path.splitext(os.path.basename(self.output_path))[0]
                    logger.info("输出目录: {}", output_dir)
                    logger.info("基础文件名: {}", output_base)
                    
                    # 列出同目录下的所有图片文件
                    if os.path.exists(output_dir):
                        for f in os.listdir(output_dir):
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                                logger.info("  发现图片文件: {}", f)
                except Exception as e:
                    logger.error("列出目录文件失败: {}", e)
            return
        
        # 检查工具可用性
        tool_status = thumbnail_embedder.get_tool_status()
        logger.info("封面嵌入工具状态: {}", tool_status)
        
        if not thumbnail_embedder.is_available():
            logger.warning("没有可用的封面嵌入工具，跳过封面嵌入")
            self.thumbnail_embed_warning.emit(
                "⚠️ 封面嵌入工具不可用\n"
                "请在设置中下载 AtomicParsley 或确保 FFmpeg 已安装。"
            )
            return
        
        # 执行封面嵌入
        for video_path, thumb_path in files_to_process:
            ext = os.path.splitext(video_path)[1].lower().lstrip(".")
            
            # 检查格式兼容性
            if not can_embed_thumbnail(ext):
                warning = get_unsupported_formats_warning(ext)
                if warning:
                    logger.warning("格式不支持封面嵌入: {}", warning)
                    self.thumbnail_embed_warning.emit(warning)
                continue
            
            # 执行嵌入
            self.status_msg.emit(f"[封面嵌入] 正在处理: {os.path.basename(video_path)}")
            
            result = thumbnail_embedder.embed_thumbnail(
                video_path,
                thumb_path,
                progress_callback=lambda msg: self.status_msg.emit(f"[封面嵌入] {msg}")
            )
            
            if result.success:
                logger.info("封面嵌入成功: {} (使用 {})", video_path, result.tool_used)
                self.status_msg.emit(f"[封面嵌入] ✓ 成功: {os.path.basename(video_path)}")
            elif result.skipped:
                logger.warning("封面嵌入跳过: {}", result.message)
                self.thumbnail_embed_warning.emit(result.message)
            else:
                logger.error("封面嵌入失败: {}", result.message)
                self.thumbnail_embed_warning.emit(f"封面嵌入失败: {result.message}")
    
    def _find_final_merged_file(self) -> str | None:
        """查找最终合并的输出文件
        
        当使用 -q 静默模式时，[Merger] 输出被抑制，output_path 可能是分片文件。
        此方法通过分析分片文件名找到最终合并的文件。
        
        分片文件命名：xxx.f137.mp4, xxx.f251.webm
        合并后文件：xxx.mp4
        """
        if not self.output_path:
            logger.debug("output_path 为空，无法查找合并文件")
            return None
        
        logger.debug("_find_final_merged_file: output_path={}", self.output_path)
        logger.debug("_find_final_merged_file: output_path exists={}", os.path.exists(self.output_path))
        
        # 检查当前 output_path 是否是分片文件
        match = re.search(r'^(.+)\.[fF]\d+\.(\w+)$', self.output_path)
        if not match:
            # 不是分片文件格式，检查文件是否存在
            if os.path.exists(self.output_path):
                logger.debug("output_path 不是分片文件格式且存在: {}", self.output_path)
                return self.output_path
            logger.debug("output_path 不是分片文件格式: {}", self.output_path)
            return None
        
        # 提取基础名和可能的输出格式
        base_name = match.group(1)
        logger.debug("分片文件基础名: {}", base_name)
        
        # 可能的合并输出格式（按优先级）
        possible_extensions = [".mp4", ".mkv", ".webm", ".avi", ".mov"]
        
        # 尝试查找合并后的文件
        for ext in possible_extensions:
            merged_path = base_name + ext
            if os.path.exists(merged_path):
                logger.info("找到合并后的文件: {}", merged_path)
                return merged_path
        
        # 也检查是否在 dest_paths 中有非分片文件
        for dest_path in self.dest_paths:
            if not re.search(r'\.[fF]\d+\.\w+$', dest_path):
                # 不是分片文件
                if os.path.exists(dest_path):
                    logger.info("在 dest_paths 中找到非分片文件: {}", dest_path)
                    return dest_path
        
        logger.debug("未找到合并后的文件，base_name={}", base_name)
        return None

    def _find_thumbnail_file(self, video_path: str) -> str | None:
        """查找视频文件对应的封面文件
        
        yt-dlp 的封面文件命名规则：
        - 封面：%(title)s.jpg
        - 视频分片：%(title)s.f137.mp4
        - 最终合并：%(title)s.mp4
        
        所以我们需要尝试：
        1. 直接匹配（去掉视频扩展名加图片扩展名）
        2. 去掉格式标识符（如 .f137）后再匹配
        """
        base_path = os.path.splitext(video_path)[0]
        thumbnail_extensions = [".jpg", ".jpeg", ".webp", ".png"]
        
        # 方法1：直接匹配
        for ext in thumbnail_extensions:
            thumb_path = base_path + ext
            if os.path.exists(thumb_path):
                return thumb_path
        
        # 方法2：去掉格式后缀（如 .f137, .f251 等）
        # yt-dlp 分片文件格式：title.f137.mp4 → 基础名是 title.f137
        # 但封面文件是：title.jpg
        # 匹配 .f数字 格式后缀
        match = re.match(r'^(.+)\.[fF]\d+$', base_path)
        if match:
            clean_base = match.group(1)
            logger.debug("尝试去掉格式后缀: {} -> {}", base_path, clean_base)
            for ext in thumbnail_extensions:
                thumb_path = clean_base + ext
                if os.path.exists(thumb_path):
                    return thumb_path
        
        return None
    
    def _cleanup_thumbnail_files(self, opts: dict[str, Any]) -> None:
        """清理下载后遗留的缩略图文件"""
        # 只在下载了封面时清理
        if not opts.get("writethumbnail"):
            return
        
        # 收集所有可能的基础路径
        paths_to_check = []
        
        if self.output_path and os.path.exists(self.output_path):
            paths_to_check.append(self.output_path)
        
        # 也检查所有捕获的目标路径
        for dest_path in self.dest_paths:
            if os.path.exists(dest_path):
                paths_to_check.append(dest_path)
        
        # 查找同名的缩略图文件（常见扩展名）
        thumbnail_extensions = [".webp", ".jpg", ".jpeg", ".png"]
        
        for path in paths_to_check:
            base_path = os.path.splitext(path)[0]
            for ext in thumbnail_extensions:
                thumb_file = base_path + ext
                if os.path.exists(thumb_file):
                    try:
                        os.remove(thumb_file)
                        logger.debug("已删除缩略图文件: {}", thumb_file)
                    except Exception as e:
                        logger.warning("无法删除缩略图文件 {}: {}", thumb_file, e)

    def _cleanup_subtitle_files(self, opts: dict[str, Any]) -> None:
        """
        清理嵌入后遗留的字幕文件
        
        仅在以下条件同时满足时删除：
        1. 字幕已嵌入到视频容器 (embedsubtitles=True)
        2. 用户未要求保留外置文件 (write_separate_file=False)
        """
        # 未启用嵌入字幕，字幕文件本身就是最终产物，不删除
        if not opts.get("embedsubtitles"):
            logger.debug("[SubCleanup] embedsubtitles 未启用，保留字幕文件")
            return
        
        # 检查用户是否要求保留外置文件
        write_separate = config_manager.get("subtitle_write_separate_file", False)
        if write_separate:
            logger.debug("[SubCleanup] write_separate_file=True，保留字幕文件")
            return
        
        # 收集所有可能的基础路径
        paths_to_check = []
        if self.output_path and os.path.exists(self.output_path):
            paths_to_check.append(self.output_path)
        for dest_path in self.dest_paths:
            if os.path.exists(dest_path):
                paths_to_check.append(dest_path)
        
        subtitle_extensions = [".srt", ".ass", ".vtt"]
        deleted_count = 0
        
        for path in paths_to_check:
            parent_dir = os.path.dirname(path)
            stem = os.path.splitext(os.path.basename(path))[0]
            
            # 查找 {stem}.*.{ext} 格式的字幕文件（如 video.zh-Hans.srt）
            try:
                for filename in os.listdir(parent_dir):
                    if not filename.startswith(stem):
                        continue
                    _, ext = os.path.splitext(filename)
                    if ext.lower() in subtitle_extensions:
                        sub_file = os.path.join(parent_dir, filename)
                        try:
                            os.remove(sub_file)
                            deleted_count += 1
                            logger.debug("[SubCleanup] 已删除字幕文件: {}", sub_file)
                        except Exception as e:
                            logger.warning("[SubCleanup] 无法删除字幕文件 {}: {}", sub_file, e)
            except Exception as e:
                logger.warning("[SubCleanup] 遍历目录失败 {}: {}", parent_dir, e)
        
        if deleted_count > 0:
            logger.info("[SubCleanup] 共清理 {} 个字幕文件（已嵌入到视频）", deleted_count)

    def _subtitle_postprocess(self, opts: dict[str, Any]) -> None:
        """
        字幕后处理
        
        功能：
        - 验证字幕文件存在性和完整性
        - 自动合并双语字幕
        """
        from ..processing import subtitle_processor
        
        logger.info("字幕后处理开始")
        
        try:
            result = subtitle_processor.process(
                output_path=self.output_path,
                opts=opts,
                status_callback=lambda msg: self.status_msg.emit(msg)
            )
            
            if result.success:
                logger.info("字幕后处理成功: {}", result.message)
                
                if result.merged_file:
                    self.status_msg.emit("[字幕处理] ✓ 双语字幕已生成")
                    logger.info("双语字幕文件: {}", result.merged_file)
                
                if result.processed_files:
                    logger.info("处理了 {} 个字幕文件", len(result.processed_files))
            else:
                logger.warning("字幕后处理失败: {}", result.message)
        
        except Exception as e:
            logger.exception("字幕后处理异常: {}", e)
            # 不阻塞主流程，只记录错误

    def _check_ffmpeg_v360_support(self, ffmpeg_exe: str) -> bool:
        """检查 FFmpeg 是否支持 v360 滤镜"""
        try:
            creation_flags = hardware_manager.get_ffmpeg_creation_flags()
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                
            # 使用 -filters 检查 v360 支持
            result = subprocess.run(
                [ffmpeg_exe, "-filters"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
                startupinfo=startupinfo,
                encoding="utf-8",
                errors="replace",
                check=False
            )
            return "v360" in result.stdout
        except Exception as e:
            logger.warning("检查 FFmpeg v360 支持失败: {}", e)
            return False

    def _vr_postprocess(self, opts: dict[str, Any]) -> None:
        """VR 后处理：EAC 转码 + 元数据注入 (带分级防御体系)"""
        proj = str(opts.get("__vr_projection") or "").lower()
        convert_eac = bool(opts.get("__vr_convert_eac") or False)
        
        # 1. 检查是否需要处理
        needs_inject = proj and proj != "unknown"
        # 强制开启检测：如果全局设置开了，也检查（虽然 UI 上通常是绑定的）
        global_convert = config_manager.get("vr_eac_auto_convert", False)
        needs_convert = (convert_eac or global_convert) and proj == "eac"
        
        if not needs_inject and not needs_convert:
            # 增加对 Mesh 格式的提示，避免用户疑惑为何没转码
            if (convert_eac or global_convert) and proj == "mesh":
                logger.warning("[VR] 无法自动转换 Mesh 投影，跳过转码")
                self.status_msg.emit("⚠️ 源视频为 Mesh 格式，暂不支持自动转码")
            return

        logger.info("[VR] 开始 VR 后处理: Proj={}, ConvertEAC={}", proj, needs_convert)

        # 找到最终文件
        final_file = self._find_final_merged_file() or self.output_path
        if not final_file or not os.path.exists(final_file):
            logger.warning("[VR] 无法找到最终文件，跳过 VR 后处理")
            return

        # 准备 ffmpeg 路径
        ffmpeg_exe = opts.get("ffmpeg_location") or "ffmpeg"
        if os.path.isdir(ffmpeg_exe):
             ffmpeg_exe = os.path.join(ffmpeg_exe, "ffmpeg.exe")

        # 2. EAC 转码 (核心防御逻辑)
        if needs_convert:
            # 2.0 前置检查
            if not self._check_ffmpeg_v360_support(ffmpeg_exe):
                logger.warning("[VR] FFmpeg 不支持 v360 滤镜，跳过转码")
                self.status_msg.emit("⚠️ FFmpeg 版本过旧，不支持 VR 转码")
                needs_convert = False
            
            # 2.1 风险评估
            # 获取视频分辨率高度 (从 info 或 ffprobe)
            video_height = 0
            try:
                # 尝试从 opts/info 中获取
                if opts.get("height"):
                    video_height = int(opts.get("height"))
                # 如果没有，可以用 ffprobe (暂时跳过，假设 yt-dlp 提供了)
            except Exception:
                pass
            
            # 如果没有高度信息，为了安全起见，假设它是 4K (中等风险)
            if video_height == 0:
                video_height = 2160
            
            # 读取设置
            max_res_setting = int(config_manager.get("vr_max_resolution", 2160))
            if video_height > max_res_setting:
                logger.warning("[VR] 视频分辨率 {}p 超过设置限制 {}p，跳过转码", video_height, max_res_setting)
                self.status_msg.emit(f"⚠️ 跳过 VR 转码: 分辨率过高 ({video_height}p)")
                needs_convert = False # 降级为仅注入
            
            # 硬件资源评估
            risk = hardware_manager.assess_transcode_risk(video_height)
            if risk == RiskLevel.CRITICAL:
                # 除非用户强制开启了 8K 允许，否则拦截
                if max_res_setting < 4320:
                    logger.warning("[VR] 系统资源不足 (Critical Risk)，强制跳过转码")
                    self.status_msg.emit("⚠️ 系统资源不足，已取消高风险转码")
                    needs_convert = False

        if needs_convert:
            self.status_msg.emit("正在进行 VR 投影转换 (EAC -> Equi)...")
            logger.info("[VR] 执行 EAC 转码...")
            
            ext = os.path.splitext(final_file)[1]
            output_converted = os.path.splitext(final_file)[0] + "_equi" + ext
            
            # 2.2 硬件加速策略
            hw_mode = config_manager.get("vr_hw_accel_mode", "auto") # auto, cpu, gpu
            encoders = hardware_manager.get_gpu_encoders()
            use_gpu = False
            gpu_encoder = ""
            
            if hw_mode == "gpu" or (hw_mode == "auto" and encoders):
                if "h264_nvenc" in encoders:
                    gpu_encoder = "h264_nvenc"
                    use_gpu = True
                elif "h264_qsv" in encoders:
                    gpu_encoder = "h264_qsv"
                    use_gpu = True
                elif "h264_amf" in encoders:
                    gpu_encoder = "h264_amf"
                    use_gpu = True
            
            if hw_mode == "gpu" and not use_gpu:
                logger.warning("[VR] 强制 GPU 模式但未检测到编码器，回退到 CPU")
            
            # 2.3 构建命令
            cmd = [ffmpeg_exe, "-y", "-i", final_file, "-vf", "v360=eac:e"]
            
            if use_gpu:
                # GPU 编码参数
                cmd.extend(["-c:v", gpu_encoder])
                if gpu_encoder == "h264_nvenc":
                    cmd.extend(["-preset", "p4", "-cq", "20"]) # 平衡画质
                elif gpu_encoder == "h264_qsv":
                    cmd.extend(["-global_quality", "20"])
                logger.info(f"[VR] 使用 GPU 加速: {gpu_encoder}")
            else:
                # CPU 编码参数
                cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"])
                # 线程控制
                cpu_priority = config_manager.get("vr_cpu_priority", "low")
                threads = hardware_manager.get_optimal_ffmpeg_threads(is_cpu_mode=True)
                if cpu_priority == "low":
                    threads = max(1, threads - 1) # 进一步降低
                elif cpu_priority == "high":
                    threads = 0 # 自动 (全速)
                
                if threads > 0:
                    cmd.extend(["-threads", str(threads)])
                logger.info(f"[VR] 使用 CPU 编码 (Threads={threads})")

            cmd.extend(["-c:a", "copy", output_converted])
            
            # 2.4 低优先级运行
            creation_flags = hardware_manager.get_ffmpeg_creation_flags()
            
            # 获取视频总时长用于进度计算
            total_duration = 0.0
            try:
                total_duration = float(opts.get("duration") or 0)
            except Exception:
                pass

            if self._run_simple_ffmpeg(cmd, creation_flags=creation_flags, total_duration=total_duration):
                # 成功，处理文件
                keep_source = config_manager.get("vr_keep_source", True)
                try:
                    if not keep_source:
                        os.remove(final_file)
                        os.rename(output_converted, final_file)
                        logger.info("[VR] EAC 转码成功，文件已替换")
                    else:
                        # 如果保留原片，我们将转码后的文件作为"最终文件"进行后续元数据注入
                        # 但原文件保留在原地 (通常会被重命名为 .orig 或类似，这里我们不重命名原文件，
                        # 而是把 output_converted 视为新的 final_file)
                        # 为了逻辑简单，我们交换文件名：
                        # final_file (EAC) -> final_file.eac.mp4
                        # output_converted (Equi) -> final_file
                        backup_file = os.path.splitext(final_file)[0] + ".eac" + ext
                        if os.path.exists(backup_file):
                            os.remove(backup_file)
                        os.rename(final_file, backup_file)
                        os.rename(output_converted, final_file)
                        logger.info("[VR] EAC 转码成功，源文件已备份为 {}", backup_file)
                        
                    proj = "equirectangular" # 更新状态
                except Exception as e:
                    logger.error("[VR] 替换文件失败: {}", e)
            else:
                self.status_msg.emit("⚠️ VR 转码失败，保留原格式")
                if os.path.exists(output_converted):
                    os.remove(output_converted)

        # 3. 元数据注入
        ext = os.path.splitext(final_file)[1].lower()
        if ext not in (".mp4", ".mov"):
            logger.info("[VR] 跳过元数据注入: 容器 {} 不支持", ext)
            if ext == ".mkv":
                self.status_msg.emit("⚠️ MKV 格式不支持 VR 标记，建议使用 MP4")
            else:
                self.status_msg.emit(f"⚠️ {ext} 格式不支持 VR 标记")
            return

        self.status_msg.emit("正在注入 VR 元数据...")
        
        # 参数映射
        md = metadata_utils.Metadata()
        stereo = str(opts.get("__vr_stereo_mode") or "").lower()
        
        if stereo == "stereo_tb":
            md.stereo_mode = "top-bottom"
        elif stereo == "stereo_sbs":
            md.stereo_mode = "left-right"
        elif stereo == "mono":
            md.stereo_mode = "none"
            
        if proj == "equirectangular":
            md.projection = "equirectangular"
        elif proj == "eac":
             pass
        elif proj == "mesh":
             pass
             
        if not md.stereo_mode and not md.projection:
             logger.info("[VR] 无需注入元数据")
             return

        temp_injected = final_file + ".temp_vr.mp4"
        try:
            logger.info("[VR] 注入元数据: Stereo={}, Proj={}", md.stereo_mode, md.projection)
            metadata_utils.inject_metadata(final_file, temp_injected, md, lambda x: logger.debug("[SpatialMedia] {}", x))
            
            if os.path.exists(temp_injected):
                os.remove(final_file)
                os.rename(temp_injected, final_file)
                self.status_msg.emit("VR 元数据注入成功")
                logger.info("[VR] 元数据注入完成")
            else:
                logger.warning("[VR] 注入未生成文件")
        except Exception as e:
            logger.error("[VR] 元数据注入异常: {}", e)
            if os.path.exists(temp_injected):
                os.remove(temp_injected)

    def _run_simple_ffmpeg(self, cmd: list[str], creation_flags: int = 0, total_duration: float = 0.0) -> bool:
        """运行 ffmpeg 命令并捕获输出"""
        try:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creation_flags,
                encoding="utf-8",
                errors="replace"
            )
            
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    line = line.strip()
                    if "time=" in line:
                        try:
                            # Parse time=HH:MM:SS.mm
                            time_str = line[line.find("time=") + 5 :].split(" ")[0]
                            
                            if total_duration > 0:
                                current_seconds = 0.0
                                parts = time_str.split(':')
                                if len(parts) == 3:
                                    current_seconds = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                                elif len(parts) == 2:
                                    current_seconds = float(parts[0]) * 60 + float(parts[1])
                                else:
                                    current_seconds = float(time_str)
                                
                                percent = min(99.9, (current_seconds / total_duration) * 100)
                                self.status_msg.emit(f"正在进行 VR 投影转换... {percent:.1f}% ({time_str})")
                            else:
                                self.status_msg.emit(f"正在进行 VR 投影转换... {time_str}")
                        except Exception:
                            pass
            
            return proc.returncode == 0
        except Exception as e:
            logger.error("FFmpeg 运行失败: {}", e)
            return False

