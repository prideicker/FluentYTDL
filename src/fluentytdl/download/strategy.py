"""
下载策略工厂模块

定义四种下载模式(极速/稳定/恶劣/自动)及其对应的参数配置。
策略对象 (DownloadStrategy) 是不可变的数据容器，由调度器或 UI 选择后注入执行器。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

# ── 下载模式枚举 ──────────────────────────────────────────

class DownloadMode(str, Enum):
    """用户可选的下载模式。"""

    SPEED = "speed"    # 极速: 多线程并发 (Native)
    STABLE = "stable"  # 稳定: 单线程 + 高容错 (Native)
    HARSH = "harsh"    # 恶劣: 激进限流 + 极强容错 (Native)
    AUTO = "auto"      # 自动: 根据网络状况 + 工具可用性自动路由

    @property
    def label(self) -> str:
        return _MODE_LABELS.get(self, self.value)


_MODE_LABELS: dict[DownloadMode, str] = {
    DownloadMode.SPEED: "🚀 极速模式",
    DownloadMode.STABLE: "🛡️ 稳定模式",
    DownloadMode.HARSH: "🧟 恶劣模式",
    DownloadMode.AUTO: "⚡ 自动模式",
}


# ── 下载策略数据类 ────────────────────────────────────────


@dataclass(frozen=True)
class DownloadStrategy:
    """
    不可变的下载策略配置 (Native Only)。
    """

    mode: DownloadMode
    label: str

    # ── yt-dlp native 参数 ──
    concurrent_fragments: int = 1     # -N
    socket_timeout: int = 15
    retries: str | int = 10           # infinite or int
    fragment_retries: str | int = 10
    sleep_interval: int = 0
    max_sleep_interval: int = 0
    force_ipv4: bool = False
    
    # ── IO 优化参数 ──
    buffer_size: str = "1024"         # --buffer-size (e.g. "16M", "1024") (default 1024 bytes in yt-dlp is too small?) No, default is 1024.
    http_chunk_size: str | None = None # --http-chunk-size
    resize_buffer: bool = False       # --resize-buffer
    skip_unavailable_fragments: bool = False # --skip-unavailable-fragments

    # ── 元信息 ──
    risk_level: str = "low"  # low / medium / high

    def apply_to_ydl_opts(self, ydl_opts: dict[str, Any]) -> None:
        """将策略参数注入 ydl_opts。"""
        ydl_opts["socket_timeout"] = self.socket_timeout
        ydl_opts["retries"] = self.retries
        ydl_opts["fragment_retries"] = self.fragment_retries

        if self.concurrent_fragments > 1:
            ydl_opts["concurrent_fragment_downloads"] = self.concurrent_fragments

        if self.sleep_interval > 0:
            ydl_opts["sleep_interval"] = self.sleep_interval
        if self.max_sleep_interval > 0:
            ydl_opts["max_sleep_interval"] = self.max_sleep_interval

        if self.force_ipv4:
            ydl_opts["source_address"] = "0.0.0.0"

        # IO Optimization
        if self.buffer_size:
            ydl_opts["buffersize"] = self.buffer_size
        if self.http_chunk_size:
            ydl_opts["http_chunk_size"] = self.http_chunk_size
        if self.resize_buffer:
            ydl_opts["resize_buffer"] = True
        
        if self.skip_unavailable_fragments:
            ydl_opts["skip_unavailable_fragments"] = True


# ── 预定义策略 ────────────────────────────────────────────

# A. 极速模式: 火力全开 (Native)
SPEED_STRATEGY = DownloadStrategy(
    mode=DownloadMode.SPEED,
    label="🚀 极速",
    concurrent_fragments=16,          # Max concurrency
    socket_timeout=30,
    retries=10,
    fragment_retries=10,
    buffer_size="16M",                # Large buffer
    http_chunk_size="10M",            # Large chunks
    resize_buffer=False,
    risk_level="high",
)

# B. 稳定模式: 恶劣环境 (Native)
STABLE_STRATEGY = DownloadStrategy(
    mode=DownloadMode.STABLE,
    label="🛡️ 稳定",
    concurrent_fragments=1,           # Single thread
    socket_timeout=10,                # Fast fail
    retries="inf",                    # Infinite retries
    fragment_retries="inf",
    buffer_size="1M",                 # Conservative buffer
    http_chunk_size=None,             # Default chunk size
    resize_buffer=True,
    skip_unavailable_fragments=True,  # Skip bad fragments in harsh conditions
    force_ipv4=True,                  # Prefer IPv4
    risk_level="low",
)

# C. 恶劣模式: (保留作为极端的稳定模式，或者合并到稳定模式?)
# 现在的 STABLE 已经很 Harsh 了。原来的 HARSH 是单线程+高重试。
# 新的 STABLE 基本涵盖了 HARSH 的特性。
# 我们可以保留 HARSH 作为 "Paranoid Stable" 或者 "Legacy Stable"？
# 用户计划中提到了 "稳定模式 - 恶劣环境"。
# 我们可以把原来的 HARSH 稍微改一下，或者直接复用 STABLE 但参数更极端。
# 让我们把 HARSH 设置为更极端的单线程模式 (Same as STABLE essentially)
HARSH_STRATEGY = DownloadStrategy(
    mode=DownloadMode.HARSH,
    label="🧟 恶劣",
    concurrent_fragments=1,
    socket_timeout=5,                 # Extremely fast fail
    retries="inf",
    fragment_retries="inf",
    sleep_interval=2,                 # Active throttling
    max_sleep_interval=5,
    buffer_size="512K",
    force_ipv4=True,
    risk_level="low",
)

# 降级策略
NATIVE_FALLBACK_STRATEGY = STABLE_STRATEGY


# ── 策略查询 ──────────────────────────────────────────────

STRATEGIES: dict[DownloadMode, DownloadStrategy] = {
    DownloadMode.SPEED: SPEED_STRATEGY,
    DownloadMode.STABLE: STABLE_STRATEGY,
    DownloadMode.HARSH: HARSH_STRATEGY,
}


def get_strategy(mode: DownloadMode) -> DownloadStrategy:
    """获取指定模式的策略。AUTO 模式不在此处解析，由调度器处理。"""
    if mode == DownloadMode.AUTO:
        raise ValueError("AUTO 模式需由 DownloadDispatcher.resolve() 解析")
    return STRATEGIES[mode]


def get_fallback(mode: DownloadMode) -> DownloadStrategy | None:
    """获取降级策略。仅用于运行时错误降级链。

    SPEED → STABLE → HARSH → None
    """
    _FALLBACK_CHAIN: dict[DownloadMode, DownloadMode] = {
        DownloadMode.SPEED: DownloadMode.STABLE,
        DownloadMode.STABLE: DownloadMode.HARSH,
    }
    next_mode = _FALLBACK_CHAIN.get(mode)
    if next_mode is None:
        return None
    return STRATEGIES[next_mode]
