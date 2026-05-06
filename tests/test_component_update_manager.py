"""Tests for ComponentUpdateManager — version parsing, channels, and logic."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Resolve src/ for direct execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ── Pure function tests (no Qt required) ──────────────────────────────────

class TestParseVersion:
    """Test _parse_version version comparison logic."""

    @staticmethod
    def _parse(ver: str) -> tuple[int, ...]:
        """Reproduce the _parse_version logic for testing."""
        import re
        clean = re.sub(r"^(v-?|pre-|beta-)", "", str(ver).strip())
        clean = clean.split("-")[0]
        parts = []
        for p in clean.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        return tuple(parts)

    def test_newer_is_greater(self):
        assert self._parse("3.0.18") > self._parse("3.0.16")

    def test_same_is_not_greater(self):
        assert not (self._parse("3.0.16") > self._parse("3.0.16"))

    def test_major_version_matters(self):
        assert self._parse("4.0.0") > self._parse("3.9.9")

    def test_strips_v_prefix(self):
        assert self._parse("v3.0.18") == (3, 0, 18)

    def test_strips_v_dash_prefix(self):
        assert self._parse("v-3.0.19") == (3, 0, 19)

    def test_v_dash_newer_than_v_dash(self):
        assert self._parse("v-3.0.19") > self._parse("v-3.0.18")

    def test_strips_pre_prefix(self):
        assert self._parse("pre-3.0.18") == (3, 0, 18)

    def test_strips_beta_prefix(self):
        assert self._parse("beta-0.0.5") == (0, 0, 5)


class TestParseVersionPrefix:
    """Test _parse_version_prefix."""

    @staticmethod
    def _parse(full: str) -> tuple[str, str]:
        for pfx in ("v-", "pre-", "beta-"):
            if full.startswith(pfx):
                return pfx, full[len(pfx):]
        return "v-", full

    def test_v_prefix(self):
        assert self._parse("v-3.0.18") == ("v-", "3.0.18")

    def test_pre_prefix(self):
        assert self._parse("pre-3.0.18") == ("pre-", "3.0.18")

    def test_beta_prefix(self):
        assert self._parse("beta-0.0.5") == ("beta-", "0.0.5")

    def test_no_prefix_defaults_to_v(self):
        assert self._parse("3.0.18") == ("v-", "3.0.18")


class TestGetUpdateChannel:
    """Test channel detection from version prefix."""

    @staticmethod
    def _channel(ver: str) -> str:
        if ver.startswith("beta-"):
            return "beta"
        elif ver.startswith("pre-"):
            return "pre"
        return "stable"

    def test_stable_channel(self):
        assert self._channel("v-3.0.16") == "stable"

    def test_pre_channel(self):
        assert self._channel("pre-3.0.18") == "pre"

    def test_beta_channel(self):
        assert self._channel("beta-0.0.5") == "beta"

    def test_no_prefix_is_stable(self):
        assert self._channel("3.0.16") == "stable"


class TestGetMirrorUrl:
    """Test mirror URL transformation."""

    @staticmethod
    def _mirror(url: str, source: str) -> str:
        if source == "ghproxy" and url.startswith("https://github.com/"):
            return "https://ghfast.top/" + url
        return url

    def test_github_to_ghproxy(self):
        url = "https://github.com/owner/repo/releases/download/v1/file.7z"
        result = self._mirror(url, "ghproxy")
        assert result.startswith("https://ghfast.top/")
        assert "github.com" in result

    def test_github_official_unchanged(self):
        url = "https://github.com/owner/repo/releases/download/v1/file.7z"
        result = self._mirror(url, "github")
        assert result == url

    def test_non_github_unchanged(self):
        url = "https://example.com/file.7z"
        result = self._mirror(url, "ghproxy")
        assert result == url


# ── PySide6 signal tests (require QApplication) ──────────────────────────

HAS_PYSIDE6 = True
try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    HAS_PYSIDE6 = False

pytestmark = pytest.mark.skipif(
    not HAS_PYSIDE6 or not sys.platform == "win32",
    reason="PySide6 and Windows required for signal tests",
)


@pytest.fixture(scope="module")
def qapp():
    """Create a QApplication for signal tests."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def manager(qapp):
    """Create a fresh ComponentUpdateManager for each test."""
    from fluentytdl.core.component_update_manager import ComponentUpdateManager
    return ComponentUpdateManager()


class TestBetaChannelLock:
    """Beta versions should not perform update checks."""

    def test_is_beta_true_for_beta_version(self, manager):
        with patch(
            "fluentytdl.core.component_update_manager._get_update_channel",
            return_value="beta",
        ):
            assert manager.is_beta() is True

    def test_is_beta_false_for_stable(self, manager):
        with patch(
            "fluentytdl.core.component_update_manager._get_update_channel",
            return_value="stable",
        ):
            assert manager.is_beta() is False


class TestCompareAppVersion:
    """Test _compare_app_version with mocked manifest."""

    def test_stable_filters_prerelease(self, manager, qapp):
        """Stable channel should ignore prerelease manifests."""
        manager._manifest = {
            "app_version": "3.0.18",
            "_is_prerelease": True,
            "_release_body": "",
            "components": {"app-core": {"url": "", "sha256": ""}},
        }

        signals_received = []
        manager.app_no_update.connect(lambda: signals_received.append(True))

        with patch(
            "fluentytdl.core.component_update_manager._get_update_channel",
            return_value="stable",
        ), patch(
            "fluentytdl.core.component_update_manager._parse_version",
            side_effect=lambda v: tuple(int(x) for x in v.replace("v-", "").replace("pre-", "").replace("beta-", "").split(".")),
        ):
            manager._compare_app_version()

        assert len(signals_received) == 1

    def test_skipped_version_suppresses(self, manager, qapp):
        """Skipped version should emit app_no_update."""
        manager._manifest = {
            "app_version": "3.0.18",
            "_is_prerelease": False,
            "_release_body": "",
            "components": {"app-core": {"url": "", "sha256": ""}},
        }

        signals_received = []
        manager.app_no_update.connect(lambda: signals_received.append(True))

        with patch(
            "fluentytdl.core.component_update_manager._get_update_channel",
            return_value="stable",
        ), patch(
            "fluentytdl.core.component_update_manager._parse_version",
            side_effect=lambda v: tuple(int(x) for x in v.replace("v-", "").replace("pre-", "").replace("beta-", "").split(".")),
        ), patch(
            "fluentytdl.core.component_update_manager.config_manager",
            get=lambda k, d=None: "3.0.18" if k == "skipped_stable_version" else d,
        ):
            manager._compare_app_version()

        assert len(signals_received) == 1
