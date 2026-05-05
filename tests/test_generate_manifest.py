"""Tests for the build-time manifest generator."""

import hashlib
import sys
from pathlib import Path

import pytest

# Resolve scripts/ for direct execution
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from generate_manifest import generate_manifest, parse_version_prefix, sha256_file


class TestParseVersionPrefix:
    def test_v_prefix(self):
        assert parse_version_prefix("v-3.0.18") == ("v-", "3.0.18")

    def test_pre_prefix(self):
        assert parse_version_prefix("pre-3.0.18") == ("pre-", "3.0.18")

    def test_beta_prefix(self):
        assert parse_version_prefix("beta-0.0.5") == ("beta-", "0.0.5")

    def test_no_prefix_defaults_to_v(self):
        assert parse_version_prefix("3.0.18") == ("v-", "3.0.18")

    def test_empty_string(self):
        assert parse_version_prefix("") == ("v-", "")


class TestSha256File:
    def test_known_content(self, tmp_path):
        """SHA256 of known content should match expected hash."""
        test_file = tmp_path / "test.bin"
        content = b"Hello, FluentYTDL!"
        test_file.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        assert sha256_file(test_file) == expected

    def test_empty_file(self, tmp_path):
        test_file = tmp_path / "empty.bin"
        test_file.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert sha256_file(test_file) == expected


class TestGenerateManifest:
    def test_structure_has_required_fields(self, tmp_path):
        """Manifest should have manifest_version, app_version, components."""
        manifest = generate_manifest("v-3.0.18", tmp_path, "https://example.com/releases")
        assert "manifest_version" in manifest
        assert "app_version" in manifest
        assert "release_tag" in manifest
        assert "components" in manifest

    def test_manifest_version_is_1(self, tmp_path):
        manifest = generate_manifest("v-3.0.18", tmp_path, "https://example.com")
        assert manifest["manifest_version"] == 1

    def test_app_version_preserved(self, tmp_path):
        manifest = generate_manifest("pre-3.0.18", tmp_path, "https://example.com")
        assert manifest["app_version"] == "pre-3.0.18"

    def test_app_core_component_with_archive(self, tmp_path):
        """When app-core.7z exists, manifest should include it with SHA256."""
        # Create a fake app-core archive
        archive = tmp_path / "FluentYTDL-v-3.0.18-win64-app-core.7z"
        content = b"fake archive content"
        archive.write_bytes(content)

        manifest = generate_manifest("v-3.0.18", tmp_path, "https://example.com")
        app_core = manifest["components"].get("app-core")

        assert app_core is not None
        assert app_core["version"] == "3.0.18"
        assert app_core["sha256"] == hashlib.sha256(content).hexdigest()
        assert app_core["size"] == len(content)
        assert "https://example.com" in app_core["url"]

    def test_app_core_missing_archive(self, tmp_path):
        """When app-core.7z doesn't exist, app-core component should be absent."""
        manifest = generate_manifest("v-3.0.18", tmp_path, "https://example.com")
        assert "app-core" not in manifest["components"]

    def test_empty_release_dir(self, tmp_path):
        """Empty release dir should produce a manifest with no app-core."""
        manifest = generate_manifest("v-3.0.18", tmp_path, "https://example.com")
        assert manifest["app_version"] == "v-3.0.18"
        assert isinstance(manifest["components"], dict)
