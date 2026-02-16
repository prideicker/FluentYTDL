from __future__ import annotations

import os
import re
import subprocess
from typing import TYPE_CHECKING, Any

from ..core.config_manager import config_manager
from ..core.hardware_manager import hardware_manager
from ..processing.thumbnail_embed import can_embed_thumbnail, get_unsupported_formats_warning
from ..processing.thumbnail_embedder import thumbnail_embedder
from ..utils.logger import logger
from ..utils.spatialmedia import metadata_utils

if TYPE_CHECKING:
    from .workers import DownloadWorker


class DownloadContext:
    """下载上下文，用于在 Feature 和 Worker 之间传递状态"""
    def __init__(self, worker: DownloadWorker, opts: dict[str, Any]):
        self.worker = worker
        self.opts = opts
        self.url = worker.url
        
    @property
    def output_path(self) -> str | None:
        return self.worker.output_path
        
    @output_path.setter
    def output_path(self, value: str | None):
        self.worker.output_path = value
        
    @property
    def dest_paths(self) -> set[str]:
        return self.worker.dest_paths
        
    def emit_status(self, msg: str):
        self.worker.status_msg.emit(msg)
        
    def emit_warning(self, msg: str):
        logger.warning(msg)
        self.worker.status_msg.emit(f"⚠️ {msg}")

    def emit_thumbnail_warning(self, msg: str):
        self.worker.thumbnail_embed_warning.emit(msg)

    def find_final_merged_file(self) -> str | None:
        """查找最终合并的输出文件"""
        output_path = self.output_path
        if not output_path:
            return None
        
        # 检查当前 output_path 是否是分片文件
        match = re.search(r'^(.+)\.[fF]\d+\.(\w+)$', output_path)
        if not match:
            if os.path.exists(output_path):
                return output_path
            return None
        
        base_name = match.group(1)
        possible_extensions = [".mp4", ".mkv", ".webm", ".avi", ".mov"]
        for ext in possible_extensions:
            merged_path = base_name + ext
            if os.path.exists(merged_path):
                return merged_path
        
        # 检查 dest_paths
        for dest_path in self.dest_paths:
            if not re.search(r'\.[fF]\d+\.\w+$', dest_path):
                if os.path.exists(dest_path):
                    return dest_path
        return None

    def find_thumbnail_file(self, video_path: str) -> str | None:
        """查找视频文件对应的封面文件"""
        base_path = os.path.splitext(video_path)[0]
        exts = [".jpg", ".jpeg", ".webp", ".png"]
        
        for ext in exts:
            candidate = base_path + ext
            if os.path.exists(candidate):
                return candidate
            
        match = re.match(r'^(.+)\.[fF]\d+$', base_path)
        if match:
            clean_base = match.group(1)
            for ext in exts:
                candidate = clean_base + ext
                if os.path.exists(candidate):
                    return candidate
        return None


class DownloadFeature:
    """下载功能模块基类"""
    
    def configure(self, ydl_opts: dict[str, Any]) -> None:
        pass
        
    def on_download_start(self, context: DownloadContext) -> None:
        pass
        
    def on_post_process(self, context: DownloadContext) -> None:
        pass


class SponsorBlockFeature(DownloadFeature):
    def configure(self, ydl_opts: dict[str, Any]) -> None:
        if not config_manager.get("sponsorblock_enabled", False):
            return
        categories = config_manager.get("sponsorblock_categories", ["sponsor", "selfpromo", "interaction"])
        action = config_manager.get("sponsorblock_action", "remove")
        if not categories:
            return
        if action == "remove":
            ydl_opts["sponsorblock_remove"] = categories
        elif action == "mark":
            ydl_opts["sponsorblock_mark"] = categories
        logger.info(f"[SponsorBlock] Enabled: action={action}, categories={categories}")


class MetadataFeature(DownloadFeature):
    def configure(self, ydl_opts: dict[str, Any]) -> None:
        if config_manager.get("embed_metadata", True):
            pps = ydl_opts.setdefault("postprocessors", [])
            if not any(p.get("key") == "FFmpegMetadata" for p in pps):
                pps.append({"key": "FFmpegMetadata"})
            logger.info("[Metadata] Enabled")


