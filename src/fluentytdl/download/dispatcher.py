"""
下载调度器

负责 AUTO 模式路由和工具/协议兼容性判断。
调度器是无状态的决策入口，输入模式+上下文，输出具体策略。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from ..utils.paths import locate_runtime_tool
from .network_probe import network_probe
from .strategy import (
    HARSH_STRATEGY,
    NATIVE_FALLBACK_STRATEGY,
    SPEED_STRATEGY,
    STABLE_STRATEGY,
    DownloadMode,
    DownloadStrategy,
    get_fallback,
)


# ── 常量 ──────────────────────────────────────────────────

# ── 常量 ──────────────────────────────────────────────────

# AUTO 模式网络阈值 (3-Tier)
_LATENCY_EXCELLENT: float = 150.0
_LATENCY_GOOD: float = 350.0

_LOSS_TOLERANCE_EXCELLENT: float = 0.0
_LOSS_TOLERANCE_GOOD: float = 0.05

# 熔断机制
_CIRCUIT_BREAKER_WINDOW: float = 300.0  # 5分钟窗口
_FAILURE_RATE_THRESHOLD: float = 0.3    # 30% 失败率触发熔断
_MIN_SAMPLES_FOR_CIRCUIT: int = 5       # 至少需要 5 个样本才计算熔断

# 拥塞控制
_CONGESTION_TASK_COUNT: int = 2         # 运行任务 > 2 时，避免使用激进模式


# ── 辅助函数 ──────────────────────────────────────────────




def _requires_native_pipeline(ydl_opts: dict[str, Any]) -> bool:
    """判断当前任务是否必须走 yt-dlp 原生管线（aria2c 无法处理）。

    以下场景不走 aria2c：
    - 纯音频提取 (extract_audio / FFmpegExtractAudio)
    - muxed 单流格式（不需要合并）
    """
    # 纯音频提取
    if ydl_opts.get("extract_audio"):
        return True

    # 检查 postprocessors 中的 FFmpegExtractAudio
    pps = ydl_opts.get("postprocessors")
    if isinstance(pps, list):
        for pp in pps:
            if isinstance(pp, dict) and pp.get("key") == "FFmpegExtractAudio":
                return True

    # 格式字符串中没有 "+" → 可能是整合流，不需要 aria2c 分离下载
    fmt = ydl_opts.get("format", "")
    if isinstance(fmt, str) and "+" not in fmt and fmt not in ("", "bestvideo+bestaudio", "bv*+ba"):
        # 单个 format_id ← 可能是 muxed 流
        # 但也可能是 "bestvideo" 等简写，所以只排除纯数字 ID
        if fmt.isdigit():
            return True

    return False


# ── 调度器 ────────────────────────────────────────────────

class DownloadDispatcher:
    """下载模式路由决策器。

    Usage::

        dispatcher = DownloadDispatcher()
        strategy = dispatcher.resolve(DownloadMode.AUTO, ydl_opts, running_tasks=2)
    """

    def __init__(self) -> None:
        from collections import deque
        # 存储 (timestamp, success)
        self._history: deque[tuple[float, bool]] = deque(maxlen=50)

    def report_result(self, success: bool) -> None:
        """上报一次下载结果（成功/失败），用于熔断机制分析。"""
        import time
        self._history.append((time.time(), success))

    def _check_circuit_breaker(self) -> bool:
        """检查是否触发熔断（近期失败率过高）。
        
        Returns:
            True 表示触发熔断（应该降级），False 表示正常。
        """
        import time
        now = time.time()
        
        # 过滤出窗口内的样本
        recent = [
            success 
            for ts, success in self._history 
            if now - ts <= _CIRCUIT_BREAKER_WINDOW
        ]
        
        if len(recent) < _MIN_SAMPLES_FOR_CIRCUIT:
            return False
            
        fail_count = recent.count(False)
        fail_rate = fail_count / len(recent)
        
        if fail_rate > _FAILURE_RATE_THRESHOLD:
            logger.warning(
                f"[Dispatcher] 触发熔断: 最近 {len(recent)} 次任务失败率 {fail_rate:.1%} (> {_FAILURE_RATE_THRESHOLD:.0%})"
            )
            return True
            
        return False

    def resolve(
        self,
        requested: DownloadMode,
        ydl_opts: dict[str, Any],
        *,
        running_tasks: int = 0,
    ) -> DownloadStrategy:
        """将用户请求的模式解析为具体策略。

        Args:
            requested: 用户选择的下载模式。
            ydl_opts: 当前任务的 yt-dlp 选项。
            running_tasks: 当前正在运行的下载任务数。

        Returns:
            最终确定的下载策略。
        """
        # Step 1: 强制 native 场景（纯音频、muxed 单流等）
        if _requires_native_pipeline(ydl_opts):
            # 虽然大多现在都是 Native，但保留这个逻辑可以用来做特定降级或者参数调整
            # 目前都指向 STABLE_STRATEGY (NATIVE_FALLBACK_STRATEGY)
            logger.info("[Dispatcher] 任务需要 native 管线 (音频提取/单流)")
            return NATIVE_FALLBACK_STRATEGY

        # Step 2: HARSH 模式直接返回
        if requested == DownloadMode.HARSH:
            logger.info("[Dispatcher] 用户选择恶劣模式")
            return HARSH_STRATEGY

        # Step 3: AUTO 模式 — 网络探测
        if requested == DownloadMode.AUTO:
            return self._auto_detect(ydl_opts, running_tasks=running_tasks)

        # Step 4: SPEED / STABLE 模式
        if requested in (DownloadMode.SPEED, DownloadMode.STABLE):
            strategy = SPEED_STRATEGY if requested == DownloadMode.SPEED else STABLE_STRATEGY
            logger.info("[Dispatcher] 使用 {} 模式", strategy.label)
            return strategy

        # Fallback: 不应到达
        logger.warning("[Dispatcher] 未知模式 {}，回退原生", requested)
        return NATIVE_FALLBACK_STRATEGY

    def _auto_detect(
        self,
        ydl_opts: dict[str, Any],
        *,
        running_tasks: int = 0,
    ) -> DownloadStrategy:
        """AUTO 模式智能决策逻辑。
        
        优先级:
        1. 熔断机制 (最近失败太多 -> STABLE/HARSH)
        2. 拥塞控制 (并发任务多 -> STABLE)
        3. 网络质量 (Excellent -> SPEED, Good -> STABLE, Poor -> HARSH)
        """
        # 1. 熔断机制 & 拥塞控制
        is_circuit_broken = self._check_circuit_breaker()
        is_congested = running_tasks > _CONGESTION_TASK_COUNT
        
        downgrade_reason = []
        if is_circuit_broken:
            downgrade_reason.append("熔断触发")
        if is_congested:
            downgrade_reason.append(f"拥塞({running_tasks}任务)")
            
        force_stable_or_lower = bool(downgrade_reason)

        # 2. 网络探测
        try:
            status = network_probe.probe()
            
            # Case A: 网络不可达/极差 -> HARSH
            if not status.is_reachable:
                logger.warning("[Dispatcher][AUTO] YouTube 不可达 → HARSH")
                return HARSH_STRATEGY

            latency = status.latency_ms or 999
            loss = status.packet_loss
            
            # Case B: 网络较差 (延迟大 或 丢包高) -> HARSH
            if latency > _LATENCY_GOOD or loss > _LOSS_TOLERANCE_GOOD:
                logger.info(
                    f"[Dispatcher][AUTO] 网络差 (延迟={latency:.0f}ms 丢包={loss:.0%}) → HARSH"
                )
                return HARSH_STRATEGY
            
            # Case C: 触发了熔断或拥塞 -> STABLE (即使网络好，也不敢太激进)
            if force_stable_or_lower:
                reason_str = ", ".join(downgrade_reason)
                logger.info(f"[Dispatcher][AUTO] {reason_str} → STABLE")
                return STABLE_STRATEGY
                
            # Case D: 网络极佳 -> SPEED
            if latency <= _LATENCY_EXCELLENT and loss <= _LOSS_TOLERANCE_EXCELLENT:
                logger.info(
                    f"[Dispatcher][AUTO] 网络极佳 (延迟={latency:.0f}ms 丢包={loss:.0%}) → SPEED"
                )
                return SPEED_STRATEGY
                
            # Case E: 网络良好 (但未达极佳) -> STABLE
            logger.info(
                f"[Dispatcher][AUTO] 网络良好 (延迟={latency:.0f}ms 丢包={loss:.0%}) → STABLE"
            )
            return STABLE_STRATEGY

        except Exception as exc:
            logger.warning(f"[Dispatcher][AUTO] 网络探测异常: {exc} → HARSH")
            return HARSH_STRATEGY

    def get_runtime_fallback(self, current: DownloadStrategy) -> DownloadStrategy | None:
        """运行时降级（仅用于 aria2c 下载失败后的自动降级）。

        降级链: SPEED → STABLE → HARSH → None
        """
        return get_fallback(current.mode)


# 全局单例
download_dispatcher = DownloadDispatcher()
