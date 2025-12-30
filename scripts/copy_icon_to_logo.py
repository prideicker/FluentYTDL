from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
assets = root / "assets"
# Find an ico that isn't logo.ico
candidates = [p for p in assets.iterdir() if p.suffix.lower() == '.ico' and p.name.lower() != 'logo.ico']
if not candidates:
    print('No candidate icon found in assets to install as logo.ico')
    raise SystemExit(2)

# Prefer the one with uuid-like name if present
src = None
for p in candidates:
    if len(p.stem) >= 20:
        src = p
        break
if src is None:
    src = candidates[0]

dst = assets / 'logo.ico'
try:
    shutil.copy2(src, dst)
    print(f'Copied {src.name} -> {dst.name}')
except Exception as e:
    print('Failed to copy:', e)
    raise