class SubtitleFeature(DownloadFeature):
    def on_download_start(self, context: DownloadContext) -> None:
        opts = context.opts
        if opts.get("embedsubtitles"):
            fmt = (opts.get("merge_output_format") or "").lower()
            if fmt == "webm":
                opts["merge_output_format"] = "mkv"
                logger.info("[SubEmbed] WebM → MKV")
            elif not fmt:
                opts["merge_output_format"] = "mkv"
                logger.info("[SubEmbed] 未指定 → MKV")
        else:
            logger.warning("[SubEmbed] embedsubtitles=False")

    def on_post_process(self, context: DownloadContext) -> None:
        opts = context.opts
        # 只有在启用了字幕下载时才执行后处理
        if not opts.get("writesubtitles") and not opts.get("writeautomaticsub"):
            return

        from ..processing import subtitle_processor
        
        try:
            result = subtitle_processor.process(
                output_path=context.output_path,
                opts=opts,
                status_callback=lambda msg: context.emit_status(msg)
            )
            if result.success:
                if result.merged_file:
                    context.emit_status("[字幕处理] ✓ 双语字幕已生成")
            else:
                logger.warning("字幕后处理失败: {}", result.message)
            self._cleanup_subtitle_files(context)
        except Exception as e:
            logger.exception("字幕后处理异常: {}", e)

    def _cleanup_subtitle_files(self, context: DownloadContext) -> None:
        opts = context.opts
        if not opts.get("embedsubtitles"):
            return
        if config_manager.get("subtitle_write_separate_file", False):
            return
        
        paths = []
        if context.output_path and os.path.exists(context.output_path):
            paths.append(context.output_path)
        for p in context.dest_paths:
            if os.path.exists(p):
                paths.append(p)
            
        exts = [".srt", ".ass", ".vtt"]
        for path in paths:
            parent = os.path.dirname(path)
            stem = os.path.splitext(os.path.basename(path))[0]
            try:
                if not os.path.exists(parent):
                    continue
                for f in os.listdir(parent):
                    if not f.startswith(stem):
                        continue
                    if os.path.splitext(f)[1].lower() in exts:
                        try:
                            os.remove(os.path.join(parent, f))
                        except Exception:
                            pass
            except Exception:
                pass


