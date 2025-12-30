"""
Install an image as application icon: copies given image to assets/logo.ico
Usage:
  python scripts/install_icon.py path/to/your/icon.ico

This is a small helper so you can place the attached icon file into the project
and the application will pick it up automatically (resource_path("assets","logo.ico")).
"""

import sys
import shutil
from pathlib import Path

def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv:
        print("Usage: python scripts/install_icon.py PATH_TO_ICON")
        return 2
    src = Path(argv[0]).expanduser()
    if not src.exists():
        print(f"Source not found: {src}")
        return 3
    proj_root = Path(__file__).resolve().parents[1]
    assets_dir = proj_root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    dst = assets_dir / "logo.ico"
    try:
        shutil.copy2(src, dst)
        print(f"Installed icon -> {dst}")
        return 0
    except Exception as e:
        print(f"Failed to install icon: {e}")
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
