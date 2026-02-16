from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import requests
from PySide6.QtCore import QObject, QThread, Signal

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False

from ..utils.logger import logger
from ..utils.paths import frozen_app_dir, is_frozen
from .config_manager import config_manager


class ComponentInfo:
    def __init__(self, key: str, name: str, exe_name: str, extra_exes: list[str] | None = None):
        self.key = key          # internal key: 'yt-dlp', 'ffmpeg', 'deno'
        self.name = name        # Display name
        self.exe_name = exe_name # executable name (e.g., yt-dlp.exe)
        self.extra_exes = extra_exes or [] # Additional executables to update (e.g. ffprobe.exe for ffmpeg)
        self.current_version: str | None = None
        self.latest_version: str | None = None
        self.download_url: str | None = None

class DependencyManager(QObject):
    """
    Manages checking updates and downloading/installing external dependencies.
    """
    
    # Signals
    check_started = Signal(str) # component_key
    check_finished = Signal(str, dict) # component_key, {current, latest, update_available, url}
    check_error = Signal(str, str) # component_key, error_msg
    
    download_started = Signal(str) # component_key
    download_progress = Signal(str, int) # component_key, percent
    download_finished = Signal(str) # component_key
    download_error = Signal(str, str) # component_key, error_msg
    
    install_finished = Signal(str) # component_key

    def __init__(self):
        super().__init__()
        self._workers = {}
        
        # Define known components
        self.components = {
            "yt-dlp": ComponentInfo("yt-dlp", "yt-dlp", "yt-dlp.exe"),
            "ffmpeg": ComponentInfo("ffmpeg", "FFmpeg", "ffmpeg.exe", extra_exes=["ffprobe.exe"]),
            "deno": ComponentInfo("deno", "JS Runtime (Deno)", "deno.exe"),
            "pot-provider": ComponentInfo("pot-provider", "POT Provider", "bgutil-pot-provider.exe"),
            "ytarchive": ComponentInfo("ytarchive", "ytarchive", "ytarchive.exe"),
            "atomicparsley": ComponentInfo("atomicparsley", "AtomicParsley", "AtomicParsley.exe"),
        }

    def get_target_dir(self, component_key: str) -> Path:
        """
        Get the installation directory for a component.
        Prioritizes exe_dir/bin/{component_key}/ for packaged apps.
        """
        # Default to 'bin' next to the executable (standard for our packaged app)
        # Fallback to project root assets/bin for dev
        if is_frozen():
            base = frozen_app_dir() / "bin"
        else:
            # Dev mode: src/fluentytdl/assets/bin or project_root/assets/bin
            # Let's use project_root/assets/bin for consistency
            base = Path(__file__).parents[3] / "assets" / "bin"
            
        target = base / component_key
        if not target.exists():
            try:
                target.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Failed to create target dir {target}: {e}")
        return target

    def get_exe_path(self, component_key: str) -> Path:
        return self.get_target_dir(component_key) / self.components[component_key].exe_name

    def get_mirror_url(self, original_url: str) -> str:
        """Apply the configured mirror source."""
        source = config_manager.get("update_source") or "github"
        
        if source == "github":
            return original_url
        elif source == "ghproxy":
            # Typical ghproxy usage: https://ghproxy.com/https://github.com/...
            # Note: domain might vary, strictly example
            return f"https://mirror.ghproxy.com/{original_url}"
        # Add more mirrors as needed
        return original_url

    def check_update(self, component_key: str):
        """Async check for updates."""
        if component_key not in self.components:
            return
            
        worker = UpdateCheckerWorker(component_key, self)
        worker.finished_signal.connect(self._on_check_finished)
        worker.error_signal.connect(self.check_error)
        worker.start()
        self._workers[f"check_{component_key}"] = worker
        self.check_started.emit(component_key)

    def _on_check_finished(self, key, result):
        # Store result in our cache
        if key in self.components:
            self.components[key].current_version = result.get('current')
            self.components[key].latest_version = result.get('latest')
            self.components[key].download_url = result.get('url')
            
        self.check_finished.emit(key, result)
        # Clean up worker ref
        self._workers.pop(f"check_{key}", None)

    def install_component(self, component_key: str):
        """Async download and install."""
        if component_key not in self.components:
            return

        url = self.components[component_key].download_url
        if not url:
            # If checking hasn't run or failed, try to resolve url dynamically if possible,
            # but usually we expect check_update to run first.
            # For now, trigger an error if no URL known.
            self.download_error.emit(component_key, "Update URL not found. Please check for updates first.")
            return

        # Apply mirror
        final_url = self.get_mirror_url(url)
        target_exe = self.get_exe_path(component_key)
        
        worker = DownloaderWorker(component_key, final_url, target_exe)
        worker.progress_signal.connect(self.download_progress)
        worker.finished_signal.connect(self._on_install_finished)
        worker.error_signal.connect(self.download_error)
        worker.start()
        self._workers[f"install_{component_key}"] = worker
        self.download_started.emit(component_key)

    def _on_install_finished(self, key):
        self.install_finished.emit(key)
        self._workers.pop(f"install_{key}", None)


