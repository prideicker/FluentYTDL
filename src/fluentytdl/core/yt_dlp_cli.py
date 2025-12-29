from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from threading import Event
from typing import Any

from fluentytdl.utils.paths import find_bundled_executable, is_frozen, locate_runtime_tool

from .config_manager import config_manager


class YtDlpCancelled(Exception):
    """Raised when a yt-dlp subprocess is cancelled by the UI."""


def _win_hide_console_kwargs() -> dict[str, Any]:
    """Hide console window for subprocess on Windows (GUI apps)."""

    if os.name != "nt":
        return {}

    kwargs: dict[str, Any] = {}
    try:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    except Exception:
        pass

    try:
        si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        si.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = si
    except Exception:
        pass

    return kwargs


def resolve_yt_dlp_exe() -> Path | None:
    """Resolve yt-dlp executable path.

    Priority:
    1) config yt_dlp_exe_path (if exists)
    2) bundled _internal/yt-dlp/yt-dlp.exe (frozen)
    3) yt-dlp on PATH
    """

    cfg = str(config_manager.get("yt_dlp_exe_path") or "").strip()
    if cfg:
        p = Path(cfg)
        if p.exists():
            return p

    # Prefer tools placed into exe-adjacent `bin` (or project `bin`) via locate_runtime_tool.
    try:
        return locate_runtime_tool("yt-dlp.exe", "yt-dlp/yt-dlp.exe", "yt_dlp/yt-dlp.exe")
    except FileNotFoundError:
        # fallback to legacy bundled search when frozen
        if is_frozen():
            p = find_bundled_executable(
                "yt-dlp.exe",
                "yt-dlp/yt-dlp.exe",
                "yt_dlp/yt-dlp.exe",
            )
            if p is not None:
                return p

    which = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    return Path(which) if which else None


def _prepend_path(env: dict[str, str], *dirs: str) -> None:
    existing = env.get("PATH") or ""
    cleaned = [d for d in dirs if d]
    if not cleaned:
        return
    env["PATH"] = os.pathsep.join(cleaned + [existing]) if existing else os.pathsep.join(cleaned)


def prepare_yt_dlp_env() -> dict[str, str]:
    """Prepare environment so yt-dlp.exe can find bundled ffmpeg and JS runtime.

    We intentionally prefer PATH injection over less-portable flags.
    """

    env = dict(os.environ)

    # FFmpeg
    ffmpeg_path = str(config_manager.get("ffmpeg_path") or "").strip() or None
    if ffmpeg_path and Path(ffmpeg_path).exists():
        _prepend_path(env, str(Path(ffmpeg_path).resolve().parent))
    else:
        try:
            p = locate_runtime_tool("ffmpeg.exe", "ffmpeg/ffmpeg.exe")
            _prepend_path(env, str(Path(p).resolve().parent))
        except FileNotFoundError:
            bundled_ffmpeg = find_bundled_executable("ffmpeg.exe", "ffmpeg/ffmpeg.exe")
            if bundled_ffmpeg is not None:
                _prepend_path(env, str(bundled_ffmpeg.resolve().parent))

    # JS runtime (deno preferred)
    js_runtime_path = str(config_manager.get("js_runtime_path") or "").strip() or None
    if js_runtime_path and Path(js_runtime_path).exists():
        _prepend_path(env, str(Path(js_runtime_path).resolve().parent))
    else:
        try:
            p = locate_runtime_tool("deno.exe", "js/deno.exe", "deno/deno.exe")
            _prepend_path(env, str(Path(p).resolve().parent))
        except FileNotFoundError:
            bundled_deno = find_bundled_executable("deno.exe", "js/deno.exe", "deno/deno.exe")
            if bundled_deno is not None:
                _prepend_path(env, str(bundled_deno.resolve().parent))

    return env


