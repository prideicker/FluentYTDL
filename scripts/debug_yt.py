import os
import sys
import http.cookiejar
import shutil
from pathlib import Path

import yt_dlp
import yt_dlp.version

# === 测试链接：可用命令行传入 ===
# 用法：
#   python debug_yt.py <URL>
#   python debug_yt.py <URL> nocookie
DEFAULT_TEST_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# === cookies 文件路径：使用你的绝对路径 ===
_ROOT_DIR = Path(__file__).resolve().parents[1]
COOKIE_FILE = os.environ.get("FLUENTYTDL_COOKIE_FILE") or str(Path(__file__).resolve().parent / "cookies.txt")


def _load_config_po_token() -> str:
    """Load youtube_po_token from FluentYTDL/config.json if present."""

    try:
        cfg_path = _ROOT_DIR / "config.json"
        if not cfg_path.exists():
            return ""
        import json

        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return ""
        return str(data.get("youtube_po_token") or "").strip()
    except Exception:
        return ""


def inspect_cookie_file(path: str) -> None:
    print("-" * 60)
    print("Inspecting cookie file format...")
    try:
        head = open(path, "rb").read(256)
        head_text = head.decode("utf-8", errors="ignore").lstrip()
        first_line = head_text.splitlines()[0] if head_text.splitlines() else ""
        print(f"First line: {first_line[:120]}")
        if head_text[:1] in "[{":
            print("Looks like JSON export (NOT supported by yt-dlp).")
        elif first_line.startswith("# Netscape HTTP Cookie File"):
            print("Looks like Netscape HTTP Cookie File (OK).")
        else:
            print("Header not recognized; may still be Netscape format if lines are tab-separated.")

        jar = http.cookiejar.MozillaCookieJar()
        jar.load(path, ignore_discard=True, ignore_expires=True)
        print(f"MozillaCookieJar loaded cookies: {len(jar)}")

        yt_related = [c for c in jar if ("youtube" in (c.domain or "")) or ("google" in (c.domain or ""))]
        print(f"YouTube/Google related cookies: {len(yt_related)}")

        domains = sorted({c.domain for c in jar})
        print(f"Domains sample: {', '.join(domains[:10])}{' ...' if len(domains) > 10 else ''}")
    except Exception as exc:
        print(f"Failed to parse as Netscape/MozillaCookieJar: {exc}")


def run_debug() -> None:
    print("=" * 60)
    print(f"Python: {sys.version}")
    print(f"Executable: {sys.executable}")
    print(f"yt-dlp: {yt_dlp.version.__version__}")
    print(f"CWD: {os.getcwd()}")
    print("-" * 60)

    args = [a.strip() for a in sys.argv[1:] if str(a).strip()]
    no_cookie_flags = {"nocookie", "no-cookie", "no_cookie"}
    no_cookie = any(a.lower() in no_cookie_flags for a in args)

    # First non-flag arg is treated as URL.
    url_args = [a for a in args if a.lower() not in no_cookie_flags]
    test_url = url_args[0] if url_args else DEFAULT_TEST_URL

    print(f"Test URL: {test_url}")
    print(f"Cookie file: {COOKIE_FILE}")

    if not no_cookie:
        if not os.path.exists(COOKIE_FILE):
            print("Cookie file not found.")
            print("- Default: scripts/cookies.txt")
            print("- Override: set env FLUENTYTDL_COOKIE_FILE to an absolute path")
            print("Tip: run `python debug_yt.py <URL> nocookie` to test without cookies.")
            return

        size = os.path.getsize(COOKIE_FILE)
        print(f"Cookie file exists. Size: {size} bytes")
        inspect_cookie_file(COOKIE_FILE)
    else:
        print("Running in NO-COOKIE mode")

    # 开启最详细的调试配置
    opts = {
        "verbose": True,  # 打印内部日志
        "quiet": False,
        "no_warnings": False,
        # Avoid system/ambient proxy settings interfering with diagnosis
        # (equivalent to CLI: --proxy "")
        "proxy": "",
        # 强制模拟 Web 客户端 (配合 Cookie 使用)
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    if not no_cookie:
        opts["cookiefile"] = COOKIE_FILE

    # --- Optional: PO Token (mweb recommended) ---
    po_token = _load_config_po_token()
    if po_token:
        print(f"PO Token detected in config.json (masked): {po_token[:16]}…{po_token[-6:] if len(po_token) > 22 else ''}")
        opts["extractor_args"] = {
            "youtube": {
                "player_client": ["default,mweb"],
                "po_token": [po_token],
            }
        }
        if no_cookie:
            print("Warning: PO Token is set, but NO-COOKIE mode is enabled. mweb.gvs token usually requires cookies.")

    # --- External JS runtime (yt-dlp issue #15012) ---
    deno_on_path = shutil.which("deno")
    if deno_on_path:
        print(f"deno on PATH: {deno_on_path}")
    else:
        # winget installs deno.exe under LocalAppData\Microsoft\WinGet\Packages\DenoLand.Deno_*\deno.exe
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            matches = list(
                (Path(local_app_data) / "Microsoft" / "WinGet" / "Packages").glob("DenoLand.Deno_*\\deno.exe")
            )
            if matches:
                deno_path = str(matches[0])
                print(f"deno (winget) detected: {deno_path}")
                opts["js_runtimes"] = {"deno": {"path": deno_path}}
            else:
                print("deno not found on PATH and not found in winget packages.")

    print("=" * 60)
    print("Calling yt-dlp... (download=False)")

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(test_url, download=False)

        if not isinstance(info, dict):
            print(f"Unexpected yt-dlp info type: {type(info)!r}")
            return

        print("=" * 60)
        print(f"Title: {info.get('title')}")
        formats = info.get("formats", []) or []

        print("Formats (video only):")
        for f in formats:
            if f.get("vcodec") == "none":
                continue
            fid = str(f.get("format_id"))
            height = f.get("height")
            note = f.get("format_note")
            ext = f.get("ext")
            print(f"  id={fid:<6} res={str(height) + 'p':<6} note={note!s:<12} ext={ext}")

        has_4k = any((f.get("height") or 0) >= 2160 and f.get("vcodec") != "none" for f in formats)
        print("=" * 60)
        print(f"4K detected: {has_4k}")

    except Exception as e:
        print("=" * 60)
        print("FATAL ERROR")
        print(e)


if __name__ == "__main__":
    run_debug()
