"""FluentYTDL package."""

__all__ = ["__version__"]


def _read_version() -> str:
    """Read version from VERSION file, falling back to importlib.metadata.

    VERSION file stores the full prefixed format like "v-3.0.18" / "pre-3.0.18" / "beta-0.0.5".
    Priority: VERSION file > importlib.metadata > default.
    """
    import sys
    from pathlib import Path

    # Candidate paths for VERSION file
    candidates = [
        Path(__file__).resolve().parents[2] / "VERSION",  # dev: src/fluentytdl → root
        Path(__file__).resolve().parents[1] / "VERSION",  # alt layout
    ]
    # PyInstaller frozen: VERSION is bundled to _internal/ or exe dir
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.insert(0, exe_dir / "VERSION")
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        if str(meipass):
            candidates.insert(0, meipass / "VERSION")

    for p in candidates:
        if p.is_file():
            v = p.read_text(encoding="utf-8").strip()
            if v and v != "0.0.0-dev":
                return v

    # Fallback: pip install -e . reads from pyproject.toml metadata
    try:
        from importlib.metadata import version

        return version("FluentYTDL")
    except Exception:
        pass

    return "0.0.0-dev"


__version__ = _read_version()
