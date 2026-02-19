"""
网络探测模块

通过 TCP socket 连接测量到 YouTube 服务器的延迟和连通性。
用于 AUTO 模式的网络状况判断（不依赖 ICMP / ping）。
"""

from __future__ import annotations

import socket
import statistics
import time
from dataclasses import dataclass
from typing import ClassVar

from loguru import logger


@dataclass
class NetworkStatus:
    """网络探测结果。"""

    latency_ms: float | None  # RTT 中位数 (ms)，None 表示不可达
    packet_loss: float         # 丢包率 0.0 ~ 1.0
    is_reachable: bool         # 至少有一次探测成功
    timestamp: float           # time.monotonic()


class NetworkProbe:
    """TCP socket 网络探测器（无需管理员权限，不依赖 ICMP）。"""

    DEFAULT_TARGET: ClassVar[str] = "www.youtube.com"
    DEFAULT_PORT: ClassVar[int] = 443
    DEFAULT_TIMEOUT: ClassVar[float] = 1.0
    DEFAULT_ATTEMPTS: ClassVar[int] = 3
    CACHE_TTL: ClassVar[float] = 30.0  # 秒

    def __init__(self) -> None:
        self._cached: NetworkStatus | None = None

    def probe(
        self,
        target: str = DEFAULT_TARGET,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        attempts: int = DEFAULT_ATTEMPTS,
    ) -> NetworkStatus:
        """执行网络探测，带 TTL 缓存。

        对 ``target:port`` 发起 ``attempts`` 次 TCP 连接。

        Returns:
            NetworkStatus: 包含延迟中位数、丢包率、可达性。
        """
        # 缓存命中
        if (
            self._cached is not None
            and (time.monotonic() - self._cached.timestamp) < self.CACHE_TTL
        ):
            return self._cached

        latencies: list[float] = []
        failures = 0

        for i in range(attempts):
            try:
                t0 = time.perf_counter()
                with socket.create_connection((target, port), timeout=timeout):
                    elapsed = (time.perf_counter() - t0) * 1000  # ms
                    latencies.append(elapsed)
            except (OSError, socket.timeout):
                failures += 1
            except Exception:
                failures += 1

        packet_loss = failures / attempts if attempts > 0 else 1.0
        is_reachable = len(latencies) > 0
        median_latency = statistics.median(latencies) if latencies else None

        status = NetworkStatus(
            latency_ms=median_latency,
            packet_loss=packet_loss,
            is_reachable=is_reachable,
            timestamp=time.monotonic(),
        )

        logger.debug(
            "[NetworkProbe] target={} latency={:.0f}ms loss={:.0%} reachable={}",
            target,
            median_latency or 0,
            packet_loss,
            is_reachable,
        )

        self._cached = status
        return status

    def invalidate_cache(self) -> None:
        """清除缓存，强制下次重新探测。"""
        self._cached = None


# 全局单例
network_probe = NetworkProbe()
