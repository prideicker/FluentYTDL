"""
FluentYTDL 统一组件更新协调器

协调 app-core 和 bin/ 工具的版本检查与更新。
通过 GitHub Release 的 update-manifest.json 统一管理所有组件版本。

版本通道:
  - v- (stable): 检查 /releases/latest，只接收稳定版
  - pre- (pre-release): 检查 /releases，可接收 pre 和 v 更新
  - beta-: 锁定更新，弹窗提示
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal

from ..utils.logger import logger
from ..utils.paths import frozen_app_dir, is_frozen
from .config_manager import config_manager

# ─── 常量 ────────────────────────────────────────────────

REPO_OWNER = "SakuraForgot"
REPO_NAME = "FluentYTDL"
GITHUB_API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"

MANIFEST_FILENAME = "update-manifest.json"

# ─── 版本比较 ────────────────────────────────────────────


def _parse_version(ver: str) -> tuple[int, ...]:
    """将 '3.0.0' 或 'v3.0.0' 解析为可比较的整数元组"""
    clean = re.sub(r"^(v-?|pre-|beta-)", "", str(ver).strip())
    clean = clean.split("-")[0]
    parts: list[int] = []
    for p in clean.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _parse_version_prefix(full_version: str) -> tuple[str, str]:
    """解析版本前缀和数字部分。
    "v-3.0.18" → ("v-", "3.0.18")
    "pre-3.0.18" → ("pre-", "3.0.18")
    "beta-0.0.5" → ("beta-", "0.0.5")
    """
    for pfx in ("v-", "pre-", "beta-"):
        if full_version.startswith(pfx):
            return pfx, full_version[len(pfx):]
    return "v-", full_version


def _get_update_channel() -> str:
    """根据当前版本前缀确定更新通道。"""
    from fluentytdl import __version__

    if __version__.startswith("beta-"):
        return "beta"
    elif __version__.startswith("pre-"):
        return "pre"
    return "stable"


def _get_proxies() -> dict[str, str]:
    """从 config 构建代理字典。"""
    proxy_mode = str(config_manager.get("proxy_mode") or "off").lower()
    proxy_url = str(config_manager.get("proxy_url") or "")

    if proxy_mode in ("http", "socks5") and proxy_url:
        scheme = "socks5h" if proxy_mode == "socks5" else "http"
        url = proxy_url if "://" in proxy_url else f"{scheme}://{proxy_url}"
        return {"http": url, "https": url}
    return {}


def _get_mirror_url(url: str) -> str:
    """根据配置应用镜像。"""
    source = str(config_manager.get("update_source") or "github").lower()
    if source == "ghproxy" and url.startswith("https://github.com/"):
        mirror = "https://ghfast.top/"
        return mirror + url
    return url


# ─── 清单获取线程 ────────────────────────────────────────


class _ManifestWorker(QThread):
    """后台线程：获取 update-manifest.json"""

    finished = Signal(dict)  # manifest dict
    error = Signal(str)

    def __init__(self, release_tag: str):
        super().__init__()
        self.release_tag = release_tag

    def run(self) -> None:
        try:
            import requests

            proxies = _get_proxies()

            # 1. 先从 GitHub Release 获取 manifest 资产 URL
            channel = _get_update_channel()

            if channel == "stable":
                api_url = f"{GITHUB_API_BASE}/releases/latest"
            else:
                # pre 通道检查所有 release，取最新的
                api_url = f"{GITHUB_API_BASE}/releases?per_page=5"

            headers = {"Accept": "application/vnd.github.v3+json"}
            token = os.environ.get("GITHUB_TOKEN")
            if token:
                headers["Authorization"] = f"token {token}"

            resp = requests.get(api_url, headers=headers, proxies=proxies, timeout=15)
            resp.raise_for_status()

            if channel == "stable":
                release_data = resp.json()
            else:
                releases = resp.json()
                # 找到最新的非 draft release
                release_data = next(
                    (r for r in releases if not r.get("draft")),
                    releases[0] if releases else {},
                )

            if not release_data:
                self.error.emit("未找到 Release")
                return

            # 2. 从 assets 中找到 manifest
            manifest_url = ""
            assets = release_data.get("assets") or []
            for asset in assets:
                if asset.get("name") == MANIFEST_FILENAME:
                    manifest_url = asset.get("browser_download_url", "")
                    break

            if not manifest_url:
                self.error.emit("Release 中未找到 update-manifest.json")
                return

            # 3. 下载 manifest（附加时间戳穿透缓存）
            final_url = _get_mirror_url(manifest_url)
            sep = "&" if "?" in final_url else "?"
            final_url = f"{final_url}{sep}t={int(time.time())}"

            resp = requests.get(final_url, headers=headers, proxies=proxies, timeout=15)
            resp.raise_for_status()
            manifest = resp.json()

            # 附加 release 信息
            manifest["_release_tag"] = release_data.get("tag_name", "")
            manifest["_release_body"] = release_data.get("body", "")
            manifest["_is_prerelease"] = release_data.get("prerelease", False)

            self.finished.emit(manifest)

        except Exception as e:
            logger.error(f"[ComponentUpdate] 清单获取失败: {e}")
            self.error.emit(str(e))


# ─── 下载线程 ────────────────────────────────────────────


class _DownloadWorker(QThread):
    """后台线程：下载更新文件"""

    progress = Signal(int)  # 0-100
    finished = Signal(str)  # 本地文件路径
    error = Signal(str)

    def __init__(self, url: str, expected_sha256: str = ""):
        super().__init__()
        self.url = url
        self.expected_sha256 = expected_sha256

    def run(self) -> None:
        try:
            import hashlib
            import tempfile

            import requests

            final_url = _get_mirror_url(self.url)
            proxies = _get_proxies()

            tmp_dir = Path(tempfile.mkdtemp(prefix="fluentytdl_update_"))
            filename = self.url.rsplit("/", 1)[-1]
            dest = tmp_dir / filename

            resp = requests.get(final_url, proxies=proxies, timeout=300, stream=True)
            resp.raise_for_status()

            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            sha256 = hashlib.sha256()

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    f.write(chunk)
                    sha256.update(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        self.progress.emit(int(downloaded / total * 100))

            if self.expected_sha256:
                actual = sha256.hexdigest().lower()
                expected = self.expected_sha256.strip().lower()
                if actual != expected:
                    dest.unlink(missing_ok=True)
                    self.error.emit(f"SHA256 校验失败\n预期: {expected}\n实际: {actual}")
                    return

            self.progress.emit(100)
            self.finished.emit(str(dest))

        except Exception as e:
            logger.error(f"[ComponentUpdate] 下载失败: {e}")
            self.error.emit(str(e))


# ─── 主管理器 ────────────────────────────────────────────


class ComponentUpdateManager(QObject):
    """统一组件更新协调器"""

    # 清单信号
    manifest_fetched = Signal(dict)
    manifest_error = Signal(str)

    # app-core 信号
    app_update_available = Signal(dict)  # {version, tag, changelog, url, sha256, is_prerelease}
    app_no_update = Signal()
    app_check_error = Signal(str)

    # 下载信号
    download_progress = Signal(int)
    download_finished = Signal(str)  # 本地路径
    download_error = Signal(str)

    # 通用信号
    check_complete = Signal(list)  # 所有组件检查结果列表

    def __init__(self) -> None:
        super().__init__()
        self._manifest: dict | None = None
        self._manifest_worker: _ManifestWorker | None = None
        self._download_worker: _DownloadWorker | None = None

    @property
    def manifest(self) -> dict | None:
        return self._manifest

    # ── 清单获取 ──────────────────────────────────────────

    def fetch_manifest(self) -> None:
        """异步获取更新清单。"""
        channel = _get_update_channel()
        if channel == "beta":
            logger.info("[ComponentUpdate] beta 通道，跳过清单获取")
            return

        worker = _ManifestWorker(release_tag="")
        worker.finished.connect(self._on_manifest_fetched)
        worker.error.connect(self._on_manifest_error)
        self._manifest_worker = worker
        worker.start()

    def _on_manifest_fetched(self, manifest: dict) -> None:
        self._manifest = manifest
        logger.info(f"[ComponentUpdate] 清单获取成功: {manifest.get('app_version', '?')}")
        self.manifest_fetched.emit(manifest)

    def _on_manifest_error(self, msg: str) -> None:
        logger.warning(f"[ComponentUpdate] 清单获取失败: {msg}")
        self.manifest_error.emit(msg)

    # ── 统一检查 ──────────────────────────────────────────

    def check_all(self) -> None:
        """检查所有组件更新（app-core + bin/ 工具）。"""
        channel = _get_update_channel()

        if channel == "beta":
            # beta 通道不检查更新
            return

        # 先获取清单
        self.fetch_manifest()

    def check_app_update(self) -> None:
        """仅检查 app-core 更新。"""
        channel = _get_update_channel()

        if channel == "beta":
            self.app_check_error.emit("beta")
            return

        if self._manifest:
            self._compare_app_version()
        else:
            # 需要先获取清单，使用一次性连接
            self._manifest_app_check_conn = True
            self.manifest_fetched.connect(self._on_manifest_for_app_check)
            self.fetch_manifest()

    def _on_manifest_for_app_check(self, _manifest: dict) -> None:
        """清单获取完成后比对 app 版本（一次性回调）。"""
        try:
            self.manifest_fetched.disconnect(self._on_manifest_for_app_check)
        except RuntimeError:
            pass
        self._compare_app_version()

    def _compare_app_version(self) -> None:
        """比对 app-core 版本。"""
        if not self._manifest:
            self.app_check_error.emit("清单未获取")
            return

        try:
            from fluentytdl import __version__
        except ImportError:
            self.app_check_error.emit("无法获取当前版本")
            return

        channel = _get_update_channel()
        manifest_version = self._manifest.get("app_version", "")
        manifest_tag = self._manifest.get("release_tag", manifest_version)
        is_prerelease = self._manifest.get("_is_prerelease", False)

        # 通道过滤：稳定版不接收预发布
        if channel == "stable" and is_prerelease:
            self.app_no_update.emit()
            return

        current = _parse_version(__version__)
        latest = _parse_version(manifest_version)

        if latest <= current:
            self.app_no_update.emit()
            return

        # 检查跳过版本
        skipped_key = "skipped_stable_version" if channel == "stable" else "skipped_pre_version"
        skipped = str(config_manager.get(skipped_key) or "")
        if skipped and _parse_version(skipped) >= latest:
            self.app_no_update.emit()
            return

        # 获取 app-core 组件信息
        app_core = self._manifest.get("components", {}).get("app-core", {})

        self.app_update_available.emit(
            {
                "version": manifest_version,
                "tag": manifest_tag,
                "changelog": self._manifest.get("_release_body", ""),
                "url": app_core.get("url", ""),
                "sha256": app_core.get("sha256", ""),
                "size": app_core.get("size", 0),
                "is_prerelease": is_prerelease,
            }
        )

    # ── 下载 app-core 更新 ────────────────────────────────

    def download_app_update(self, url: str, sha256: str = "") -> None:
        """下载 app-core 更新归档。"""
        if not url:
            self.download_error.emit("下载 URL 为空")
            return

        worker = _DownloadWorker(url, sha256)
        worker.progress.connect(self.download_progress)
        worker.finished.connect(self._on_download_done)
        worker.error.connect(self.download_error)
        self._download_worker = worker
        worker.start()

    def _on_download_done(self, path: str) -> None:
        self.download_finished.emit(path)

    # ── 应用 app-core 更新 ────────────────────────────────

    @staticmethod
    def apply_app_core_update(archive_path: str) -> None:
        """启动 updater.exe 并退出主程序。"""
        app_dir = frozen_app_dir()
        exe_name = Path(sys.executable).name if is_frozen() else "FluentYTDL.exe"
        pid = os.getpid()

        # updater.exe 位于应用目录根目录
        updater_path = app_dir / "updater.exe"
        if not updater_path.exists():
            # 回退：检查 _internal/ 目录
            updater_path = app_dir / "_internal" / "updater.exe"

        if not updater_path.exists():
            logger.error(f"[ComponentUpdate] updater.exe 不存在: {updater_path}")
            raise FileNotFoundError(f"updater.exe 不存在: {updater_path}")

        logger.info(
            f"[ComponentUpdate] 启动 updater.exe: pid={pid}, archive={archive_path}, dest={app_dir}"
        )

        cmd = [
            str(updater_path),
            "--pid", str(pid),
            "--archive", str(archive_path),
            "--dest", str(app_dir),
            "--exe", exe_name,
        ]

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW

        subprocess.Popen(cmd, creationflags=creationflags)
        sys.exit(0)

    # ── 版本通道工具 ──────────────────────────────────────

    @staticmethod
    def get_update_channel() -> str:
        """获取当前更新通道。"""
        return _get_update_channel()

    @staticmethod
    def is_beta() -> bool:
        """是否为 beta 版本。"""
        return _get_update_channel() == "beta"

    def get_manifest_component(self, key: str) -> dict | None:
        """从缓存清单中获取指定组件信息。"""
        if not self._manifest:
            return None
        return self._manifest.get("components", {}).get(key)


# ── 单例 ──
component_update_manager = ComponentUpdateManager()
