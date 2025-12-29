#!/usr/bin/env python3
"""
maintenance.py

Cross-platform project maintenance script for safe cleaning and verification.
Default: dry-run (prints what would be removed). Use --force to actually delete.

Usage:
  python scripts/maintenance.py [--path PATH] [--force] [--yes] [--exclude PATTERN]

Features:
- Clean caches: __pycache__, *.pyc, *.pyo, *.pyd
- Remove build artifacts: build/, dist/, *.spec
- Remove runtime trash: *.log, *.part, *.ytdl, crash dumps (*.dmp, *.dump, *.stackdump)
- Remove system junk: .DS_Store, Thumbs.db
- Remove empty directories (post-clean), respecting whitelist
- Safety: whitelist .git, venv/, .venv/, src/ (no deletion inside)
- Dry run default, prints counts and total size to be freed
- Verification: check presence of README.md, LICENSE, requirements.txt, config.json or config.example.json
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Set, Tuple

# --- Configuration ---
DEFAULT_WHITELIST_NAMES = {".git", ".venv", "venv", "env", "src"}
CLEAN_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "build",
    "dist",
    "*.spec",
    "*.log",
    "*.part",
    "*.ytdl",
    "*.dmp",
    "*.dump",
    "*.stackdump",
    ".DS_Store",
    "Thumbs.db",
]

VERIFY_FILES = ["README.md", "LICENSE", "requirements.txt"]
CONFIG_CANDIDATES = ["config.json", "config.example.json"]

# --- Helpers ---

def sizeof_fmt(num: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}PB"


@dataclass
class RemoveCandidate:
    path: Path
    is_dir: bool
    size: int = 0


def is_within_whitelist(path: Path, root: Path, whitelist: Set[str]) -> bool:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except Exception:
        return False
    for part in rel.parts:
        if part in whitelist:
            return True
    return False


def collect_candidates(root: Path, whitelist: Set[str], exclude_patterns: Iterable[str]) -> List[RemoveCandidate]:
    candidates: List[RemoveCandidate] = []
    exclude_set = set(exclude_patterns or [])

    for p in root.rglob("*"):
        name = p.name
        # Skip if inside whitelist
        if is_within_whitelist(p, root, whitelist):
            continue

        # Exclude by explicit glob patterns from user
        skip = False
        for pat in exclude_set:
            if p.match(pat):
                skip = True
                break
        if skip:
            continue

        # Directory patterns
        if p.is_dir():
            if name in {"__pycache__", "build", "dist"}:
                size = get_dir_size(p)
                candidates.append(RemoveCandidate(p, True, size))
            continue

        # File patterns
        for pat in ("*.pyc", "*.pyo", "*.pyd", "*.spec", "*.log", "*.part", "*.ytdl", "*.dmp", "*.dump", "*.stackdump", ".DS_Store", "Thumbs.db"):
            if p.match(pat) or name == pat:
                try:
                    size = p.stat().st_size
                except Exception:
                    size = 0
                candidates.append(RemoveCandidate(p, False, size))
                break
    return candidates


def get_dir_size(path: Path) -> int:
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except Exception:
                    pass
    except Exception:
        pass
    return total


def remove_path(p: Path, is_dir: bool) -> Tuple[bool, str]:
    try:
        if is_dir:
            shutil.rmtree(p)
        else:
            p.unlink()
        return True, ""
    except Exception as e:
        return False, str(e)


def remove_empty_dirs(root: Path, whitelist: Set[str]) -> Tuple[int, int]:
    removed_count = 0
    freed_bytes = 0
    # Walk bottom-up
    for d in sorted([p for p in root.rglob("*") if p.is_dir()], key=lambda x: -len(str(x))):
        # Skip whitelist
        if is_within_whitelist(d, root, whitelist):
            continue
        try:
            if not any(d.iterdir()):
                size = 0
                try:
                    size = get_dir_size(d)
                except Exception:
                    pass
                d.rmdir()
                removed_count += 1
                freed_bytes += size
        except Exception:
            continue
    return removed_count, freed_bytes


def verify_project(root: Path) -> List[str]:
    warnings: List[str] = []
    for fname in VERIFY_FILES:
        if not (root / fname).exists():
            warnings.append(f"Missing: {fname}")
    if not any((root / c).exists() for c in CONFIG_CANDIDATES):
        warnings.append("Missing: config.json or config.example.json")
    return warnings


def summarize_candidates(candidates: List[RemoveCandidate]) -> Tuple[int, int]:
    total_files = len(candidates)
    total_bytes = sum(c.size for c in candidates)
    return total_files, total_bytes


def prompt_confirm(prompt: str) -> bool:
    try:
        ans = input(prompt).strip().lower()
    except EOFError:
        return False
    return ans in {"y", "yes"}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project maintenance: dry-run by default. Use --force to actually delete.")
    parser.add_argument("--path", "-p", default=".", help="Project root path")
    parser.add_argument("--force", "-f", action="store_true", help="Actually perform deletions")
    parser.add_argument("--yes", "-y", action="store_true", help="Assume yes for confirmations when --force is used")
    parser.add_argument("--exclude", "-e", action="append", help="Glob pattern to exclude (can be given multiple times)")
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"Error: path not found: {root}")
        return 2

    whitelist = set(DEFAULT_WHITELIST_NAMES)

    print(f"Maintenance run at: {root}")
    print("Safety whitelist:", ", ".join(sorted(whitelist)))
    print("Dry-run mode:" if not args.force else "FORCE mode: will delete files")
    print()

    # 1. Verification
    warnings = verify_project(root)
    if warnings:
        print("Verification warnings:")
        for w in warnings:
            print(" - ", w)
        print()

    # 2. Collect candidates
    start = time.time()
    candidates = collect_candidates(root, whitelist, args.exclude or [])
    files_count, bytes_total = summarize_candidates(candidates)

    print(f"Found {files_count} candidate items to remove (total size {sizeof_fmt(bytes_total)})")
    if files_count:
        print()
        for c in candidates:
            typ = "DIR " if c.is_dir else "FILE"
            print(f"{typ:4} {c.path} ({sizeof_fmt(c.size)})")

    # 3. Dry-run summary
    print()
    if not args.force:
        print("This was a dry run. No files were deleted.")
        print("Run with --force to actually delete the above items (or use --exclude to skip patterns).")
        print(f"Scan time: {time.time() - start:.2f}s")
        return 0

    # 4. Confirm
    if not args.yes:
        ok = prompt_confirm("Proceed to delete the listed items? [y/N]: ")
        if not ok:
            print("Aborted by user.")
            return 0

    # 5. Perform deletion
    removed = 0
    removed_bytes = 0
    failures: List[Tuple[Path, str]] = []
    for c in candidates:
        # double-check whitelist
        if is_within_whitelist(c.path, root, whitelist):
            failures.append((c.path, "Inside whitelist"))
            continue
        success, err = remove_path(c.path, c.is_dir)
        if success:
            removed += 1
            removed_bytes += c.size
        else:
            failures.append((c.path, err))

    # Remove empty dirs
    empty_removed_count, empty_removed_bytes = remove_empty_dirs(root, whitelist)
    removed += empty_removed_count
    removed_bytes += empty_removed_bytes

    # Summary
    print()
    print(f"Deletion complete: {removed} items removed, freed {sizeof_fmt(removed_bytes)}")
    if failures:
        print(f"Failed to remove {len(failures)} items:")
        for p, e in failures:
            print(" - ", p, " -> ", e)

    print(f"Elapsed: {time.time() - start:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