class UpdateCheckerWorker(QThread):
    finished_signal = Signal(str, dict)
    error_signal = Signal(str, str)

    def __init__(self, key: str, manager: DependencyManager):
        super().__init__()
        self.key = key
        self.manager = manager

    def run(self):
        try:
            exe_path = self.manager.get_exe_path(self.key)
            current_ver = self._get_local_version(self.key, exe_path)
            
            latest_ver, url = self._get_remote_version(self.key)
            
            update_available = False
            if latest_ver and latest_ver != "unknown":
                if current_ver == "unknown" or current_ver != latest_ver:
                    # Simple string comparison is often enough for git tags, 
                    # but semantic versioning compare is better. 
                    # For now, inequality is a safe trigger.
                    update_available = True

            result = {
                "current": current_ver,
                "latest": latest_ver,
                "update_available": update_available,
                "url": url
            }
            self.finished_signal.emit(self.key, result)

        except Exception as e:
            logger.error(f"Update check failed for {self.key}: {e}")
            self.error_signal.emit(self.key, str(e))

    def _get_local_version(self, key: str, path: Path) -> str:
        if not path.exists():
            return "unknown"
        
        try:
            # Run --version
            cmd = [str(path), "--version"]
            # Deno uses 'deno --version'
            # FFmpeg uses 'ffmpeg -version' (single dash often works too)
            if key == "ffmpeg":
                cmd = [str(path), "-version"]
            
            # Windows hide console
            kwargs = {}
            if os.name == "nt":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0
                kwargs["startupinfo"] = si
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", **kwargs)
            if proc.returncode != 0:
                return "unknown"
            
            out = proc.stdout.strip()
            if key == "yt-dlp":
                # yt-dlp output is just the date/version: "2023.11.16"
                return out.splitlines()[0]
            elif key == "deno":
                # deno 1.38.0 (release, x86_64-pc-windows-msvc) ...
                m = re.search(r"deno (\d+\.\d+\.\d+)", out)
                if m:
                    return m.group(1)
            elif key == "ffmpeg":
                # ffmpeg version 6.1-essentials_build-www.gyan.dev ...
                # or ffmpeg version n6.1 ...
                line = out.splitlines()[0]
                m = re.search(r"ffmpeg version ([^\s]+)", line)
                if m:
                    return m.group(1)
            elif key == "pot-provider":
                # bgutil-ytdlp-pot-provider-rs
                # Output: something like "bgutil-pot-provider 0.1.5" or just version
                m = re.search(r"(\d+\.\d+\.\d+)", out)
                if m:
                    return m.group(1)
            elif key == "ytarchive":
                # ytarchive outputs: "ytarchive v0.4.0" or similar
                m = re.search(r"v?(\d+\.\d+\.\d+)", out)
                if m:
                    return m.group(1)
            elif key == "atomicparsley":
                # AtomicParsley outputs: "AtomicParsley version: 20240608.083822.1ed9031" or similar
                m = re.search(r"(\d{8}\.\d+\.\w+)", out)
                if m:
                    return m.group(1)
                
            return "installed" # Fallback if parsing fails
        except Exception:
            return "unknown"

    def _get_remote_version(self, key: str) -> tuple[str, str]:
        # Return (version_tag, download_url)
        # Using GitHub API
        proxies = {}
        proxy_url = config_manager.get("proxy_url")
        if config_manager.get("proxy_mode") in ("http", "socks5") and proxy_url:
             proxies = {"http": proxy_url, "https": proxy_url}

        if key == "yt-dlp":
            url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
            resp = requests.get(url, proxies=proxies, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            tag = data["tag_name"] # e.g. "2023.11.16"
            
            # Find exe asset
            dl_url = ""
            for asset in data.get("assets", []):
                if asset["name"] == "yt-dlp.exe":
                    dl_url = asset["browser_download_url"]
                    break
            return tag, dl_url

        elif key == "deno":
            url = "https://api.github.com/repos/denoland/deno/releases/latest"
            resp = requests.get(url, proxies=proxies, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            tag = data["tag_name"].lstrip("v") # e.g. "1.38.0"
            
            # Find windows zip
            dl_url = ""
            for asset in data.get("assets", []):
                if "x86_64-pc-windows-msvc.zip" in asset["name"]:
                    dl_url = asset["browser_download_url"]
                    break
            return tag, dl_url

        elif key == "ffmpeg":
            # FFmpeg is tricky. Gyan.dev is standard for Windows.
            # We can check the 'release' info from gyan.dev api or just check github mirror.
            # BtbN builds are also good and hosted on GitHub. Let's use BtbN for easy API access.
            url = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
            resp = requests.get(url, proxies=proxies, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            tag = data["tag_name"] # e.g. "latest" or "autobuild-..."
            
            # We specifically want the win64-gpl-shared or static
            dl_url = ""
            for asset in data.get("assets", []):
                if "win64-gpl.zip" in asset["name"] and "shared" not in asset["name"]:
                     dl_url = asset["browser_download_url"]
                     break
            return tag, dl_url

        elif key == "pot-provider":
            # bgutil-ytdlp-pot-provider-rs from jim60105
            url = "https://api.github.com/repos/jim60105/bgutil-ytdlp-pot-provider-rs/releases/latest"
            resp = requests.get(url, proxies=proxies, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            tag = data["tag_name"].lstrip("v")  # e.g. "0.1.5"
            
            # Find windows exe or zip
            dl_url = ""
            for asset in data.get("assets", []):
                name = asset["name"].lower()
                # Look for windows exe: bgutil-pot-windows-x86_64.exe
                if "windows" in name and name.endswith(".exe"):
                    dl_url = asset["browser_download_url"]
                    break
            return tag, dl_url

        elif key == "ytarchive":
            # Kethsar/ytarchive from GitHub
            url = "https://api.github.com/repos/Kethsar/ytarchive/releases/latest"
            resp = requests.get(url, proxies=proxies, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            tag = data["tag_name"].lstrip("v")  # e.g. "0.4.0"
            
            # Find windows amd64 executable
            dl_url = ""
            for asset in data.get("assets", []):
                name = asset["name"].lower()
                # ytarchive_windows_amd64.exe
                if "windows" in name and "amd64" in name and name.endswith(".exe"):
                    dl_url = asset["browser_download_url"]
                    break
            return tag, dl_url

        elif key == "atomicparsley":
            # wez/atomicparsley from GitHub
            url = "https://api.github.com/repos/wez/atomicparsley/releases/latest"
            resp = requests.get(url, proxies=proxies, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            tag = data["tag_name"]  # e.g. "20240608.083822.1ed9031"
            
            # Find Windows zip asset
            dl_url = ""
            for asset in data.get("assets", []):
                name = asset["name"].lower()
                # AtomicParsleyWindows.zip
                if "windows" in name and name.endswith(".zip"):
                    dl_url = asset["browser_download_url"]
                    break
            return tag, dl_url

        return "unknown", ""


class DownloaderWorker(QThread):
    progress_signal = Signal(str, int)
    finished_signal = Signal(str)
    error_signal = Signal(str, str)

    def __init__(self, key: str, url: str, target_exe: Path):
        super().__init__()
        self.key = key
        self.url = url
        self.target_exe = target_exe
        self.extra_exes: list[str] = []
        
        # Inject extra_exes if available
        if dependency_manager.components.get(key):
            self.extra_exes = dependency_manager.components[key].extra_exes

    def run(self):
        tmp_path: str | None = None
        try:
            # 1. Download to temp file
            proxies = {}
            proxy_url = config_manager.get("proxy_url")
            if config_manager.get("proxy_mode") in ("http", "socks5") and proxy_url:
                 proxies = {"http": proxy_url, "https": proxy_url}

            logger.info(f"Downloading {self.key} from {self.url}")
            
            with requests.get(self.url, stream=True, proxies=proxies, timeout=30) as r:
                r.raise_for_status()
                total_length = int(r.headers.get('content-length', 0))
                
                # Create a temp file
                fd, tmp_path = tempfile.mkstemp()
                os.close(fd)
                
                last_emit_time = 0
                last_emit_percent = -1
                
                with open(tmp_path, 'wb') as f:
                    downloaded = 0
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_length > 0:
                                percent = int(downloaded * 100 / total_length)
                                current_time = time.time()
                                # Throttle: emit only if percent changed AND (>= 1% diff OR > 100ms passed)
                                if percent != last_emit_percent:
                                    if (percent - last_emit_percent >= 1) or (current_time - last_emit_time > 0.1) or percent == 100:
                                        self.progress_signal.emit(self.key, percent)
                                        last_emit_percent = percent
                                        last_emit_time = current_time

            # 2. Extract or Move
            # Kill processes first? Ideally UI should ensure nothing is running.
            
            # Prepare final dir
            dest_dir = self.target_exe.parent
            dest_dir.mkdir(parents=True, exist_ok=True)
            
            if self.url.endswith(".zip"):
                self._handle_zip(tmp_path, dest_dir)
                # zip handling doesn't move the temp file, so we need to delete it
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            else:
                self._handle_exe(tmp_path)
                # _handle_exe uses shutil.move, which moves the file, so no need to delete
                # But if it exists (move failed), clean it up
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

            self.finished_signal.emit(self.key)

        except Exception as e:
            logger.error(f"Install failed for {self.key}: {e}")
            self.error_signal.emit(self.key, str(e))
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def _handle_exe(self, tmp_path):
        self._safe_install(tmp_path, self.target_exe)

    def _handle_zip(self, zip_path, dest_dir):
        # Extract specific file from zip
        with zipfile.ZipFile(zip_path, 'r') as z:
            # Prepare list of files to extract: main exe + extra exes
            targets = [(self.target_exe.name, self.target_exe)]
            
            for extra in self.extra_exes:
                targets.append((extra, dest_dir / extra))
            
            for target_name, target_path in targets:
                found_member = None
                
                # 1. Try exact match or path ending with target_name
                for name in z.namelist():
                    if name.endswith(f"/{target_name}") or name == target_name:
                        found_member = name
                        break
                
                # 2. Heuristic search (case insensitive)
                if not found_member:
                    for name in z.namelist():
                        if name.lower().endswith(target_name.lower()):
                            found_member = name
                            break
                
                if not found_member:
                    # Only raise error for the main executable
                    if target_name == self.target_exe.name:
                        raise FileNotFoundError(f"Could not find {target_name} inside the downloaded archive.")
                    else:
                        logger.warning(f"Could not find extra component {target_name} in archive. Skipping.")
                        continue

                # Extract to a temporary file first
                with z.open(found_member) as source:
                    # Create a temp file for the extracted exe
                    fd, extracted_tmp_path = tempfile.mkstemp()
                    os.close(fd)
                    
                    try:
                        with open(extracted_tmp_path, "wb") as target:
                            shutil.copyfileobj(source, target)
                        
                        # Install securely
                        self._safe_install(extracted_tmp_path, target_path)
                    finally:
                        if os.path.exists(extracted_tmp_path):
                            try:
                                os.remove(extracted_tmp_path)
                            except Exception:
                                pass

    def _safe_install(self, source_path: str | Path, target_path: Path):
        """
        Safely install a file, handling existing files and potential locks.
        """
        source_path = Path(source_path)
        
        # 1. If target doesn't exist, just move
        if not target_path.exists():
            shutil.move(source_path, target_path)
            return

        # 2. Try to kill processes locking the file
        self._kill_locking_processes(target_path)
        
        # 3. Try to replace with retries
        old_file = target_path.with_suffix(".exe.old")
        
        # Clean up previous .old if exists
        if old_file.exists():
            try:
                os.remove(old_file)
            except Exception as e:
                logger.warning(f"Could not remove existing backup {old_file}: {e}")

        max_retries = 3
        for i in range(max_retries):
            try:
                # Try to rename current to .old
                target_path.replace(old_file)
                break
            except OSError as e:
                if i == max_retries - 1:
                    logger.error(f"Failed to replace {target_path} after {max_retries} attempts: {e}")
                    # Last ditch effort: try to move source to target directly (will fail if locked)
                    # But maybe replace failed due to permission on old_file?
                    pass
                else:
                    logger.warning(f"Replace attempt {i+1} failed for {target_path}: {e}. Retrying...")
                    time.sleep(1)
                    # Try killing processes again
                    self._kill_locking_processes(target_path)
        
        # 4. Move new file to target
        try:
            shutil.move(source_path, target_path)
        except OSError as e:
            # If move failed, try to restore old file if we successfully renamed it
            if old_file.exists() and not target_path.exists():
                try:
                    old_file.replace(target_path)
                except Exception:
                    pass
            raise OSError(
                f"Failed to install new file to {target_path}. Please ensure the file is not in use. Error: {e}"
            ) from e

        # 5. Cleanup .old (best effort)
        if old_file.exists():
            try:
                os.remove(old_file)
            except Exception:
                pass

    def _kill_locking_processes(self, file_path: Path):
        """
        Kill processes that have the file open.
        """
        if not HAS_PSUTIL:
            # Fallback: try to kill by name if it matches known components
            name = file_path.name.lower()
            try:
                subprocess.run(["taskkill", "/F", "/IM", name], 
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            except Exception:
                pass
            return

        file_path_str = str(file_path.resolve()).lower()
        import psutil as psutil_mod
        
        for proc in psutil_mod.process_iter(['pid', 'name', 'open_files']):
            try:
                # Check open files
                open_files = proc.info.get('open_files')
                if open_files:
                    for f in open_files:
                        if f.path and str(Path(f.path).resolve()).lower() == file_path_str:
                            logger.info(f"Killing process {proc.info['name']} ({proc.info['pid']}) locking {file_path}")
                            proc.kill()
                            break
                
                # Also check if the process executable itself is the file
                try:
                    exe = proc.exe()
                    if exe and str(Path(exe).resolve()).lower() == file_path_str:
                        logger.info(f"Killing process {proc.info['name']} ({proc.info['pid']}) running from {file_path}")
                        proc.kill()
                except (psutil_mod.AccessDenied, psutil_mod.NoSuchProcess):
                    pass
                    
            except (psutil_mod.NoSuchProcess, psutil_mod.AccessDenied):
                continue


# Global instance
dependency_manager = DependencyManager()
