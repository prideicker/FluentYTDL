from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
assets = root / "assets"
# Find a png that isn't logo.png
candidates = [p for p in assets.iterdir() if p.suffix.lower() in {'.png', '.jpg', '.jpeg'} and p.name.lower() != 'logo.png']
if not candidates:
    print('No candidate image found in assets to install as logo.png')
    raise SystemExit(2)

# Prefer the one with uuid-like name if present
src = None
for p in candidates:
    if len(p.stem) >= 20:
        src = p
        break
if src is None:
    src = candidates[0]

dst = assets / 'logo.png'
try:
    shutil.copy2(src, dst)
    print(f'Copied {src.name} -> {dst.name}')
except Exception as e:
    print('Failed to copy:', e)
    raise
