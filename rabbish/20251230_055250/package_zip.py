from __future__ import annotations

import argparse
import os
import platform
import sys
import zipfile
from datetime import datetime
from pathlib import Path


def _read_project_version(pyproject: Path) -> str:
    if not pyproject.exists():
        return "0.0.0"

    # Python 3.11+ has tomllib
    try:
        import tomllib  # type: ignore

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return str((data.get("project") or {}).get("version") or "0.0.0")
    except Exception:
        # Fallback: simple parse
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("version") and "=" in line:
                _, v = line.split("=", 1)
                return v.strip().strip('"').strip("'")
        return "0.0.0"


def _detect_win_arch() -> str:
    # Prefer Windows environment variable
    arch = (os.environ.get("PROCESSOR_ARCHITECTURE") or "").lower()
    if arch in {"amd64", "x86_64"}:
        return "win64"
    if arch in {"x86", "i386", "i686"}:
        return "win32"

    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "win64"
    if machine in {"x86", "i386", "i686"}:
        return "win32"
    return "win"


def _iter_files(base_dir: Path) -> list[Path]:
    files: list[Path] = []
    for p in base_dir.rglob("*"):
        if p.is_file():
            files.append(p)
    return files


def build_zip(dist_dir: Path, output_zip: Path) -> None:
    if output_zip.exists():
        output_zip.unlink()

    top_folder = dist_dir.name  # keep folder name in zip

    files = _iter_files(dist_dir)
    if not any(p.name.lower() == "fluentytdl.exe" for p in files):
        raise RuntimeError(f"dist folder missing main exe: {dist_dir}")

    output_zip.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            rel = p.relative_to(dist_dir)
            arcname = str(Path(top_folder) / rel).replace("\\", "/")
            zf.write(p, arcname)


def main() -> int:
    parser = argparse.ArgumentParser(description="Package PyInstaller dist output into a ZIP.")
    parser.add_argument(
        "--dist",
        default=str(Path("dist") / "FluentYTDL"),
        help="dist folder to zip (default: dist/FluentYTDL)",
    )
    parser.add_argument(
        "--out",
        default="",
        help="output zip path (default: installer/FluentYTDL-v<version>-<arch>-<date>.zip)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    pyproject = root / "pyproject.toml"
    version = _read_project_version(pyproject)
    arch = _detect_win_arch()
    date = datetime.now().strftime("%Y%m%d")

    dist_dir = (root / args.dist).resolve() if not Path(args.dist).is_absolute() else Path(args.dist)

    if args.out:
        out_zip = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    else:
        out_zip = root / "installer" / f"FluentYTDL-v{version}-{arch}-{date}.zip"

    if not dist_dir.exists():
        raise FileNotFoundError(f"dist folder not found: {dist_dir}")

    build_zip(dist_dir, out_zip)
    print(f"OK: {out_zip}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