def ydl_opts_to_cli_args(ydl_opts: dict[str, Any]) -> list[str]:
    """Convert a subset of yt-dlp Python options to CLI args.

    This mapping is intentionally minimal and only covers what the app uses.
    """

    args: list[str] = []

    proxy = ydl_opts.get("proxy")
    if isinstance(proxy, str):
        args += ["--proxy", proxy]

    user_agent = ydl_opts.get("user_agent")
    if isinstance(user_agent, str) and user_agent:
        args += ["--user-agent", user_agent]

    for key, flag in [
        ("socket_timeout", "--socket-timeout"),
        ("retries", "--retries"),
        ("fragment_retries", "--fragment-retries"),
        ("sleep_interval", "--sleep-interval"),
        ("max_sleep_interval", "--max-sleep-interval"),
    ]:
        v = ydl_opts.get(key)
        if isinstance(v, (int, float)):
            args += [flag, str(int(v))]

    cookiefile = ydl_opts.get("cookiefile")
    if isinstance(cookiefile, str) and cookiefile:
        args += ["--cookies", cookiefile]

    cookies_from_browser = ydl_opts.get("cookiesfrombrowser")
    if isinstance(cookies_from_browser, (tuple, list)) and cookies_from_browser:
        browser = str(cookies_from_browser[0] or "").strip()
        if browser:
            args += ["--cookies-from-browser", browser]

    js_runtimes = ydl_opts.get("js_runtimes")
    if isinstance(js_runtimes, dict):
        # yt-dlp CLI: --js-runtimes RUNTIME[:PATH]
        # Example: {"deno": {"path": "C:/.../deno.exe"}}
        for runtime_id, cfg in js_runtimes.items():
            rid = str(runtime_id or "").strip()
            if not rid:
                continue
            path = ""
            if isinstance(cfg, dict):
                path = str(cfg.get("path") or "").strip()
            elif isinstance(cfg, str):
                path = cfg.strip()
            value = f"{rid}:{path}" if path else rid
            args += ["--js-runtimes", value]

    ffmpeg_location = ydl_opts.get("ffmpeg_location")
    if isinstance(ffmpeg_location, str) and ffmpeg_location.strip():
        args += ["--ffmpeg-location", ffmpeg_location.strip()]

    extractor_args = ydl_opts.get("extractor_args")
    if isinstance(extractor_args, dict):
        # Example (python API):
        # {"youtube": {"player_client": ["android,ios"], "player_skip": ["js,configs,hls"]}}
        for ie_key, ie_args in extractor_args.items():
            if not ie_key:
                continue
            if not isinstance(ie_args, dict):
                continue
            parts: list[str] = []
            for k, v in ie_args.items():
                if not k:
                    continue
                if isinstance(v, (list, tuple)):
                    flat = [str(x) for x in v if str(x).strip()]
                    if not flat:
                        continue
                    val = ",".join(flat)
                else:
                    val = str(v)
                val = val.strip()
                if not val:
                    continue
                parts.append(f"{k}={val}")
            if parts:
                # See yt-dlp CLI: --extractor-args IE_KEY:ARGS, where ARGS is semicolon-separated.
                args += ["--extractor-args", f"{ie_key}:{';'.join(parts)}"]

    outtmpl = ydl_opts.get("outtmpl")
    if isinstance(outtmpl, str) and outtmpl:
        args += ["-o", outtmpl]

    paths = ydl_opts.get("paths")
    if isinstance(paths, dict):
        # Support {'home': '...'} or {'temp': '...'}
        # CLI -P supports setting home path.
        home = paths.get("home")
        if isinstance(home, str) and home.strip():
            args += ["-P", home.strip()]
        # Note: yt-dlp CLI allows multiple -P, e.g. -P "temp:..."
        temp = paths.get("temp")
        if isinstance(temp, str) and temp.strip():
            args += ["-P", f"temp:{temp.strip()}"]

    fmt = ydl_opts.get("format")
    if isinstance(fmt, str) and fmt:
        args += ["-f", fmt]

    merge_fmt = ydl_opts.get("merge_output_format")
    if isinstance(merge_fmt, str) and merge_fmt:
        args += ["--merge-output-format", merge_fmt]

    if ydl_opts.get("addmetadata") is True:
        args += ["--add-metadata"]

    # Audio-only conversion via postprocessors
    postprocessors = ydl_opts.get("postprocessors")
    if isinstance(postprocessors, list):
        for pp in postprocessors:
            if not isinstance(pp, dict):
                continue
            if str(pp.get("key") or "").strip() == "FFmpegExtractAudio":
                codec = str(pp.get("preferredcodec") or "mp3").strip() or "mp3"
                quality = str(pp.get("preferredquality") or "192").strip() or "192"
                args += ["--extract-audio", "--audio-format", codec, "--audio-quality", f"{quality}K"]
                break

    return args


def _terminate_process_best_effort(proc: subprocess.Popen[str]) -> None:
    try:
        proc.terminate()
    except Exception:
        return
    try:
        proc.wait(timeout=1.0)
        return
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def run_dump_single_json(
    url: str,
    ydl_opts: dict[str, Any],
    extra_args: list[str] | None = None,
    *,
    cancel_event: Event | None = None,
) -> dict[str, Any]:
    exe = resolve_yt_dlp_exe()
    if exe is None:
        raise FileNotFoundError("未找到 yt-dlp.exe（既没有内置也不在 PATH 中）")

    cmd = [
        str(exe),
        "--no-warnings",
        "--no-color",
        "--no-progress",
        "-J",
        *ydl_opts_to_cli_args(ydl_opts),
    ]
    if extra_args:
        cmd += list(extra_args)
    cmd.append(url)

    env = prepare_yt_dlp_env()

    if cancel_event is None:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(Path.cwd()),
            **_win_hide_console_kwargs(),
        )

        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode != 0:
            raise RuntimeError(f"yt-dlp.exe 解析失败 (code={proc.returncode})\n{out.strip()}")
    else:
        proc2 = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(Path.cwd()),
            **_win_hide_console_kwargs(),
        )

        # IMPORTANT: We must continuously drain stdout/stderr to avoid deadlocks
        # when yt-dlp prints large JSON (common for playlists).
        stdout = ""
        stderr = ""
        while True:
            if cancel_event.is_set():
                _terminate_process_best_effort(proc2)
                raise YtDlpCancelled("yt-dlp cancelled")
            try:
                stdout, stderr = proc2.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                # keep pumping
                time.sleep(0.02)
                continue

        out = (stdout or "") + "\n" + (stderr or "")
        if proc2.returncode != 0:
            raise RuntimeError(f"yt-dlp.exe 解析失败 (code={proc2.returncode})\n{out.strip()}")

    # yt-dlp may print other lines; pick the last parsable JSON line.
    for line in reversed(out.splitlines()):
        s = line.strip()
        if not s:
            continue
        if not (s.startswith("{") or s.startswith("[")):
            continue
        try:
            data = json.loads(s)
            if isinstance(data, dict):
                return data
        except Exception:
            continue

    raise RuntimeError(f"yt-dlp 未输出可解析的 JSON:\n{out.strip()}")


def run_version() -> str:
    exe = resolve_yt_dlp_exe()
    if exe is None:
        return ""
    try:
        out = subprocess.check_output(
            [str(exe), "--version"],
            text=True,
            encoding="utf-8",
            errors="replace",
            **_win_hide_console_kwargs(),
        )
        return (out or "").strip()
    except Exception:
        return ""