class ThumbnailFeature(DownloadFeature):
    def on_post_process(self, context: DownloadContext) -> None:
        if not config_manager.get("embed_thumbnail", True):
            return
        if not context.opts.get("writethumbnail"):
            return
        
        final_output = context.find_final_merged_file()
        if final_output:
            context.output_path = final_output
            
        files = self._locate_files(context)
        if not files:
            return
            
        if not thumbnail_embedder.is_available():
            context.emit_thumbnail_warning("⚠️ 封面嵌入工具不可用")
            return
            
        for v, t in files:
            self._process_single_file(context, v, t)
        self._cleanup_thumbnail_files(context)

    def _process_single_file(self, context: DownloadContext, video_path: str, thumb_path: str):
        ext = os.path.splitext(video_path)[1].lower().lstrip(".")
        if not can_embed_thumbnail(ext):
            w = get_unsupported_formats_warning(ext)
            if w:
                context.emit_thumbnail_warning(w)
            return
        context.emit_status(f"[封面嵌入] 正在处理: {os.path.basename(video_path)}")
        res = thumbnail_embedder.embed_thumbnail(
            video_path, thumb_path,
            progress_callback=lambda msg: context.emit_status(f"[封面嵌入] {msg}")
        )
        if res.success:
            context.emit_status("[封面嵌入] ✓ 成功")
        elif res.skipped:
            context.emit_thumbnail_warning(res.message)
        else:
            context.emit_thumbnail_warning(f"封面嵌入失败: {res.message}")

    def _locate_files(self, context: DownloadContext) -> list[tuple[str, str]]:
        files = []
        paths = set()
        if context.output_path:
            paths.add(context.output_path)
        paths.update(context.dest_paths)
        
        for p in paths:
            if not os.path.exists(p):
                continue
            if re.search(r'\.[fF]\d+\.\w+$', p):
                continue
            t = context.find_thumbnail_file(p)
            if t:
                files.append((p, t))
            
        if not files: # Fallback scan
            output_dir = None
            if context.output_path:
                output_dir = os.path.dirname(context.output_path)
            elif context.dest_paths:
                output_dir = os.path.dirname(next(iter(context.dest_paths)))
            
            if output_dir and os.path.exists(output_dir):
                v_files, t_files = [], []
                v_exts = {'.mp4', '.mkv', '.webm', '.avi', '.mov', '.m4a', '.mp3', '.flac', '.opus'}
                t_exts = {'.jpg', '.jpeg', '.png', '.webp'}
                for f in os.listdir(output_dir):
                    fp = os.path.join(output_dir, f)
                    if not os.path.isfile(fp):
                        continue
                    if re.search(r'\.[fF]\d+\.\w+$', f):
                        continue
                    ext = os.path.splitext(f)[1].lower()
                    if ext in v_exts:
                        v_files.append(fp)
                    elif ext in t_exts:
                        t_files.append(fp)
                
                for v in v_files:
                    vb = os.path.splitext(os.path.basename(v))[0]
                    for t in t_files:
                        if os.path.splitext(os.path.basename(t))[0] == vb:
                            files.append((v, t))
                            context.output_path = v
                            break
        return files

    def _cleanup_thumbnail_files(self, context: DownloadContext) -> None:
        if not context.opts.get("writethumbnail"):
            return
        paths = set()
        if context.output_path and os.path.exists(context.output_path):
            paths.add(context.output_path)
        for p in context.dest_paths:
            if os.path.exists(p):
                paths.add(p)
        exts = [".webp", ".jpg", ".jpeg", ".png"]
        for p in paths:
            b = os.path.splitext(p)[0]
            for e in exts:
                t = b + e
                if os.path.exists(t):
                    try:
                        os.remove(t)
                    except Exception:
                        pass


