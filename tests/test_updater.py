"""Tests for the standalone updater module (no Qt/network dependencies)."""

import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

# Resolve src/ for direct execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fluentytdl.core.updater import (
    extract_archive,
    request_admin_if_needed,
    self_delete,
    wait_for_process,
)


class TestWaitForProcess:
    def test_nonexistent_pid_returns_true(self):
        """A PID that doesn't exist should return True immediately."""
        result = wait_for_process(99999, timeout=2)
        assert result is True

    def test_current_pid_times_out(self):
        """The current process is alive, so waiting should time out."""
        result = wait_for_process(os.getpid(), timeout=1)
        assert result is False


class TestExtractArchive:
    def test_zip_extraction(self, tmp_path):
        """Extracting a valid zip should produce the expected file."""
        # Create a zip with a test file
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("hello.txt", "world")

        dest = tmp_path / "out"
        dest.mkdir()
        extract_archive(zip_path, dest)
        assert (dest / "hello.txt").read_text() == "world"

    def test_unsupported_format_raises(self, tmp_path):
        """A .txt file should raise ValueError."""
        txt_path = tmp_path / "file.txt"
        txt_path.write_text("not an archive")
        with pytest.raises(ValueError, match="不支持的归档格式"):
            extract_archive(txt_path, tmp_path / "out")

    def test_7z_extraction_with_py7zr(self, tmp_path):
        """If py7zr is available, test 7z extraction."""
        py7zr = pytest.importorskip("py7zr")

        archive_path = tmp_path / "test.7z"
        with py7zr.SevenZipFile(archive_path, "w") as zf:
            zf.writestr(b"hello 7z", "hello.txt")

        dest = tmp_path / "out"
        dest.mkdir()
        extract_archive(archive_path, dest)
        assert (dest / "hello.txt").exists()


class TestRequestAdminIfNeeded:
    def test_user_directory_no_elevation(self, tmp_path):
        """A non-Program-Files directory should not request elevation."""
        result = request_admin_if_needed(tmp_path)
        assert result is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_local_appdata_no_elevation(self):
        """LOCALAPPDATA directory should not request elevation."""
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        if local.exists():
            result = request_admin_if_needed(local / "FluentYTDL")
            assert result is False


class TestSelfDelete:
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_self_delete_creates_process(self, tmp_path):
        """self_delete should spawn a cmd process without raising."""
        fake_exe = tmp_path / "fake.exe"
        fake_exe.write_bytes(b"MZ")
        # Should not raise
        self_delete(fake_exe)
