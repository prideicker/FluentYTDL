from __future__ import annotations

import os
import re
import subprocess
import threading
from collections import deque
from typing import Any, cast

from PySide6.QtCore import QThread, Signal

from ..utils.logger import logger
from ..utils.paths import locate_runtime_tool
from ..utils.translator import translate_error
from ..youtube.youtube_service import YoutubeServiceOptions, youtube_service
from ..youtube.yt_dlp_cli import YtDlpCancelled, prepare_yt_dlp_env, ydl_opts_to_cli_args
from .features import (
    DownloadContext,
    MetadataFeature,
    SponsorBlockFeature,
    SubtitleFeature,
    ThumbnailFeature,
    VRFeature,
)


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
    """VR 解析工人：智能处理 VR 视频和播放列表"""

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
            # 策略：
            # 1. 如果 URL 看起来像播放列表，先尝试 Flat 解析
            # 2. 如果 Flat 解析发现是单视频（或 URL 不像播放列表），则使用 android_vr 客户端进行深度 VR 解析
            
            is_playlist_url = "list=" in self.url
            info = None
            
            if is_playlist_url:
                try:
                    # 尝试作为播放列表解析
                    info = youtube_service.extract_playlist_flat(
                        self.url, 
                        cancel_event=self._cancel_event
                    )
                    
                    # 检查是否真的是播放列表
                    if info.get("_type") != "playlist" and not info.get("entries"):
                        # 只有单个条目或不是播放列表，视为单视频，需要重新解析
                        info = None
                except Exception:
                    # 播放列表解析失败，可能是单视频，忽略错误继续尝试 VR 解析
                    info = None
            
            if self._cancel_event.is_set():
                return

            if info is None:
                # 单视频模式：使用 android_vr 客户端
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

    def __init__(
        self, 
        row: int, 
        url: str, 
        options: YoutubeServiceOptions | None = None,
        *,
        vr_mode: bool = False
    ):
        super().__init__()
        self.row = row
        self.url = url
        self.options = options
        self.vr_mode = vr_mode
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        try:
            if self.vr_mode:
                # VR 模式：使用 android_vr 客户端获取详情
                info = youtube_service.extract_vr_info_sync(self.url, cancel_event=self._cancel_event)
            else:
                # 普通模式：使用标准流程
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
        
        # 初始化功能模块
        self.features = [
            SponsorBlockFeature(),
            MetadataFeature(),
            SubtitleFeature(),
            ThumbnailFeature(),
            VRFeature(),
        ]

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

            # === Feature Pipeline: Configuration & Pre-flight ===
            # 构建上下文并运行 Feature 链
            context = DownloadContext(self, merged)
            
            for feature in self.features:
                feature.configure(merged)
                feature.on_download_start(context)

            # Capture intent flags before stripping
            is_vr_mode = merged.get("__fluentytdl_use_android_vr", False)
            should_embed_subs = merged.get("embedsubtitles", False)

            # Strip internal meta options (never pass to yt-dlp)
            for k in list(merged.keys()):
                if isinstance(k, str) and k.startswith("__fluentytdl_"):
                    merged.pop(k, None)

            # === Phase 2: 断点续传支持 ===
            from ..core.config_manager import config_manager as cfg_mgr
            if cfg_mgr.get("enable_resume", True):
                merged["continuedl"] = True  # 继续下载部分文件

            try:
                yt_dlp_exe = locate_runtime_tool(
                    "yt-dlp.exe",
                    "yt-dlp/yt-dlp.exe",
                    "yt_dlp/yt-dlp.exe",
                )
            except FileNotFoundError as e:
                raise FileNotFoundError(
                    "未找到 yt-dlp.exe。请在设置页指定路径，或将 yt-dlp.exe 放入 _internal/yt-dlp/，或加入 PATH。"
                ) from e

            self._download_via_exe(
                str(yt_dlp_exe), 
                merged, 
                context,
                is_vr_mode=is_vr_mode,
                should_embed_subs=should_embed_subs
            )

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

    def _download_via_exe(
        self, 
        exe: str, 
        merged_opts: dict[str, Any], 
        context: DownloadContext,
        is_vr_mode: bool = False,
        should_embed_subs: bool = False,
    ) -> None:
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
        if should_embed_subs and not has_embed:
            logger.warning("[SubEmbed] ⚠️ 命令中没有 --embed-subs！字幕将不会被嵌入到视频中！")
        
        if is_vr_mode:
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
            raw_bytes = cast(bytes, raw_bytes)
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
        
        # === Feature Pipeline: Post-process ===
        # 执行各模块的后处理逻辑（封面嵌入、字幕合并、VR转码等）
        for feature in self.features:
            feature.on_post_process(context)

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
    
