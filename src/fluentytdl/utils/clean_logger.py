"""
Clean Logger 模块
统一汇聚下载引擎底层的进度回调、状态消息与合并钩子，
产出干净统一的 (状态码, 进度(0-100), 友好信息字符串) 并回调给外层。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class _StreamPhase:
    """单次下载任务中的多流阶段追踪器"""
    
    # 阶段定义: (阶段名, 输出进度范围起始, 输出进度范围宽度)
    VIDEO  = ("video",  0.0,  50.0)   # 0%  -> 50%
    AUDIO  = ("audio",  50.0, 45.0)   # 50% -> 95% 
    POST   = ("post",   95.0, 4.0)    # 95% -> 99%
    SINGLE = ("single", 0.0,  95.0)   # 单流模式: 0% -> 95%
    
    def __init__(self):
        self._phase = None
        self._is_multi_stream = False
        self._stream_count = 0
    
    def detect_phase(self, info_dict: dict) -> tuple:
        """根据 vcodec/acodec 判断当前下载的流类型，返回 (阶段, 是否发生了切换)"""
        vcodec = (info_dict.get("vcodec") or "").lower()
        acodec = (info_dict.get("acodec") or "").lower()
        
        has_video = vcodec and vcodec != "none" and vcodec != "na"
        has_audio = acodec and acodec != "none" and acodec != "na"
        
        if self._phase is None:
            if has_video and not has_audio:
                self._phase = self.VIDEO
                self._is_multi_stream = True
            elif has_audio and not has_video:
                self._phase = self.SINGLE if self._stream_count == 0 else self.AUDIO
            else:
                self._phase = self.SINGLE
            self._stream_count += 1
            return (self._phase, True)
        
        if self._phase == self.VIDEO and has_audio and not has_video:
            self._phase = self.AUDIO
            self._stream_count += 1
            return (self._phase, True)
        
        return (self._phase, False)
    
    def map_progress(self, phase: tuple, raw_pct: float) -> float:
        """将单流内的原始百分比映射到全局进度"""
        if phase is None:
            phase = self.SINGLE
        _, start, width = phase
        return start + (raw_pct / 100.0) * width


class CleanLogger:
    """
    状态收敛日志器。

    接收 yt-dlp 原始数据、进度及日志，进行多模态翻译，并提供单一的 emit_status 回调。
    状态码参考：
    - "queued": 等待中
    - "downloading": 正在下载
    - "processing": 后处理中 (合并、转码等)
    - "finished": 完成
    - "error": 发生错误
    - "paused": 暂停
    """

    def __init__(self, callback: Callable[[str, float, str], None], duration: float = 0.0):
        """
        :param callback: 向外发射的清理后信号方法 (状态码, float进度, 友好状态文案)
        """
        self.callback = callback
        self._current_state = "queued"
        self._current_percent = 0.0
        self._current_msg = "等待下载..."
        self._stream_phase = _StreamPhase()
        self._phase_just_switched = False
        self._duration = duration
    def _emit(self, state: str, percent: float, msg: str) -> None:
        # 进度不后退规则（仅在同一阶段内生效）
        # 阶段切换时允许视觉上的 "重置"（实际是映射后的递增）
        if state in ("downloading", "processing", "finished"):
            if percent < self._current_percent and percent != 0.0:
                if not getattr(self, "_phase_just_switched", False):
                    percent = self._current_percent
        self._phase_just_switched = False

        self._current_state = state
        self._current_percent = percent
        self._current_msg = msg
        self.callback(state, percent, msg)

    def force_update(self, state: str, percent: float, msg: str) -> None:
        """人工强制刷新指定状态"""
        self._emit(state, percent, msg)

    def handle_status(self, raw_status_msg: str) -> None:
        """处理一般性的 status 消息 (通常来自 FFmpeg 等后处理步骤、或者字幕转换)"""
        if self._current_state in ("completed", "error", "paused", "cancelled"):
            return

        msg = raw_status_msg.strip()

        if "Deleting original file" in msg:
            return

        # 拦截前置准备动作 (Parsing Phase)
        if msg.startswith("[youtube] Extracting URL"):
            self._emit("parsing", 0, "🔍 正在解析目标地址...")
            return
        elif msg.startswith("[info]"):
            self._emit("parsing", 0, "📡 正在获取流媒体元数据...")
            return
        elif msg.startswith("[hlsnative]"):
            self._emit("parsing", 0, "🧩 正在组装 m3u8 碎片地图...")
            return

        # 翻译并判断是否为后处理阶段
        processed_msg = ""
        # 英文日志到中文的翻译
        if "Merging formats into" in msg or "[Merger]" in msg:
            processed_msg = "📦 正在无损合并音视频 (FFmpeg)..."
        elif "[ExtractAudio]" in msg:
            processed_msg = "🎵 正在提取独立音频流..."
        elif "Writing video subtitles to" in msg:
            processed_msg = "📝 正在下载字幕..."
        elif "[FFmpegSubtitlesConvertor]" in msg:
            processed_msg = "📝 正在转换字幕格式..."
        elif "Embedding subtitles in" in msg:
            processed_msg = "📝 正在内嵌字幕轨道..."
        elif "Writing metadata to" in msg or "[MetadataParser]" in msg:
            processed_msg = "🏷️ 正在写入视频元数据 (标题/作者)..."
        elif "ThumbnailsConvertor" in msg:
            processed_msg = "🖼️ 正在转换视频封面图..."
        elif "EmbedThumbnail" in msg:
            processed_msg = "🖼️ 正在嵌入视频封面图..."
        elif "Writing video thumbnail" in msg:
            processed_msg = "🖼️ 正在下载视频封面图..."

        if processed_msg:
            self._emit("processing", self._current_percent, processed_msg)

    def handle_progress(self, progress_data: dict[str, Any]) -> None:
        """处理 yt-dlp 的原生 progress 回调 (来自 dict)"""
        if self._current_state in ("completed", "error", "paused", "cancelled"):
            return

        status = progress_data.get("status", "downloading")

        if status == "ffmpeg_progress":
            time_sec = progress_data.get("time_sec", 0.0)
            speed = progress_data.get("speed", "1x")
            
            if self._duration > 0:
                raw_pct = (time_sec / self._duration) * 100.0
                raw_pct = min(100.0, max(0.0, raw_pct))
            else:
                raw_pct = 50.0  # unknown duration
                
            pct = self._stream_phase.map_progress(_StreamPhase.POST, raw_pct)
            pct = round(pct, 1)
            msg = f"🔄 FFmpeg 转码中 {raw_pct:.1f}% | 速度: {speed}..."
            self._emit("processing", pct, msg)
            return

        if status == "postprocess":  # 来自 FLUENTYTDL|postprocess| 钩子
            pp_name = progress_data.get("postprocessor", "Unknown")
            pp_status = progress_data.get("pp_status", "")  # started/finished

            if pp_status == "started":
                if pp_name == "Merger":
                    msg = "📦 正在无损合并音视频 (FFmpeg)..."
                elif pp_name == "EmbedSubtitle":
                    msg = "📝 正在内嵌字幕轨道..."
                elif pp_name in ("MetadataParser", "FFmpegMetadata"):
                    msg = "🏷️ 正在写入视频元数据 (标题/作者)..."
                elif pp_name == "ThumbnailsConvertor":
                    msg = "🖼️ 正在转换视频封面图..."
                elif pp_name == "EmbedThumbnail":
                    msg = "🖼️ 正在嵌入视频封面图..."
                elif pp_name == "MoveFiles":
                    msg = "🚚 正在移动文件..."
                elif pp_name == "SponsorBlock":
                    msg = "⏭️ 正在标记/跳过赞助片段..."
                else:
                    msg = f"⚙️ 正在执行后期处理 ({pp_name})..."
                self._emit("processing", self._current_percent, msg)
            return

        dl_bytes = progress_data.get("downloaded_bytes") or 0
        tot_bytes = (
            progress_data.get("total_bytes") or progress_data.get("total_bytes_estimate") or 0
        )
        speed = progress_data.get("speed") or 0
        eta = progress_data.get("eta") or 0
        filename = progress_data.get("filename", "")

        pct = 0.0
        if tot_bytes > 0:
            pct = (dl_bytes / tot_bytes) * 100.0
        elif dl_bytes > 0:
            # 未知总大小时：对数增长曲线，缓慢逼近 90% 但永远不会到达
            # 公式: pct = 90 * (1 - 1/(1 + dl_bytes/10MB))
            # 效果: 10MB->45%, 50MB->81%, 100MB->86%, 500MB->89%
            pct = 90.0 * (1.0 - 1.0 / (1.0 + dl_bytes / (10 * 1024 * 1024)))

        pct = round(pct, 1)

        if status == "downloading":
            # 💡 流类型识别：优先按文件名后缀判断字幕/封面，
            # 因为字幕下载时 info_dict 的 vcodec/acodec 仍是主视频的值，不可靠。
            stream_type = "📦 数据流"
            info = progress_data.get("info_dict", {})
            vcodec = info.get("vcodec", "") if info else ""
            acodec = info.get("acodec", "") if info else ""

            # 1. 文件名后缀优先（最准确）
            if filename:
                lower_name = filename.lower()
                if lower_name.endswith((".vtt", ".srt", ".ass", ".ssa", ".sub", ".lrc")):
                    stream_type = "📝 字幕"
                elif lower_name.endswith((".jpg", ".jpeg", ".png", ".webp")):
                    stream_type = "🖼️ 封面"
                elif lower_name.endswith((".m4a", ".mp3", ".aac", ".ogg", ".wav", ".opus")):
                    stream_type = "🎵 音频流"
                elif lower_name.endswith((".mp4", ".webm", ".mkv", ".flv", ".mov")):
                    stream_type = "🎬 视频流"

            # 2. 文件名无法判断时，回退到 codec 判断
            if stream_type == "📦 数据流":
                if vcodec and vcodec.lower() != "none":
                    stream_type = "🎬 视频流"
                elif acodec and acodec.lower() != "none":
                    stream_type = "🎵 音频流"

            # ── 多流阶段感知 ──
            if info:
                phase, switched = self._stream_phase.detect_phase(info)
                if switched:
                    self._phase_just_switched = True
                pct = self._stream_phase.map_progress(phase, pct)
                pct = round(pct, 1)

            speed_str = self._format_bytes(speed) + "/s"
            downloaded_str = self._format_bytes(dl_bytes)
            total_str = self._format_bytes(tot_bytes) if tot_bytes > 0 else "?"
            eta_str = self._format_time(eta)

            detail_text = (
                f"{stream_type} | ⬇️ {speed_str} | {downloaded_str}/{total_str} | 剩余: {eta_str}"
            )

            self._emit("downloading", pct, detail_text)

        elif status == "finished":
            # [download] 标明 finish，但后续可能有 [ffmpeg] 处理
            self._emit("processing", 99.0, "下载流完毕，等待后续合并与处理...")

    def _format_bytes(self, bytes_val: float) -> str:
        if not bytes_val:
            return "0.00B"
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_val < 1024.0:
                return f"{bytes_val:.2f}{unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.2f}TB"

    def _format_time(self, seconds: int) -> str:
        if not seconds:
            return "--:--"
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}" if h else f"{int(m):02d}:{int(s):02d}"

