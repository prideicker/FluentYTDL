from __future__ import annotations

from PySide6.QtCore import QObject, QUrl, Signal, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkProxy,
    QNetworkProxyFactory,
    QNetworkReply,
    QNetworkRequest,
)

from ..core.config_manager import config_manager
from .logger import logger


class ImageLoader(QObject):
    """通用异步图片加载器（增强版：代理修正 + 详细日志 + WebP→JPG 兜底）。"""

    loaded = Signal(QPixmap)
    loaded_with_url = Signal(str, QPixmap)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self._apply_proxy()

    def _apply_proxy(self) -> None:
        """从配置中读取代理并应用到 NetworkManager。"""

        proxy_mode = str(config_manager.get("proxy_mode") or "off").lower().strip()
        proxy_url_str = str(config_manager.get("proxy_url", "") or "").strip()

        if proxy_mode == "off":
            # 强制不走系统代理
            try:
                QNetworkProxyFactory.setUseSystemConfiguration(False)
            except Exception:
                pass
            self.manager.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
            return

        if proxy_mode == "system":
            # 跟随系统代理
            try:
                QNetworkProxyFactory.setUseSystemConfiguration(True)
            except Exception:
                pass
            return

        # manual http/socks5
        if not proxy_url_str:
            logger.warning("[ImageLoader] 代理模式=手动，但 URL 为空")
            return

        # [关键修正] 确保 URL 有 scheme，否则 QUrl 解析不出 host/port
        lower = proxy_url_str.lower()
        if not (lower.startswith("http://") or lower.startswith("https://") or lower.startswith("socks5://")):
            scheme = "socks5" if proxy_mode == "socks5" else "http"
            proxy_url_str = f"{scheme}://" + proxy_url_str
            lower = proxy_url_str.lower()

        url = QUrl(proxy_url_str)
        logger.info(
            "[ImageLoader] 配置代理: {}:{} (原始: {})",
            url.host(),
            url.port(),
            proxy_url_str,
        )

        if not url.isValid() or not url.host() or url.port() <= 0:
            logger.error("[ImageLoader] 代理 URL 无效: {}", proxy_url_str)
            return

        proxy_type = QNetworkProxy.ProxyType.HttpProxy
        if proxy_mode == "socks5" or lower.startswith("socks5://") or "socks5" in lower:
            proxy_type = QNetworkProxy.ProxyType.Socks5Proxy

        proxy = QNetworkProxy(proxy_type, url.host(), url.port())
        self.manager.setProxy(proxy)

    def load(
        self,
        url_str: str,
        target_size: tuple[int, int] | None = None,
        radius: int = 0,
    ) -> None:
        """开始加载图片。"""

        url_str = str(url_str or "").strip()
        if not url_str:
            logger.debug("[ImageLoader] URL 为空，跳过加载")
            return

        url_str = self._force_youtube_webp_to_jpg(url_str)
        logger.debug("[ImageLoader] 开始下载图片: {}", url_str)

        request = QNetworkRequest(QUrl(url_str))
        request.setRawHeader(
            b"User-Agent",
            (
                b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                b"AppleWebKit/537.36 (KHTML, like Gecko) "
                b"Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        reply = self.manager.get(request)

        # 记录 SSL 错误（不自动忽略）
        try:
            reply.sslErrors.connect(
                lambda errors: logger.error(
                    "[ImageLoader] SSL errors ({}): {}",
                    url_str,
                    ", ".join(e.errorString() for e in errors),
                )
            )
        except Exception:
            pass

        reply.finished.connect(
            lambda: self._on_finished(reply, target_size, radius, url_str)
        )

    def _on_finished(
        self,
        reply,
        target_size: tuple[int, int] | None,
        radius: int,
        original_url: str,
    ) -> None:
        try:
            # 1. 检查网络错误
            err = reply.error()
            try:
                err_code: object = int(err)  # type: ignore[arg-type]
            except Exception:
                err_code = getattr(err, "value", str(err))

            # 注意：PySide6 的枚举对象在 bool 上恒为 True，不能用 if err: 判断
            if err != QNetworkReply.NetworkError.NoError:
                try:
                    http_status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                except Exception:
                    http_status = None
                logger.error(
                    "[ImageLoader] 网络错误 ({}): {} (Code: {}, HTTP: {})",
                    original_url,
                    reply.errorString(),
                    err_code,
                    http_status,
                )
                return

            # 2. 检查数据有效性
            data = reply.readAll()
            if data.size() == 0:
                logger.error("[ImageLoader] 下载数据为空: {}", original_url)
                return

            # 3. 尝试解码
            pixmap = QPixmap()
            if not pixmap.loadFromData(data):
                logger.error(
                    "[ImageLoader] 图片解码失败 (数据大小: {} bytes). 可能是不支持的格式或非图片数据。",
                    data.size(),
                )
                try:
                    logger.debug("[ImageLoader] 数据头: {}", bytes(data[:20]))
                except Exception:
                    pass
                return

            logger.debug(
                "[ImageLoader] 图片加载成功: {} (尺寸: {}x{})",
                original_url,
                pixmap.width(),
                pixmap.height(),
            )

            # 4. 后处理 (缩放/圆角)
            if target_size:
                w, h = target_size
                pixmap = pixmap.scaled(
                    w,
                    h,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )

            if radius > 0:
                pixmap = self._round_corners(pixmap, radius)

            self.loaded.emit(pixmap)
            self.loaded_with_url.emit(str(original_url), pixmap)
        finally:
            reply.deleteLater()

    @staticmethod
    def _round_corners(source: QPixmap, radius: int) -> QPixmap:
        if source.isNull():
            return source
        target = QPixmap(source.size())
        target.fill(Qt.GlobalColor.transparent)
        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, source.width(), source.height(), radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, source)
        painter.end()
        return target

    @staticmethod
    def _force_youtube_webp_to_jpg(url_str: str) -> str:
        # YouTube 缩略图常见：
        # https://i.ytimg.com/vi_webp/VIDEO_ID/maxresdefault.webp
        # -> https://i.ytimg.com/vi/VIDEO_ID/maxresdefault.jpg
        if "/vi_webp/" in url_str:
            url_str = url_str.replace("/vi_webp/", "/vi/")
        if url_str.endswith(".webp"):
            url_str = url_str[:-5] + ".jpg"
        return url_str