class VRFeature(DownloadFeature):
    def on_download_start(self, context: DownloadContext) -> None:
        opts = context.opts
        if not opts.get("__fluentytdl_use_android_vr"):
            return
        
        logger.info("🥽 VR 模式: 使用 android_vr 客户端下载")
        opts.pop("__android_vr_format_ids", None)
        
        ext_args = opts.get("extractor_args", {})
        if not isinstance(ext_args, dict):
            ext_args = {}
        if "youtubepot-bgutilhttp" in ext_args:
            ext_args.pop("youtubepot-bgutilhttp", None)
        
        yt_args = ext_args.get("youtube", {})
        if not isinstance(yt_args, dict):
            yt_args = {}
        yt_args["player_client"] = "android_vr"
        ext_args["youtube"] = yt_args
        opts["extractor_args"] = ext_args
        
        if opts.get("cookiefile"):
            opts.pop("cookiefile", None)
        opts.pop("cookiesfrombrowser", None)

    def on_post_process(self, context: DownloadContext) -> None:
        if not context.opts.get("__fluentytdl_use_android_vr"):
            return
        
        opts = context.opts
        proj = str(opts.get("__vr_projection") or "").lower()
        convert = bool(opts.get("__vr_convert_eac") or False)
        auto_convert = config_manager.get("vr_eac_auto_convert", False)
        
        if not (proj and proj != "unknown") and not ((convert or auto_convert) and proj == "eac"):
            if (convert or auto_convert) and proj == "mesh":
                context.emit_warning("Mesh 格式暂不支持转码")
            return

        final_file = context.find_final_merged_file() or context.output_path
        if not final_file or not os.path.exists(final_file):
            logger.warning("[VR] 无法找到最终文件")
            return

        ffmpeg_exe = opts.get("ffmpeg_location") or "ffmpeg"
        if os.path.isdir(ffmpeg_exe):
            ffmpeg_exe = os.path.join(ffmpeg_exe, "ffmpeg.exe")

        needs_convert = (convert or auto_convert) and proj == "eac"
        if needs_convert:
            if not self._check_ffmpeg_v360(ffmpeg_exe):
                context.emit_warning("FFmpeg 不支持 v360")
                needs_convert = False
            
            h = int(opts.get("height") or 0)
            if h == 0:
                h = 2160
            if h > int(config_manager.get("vr_max_resolution", 2160)):
                context.emit_warning(f"跳过 VR 转码: 分辨率过高 ({h}p)")
                needs_convert = False

        if needs_convert:
            context.emit_status("VR 投影转换 (EAC -> Equi)...")
            ext = os.path.splitext(final_file)[1]
            out_conv = os.path.splitext(final_file)[0] + "_equi" + ext
            
            cmd = self._build_cmd(ffmpeg_exe, final_file, out_conv)
            dur = 0.0
            try:
                dur = float(opts.get("duration") or 0)
            except Exception:
                pass
            
            if self._run_ffmpeg(cmd, context, dur):
                if not config_manager.get("vr_keep_source", True):
                    os.remove(final_file)
                    os.rename(out_conv, final_file)
                else:
                    bak = os.path.splitext(final_file)[0] + ".eac" + ext
                    if os.path.exists(bak):
                        os.remove(bak)
                    os.rename(final_file, bak)
                    os.rename(out_conv, final_file)
                proj = "equirectangular"
            else:
                context.emit_warning("VR 转码失败")
                if os.path.exists(out_conv):
                    os.remove(out_conv)

        self._inject_meta(context, final_file, proj, opts)

    def _build_cmd(self, exe, inp, out):
        cmd = [exe, "-y", "-i", inp, "-vf", "v360=eac:e"]
        hw = config_manager.get("vr_hw_accel_mode", "auto")
        encs = hardware_manager.get_gpu_encoders()
        gpu = ""
        if hw in ("gpu", "auto") and encs:
            if "h264_nvenc" in encs:
                gpu = "h264_nvenc"
            elif "h264_qsv" in encs:
                gpu = "h264_qsv"
            elif "h264_amf" in encs:
                gpu = "h264_amf"
        
        if gpu:
            cmd.extend(["-c:v", gpu])
            if gpu == "h264_nvenc":
                cmd.extend(["-preset", "p4", "-cq", "20"])
            elif gpu == "h264_qsv":
                cmd.extend(["-global_quality", "20"])
        else:
            cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"])
            th = hardware_manager.get_optimal_ffmpeg_threads(True)
            if config_manager.get("vr_cpu_priority", "low") == "low":
                th = max(1, th - 1)
            if th > 0:
                cmd.extend(["-threads", str(th)])
            
        cmd.extend(["-c:a", "copy", out])
        return cmd

    def _check_ffmpeg_v360(self, exe):
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            res = subprocess.run([exe, "-filters"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, startupinfo=si, encoding="utf-8", errors="replace", check=False)
            return "v360" in res.stdout
        except Exception:
            return False

    def _run_ffmpeg(self, cmd, ctx, dur):
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, startupinfo=si, encoding="utf-8", errors="replace")
            while True:
                if p.stdout is None:
                    break
                line = p.stdout.readline()
                if not line and p.poll() is not None:
                    break
                if line and "time=" in line:
                    t = line[line.find("time=")+5:].split(" ")[0]
                    ctx.emit_status(f"VR 转换... ({t})")
            return p.returncode == 0
        except Exception:
            return False

    def _inject_meta(self, ctx, f, proj, opts):
        if os.path.splitext(f)[1].lower() not in (".mp4", ".mov"):
            return
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
        
        if not md.stereo_mode and not md.projection:
            return
        
        ctx.emit_status("注入 VR 元数据...")
        tmp = f + ".tmp.mp4"
        try:
            metadata_utils.inject_metadata(f, tmp, md, lambda x: None)
            if os.path.exists(tmp):
                os.remove(f)
                os.rename(tmp, f)
                ctx.emit_status("VR 元数据注入成功")
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
