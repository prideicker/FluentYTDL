#!/usr/bin/env python3
"""Generate per-AI rule files from docs/RULES_EN.md source of truth."""

import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
RULES_SOURCE = PROJECT_ROOT / "docs" / "RULES_EN.md"

TARGETS = {
    "CLAUDE.md": (
        "# FluentYTDL — Claude Code Rules\n"
        "\n"
        "> Auto-generated from `docs/RULES_EN.md` by `scripts/sync_rules.py`\n"
        ">\n"
        "> Companion documents (read on demand):\n"
        "> - `docs/ARCHITECTURE_EN.md` — Architecture with 6 parsing flow details\n"
        "> - `docs/YTDLP_KNOWLEDGE_EN.md` — Empirical yt-dlp troubleshooting knowledge\n"
        "\n"
    ),
    "AGENTS.md": (
        "# FluentYTDL — AI Agent Rules\n"
        "\n"
        "> Auto-generated from `docs/RULES_EN.md` by `scripts/sync_rules.py`\n"
        ">\n"
        "> Companion documents (read on demand):\n"
        "> - `docs/ARCHITECTURE_EN.md` — Architecture with 6 parsing flow details\n"
        "> - `docs/YTDLP_KNOWLEDGE_EN.md` — Empirical yt-dlp troubleshooting knowledge\n"
        "\n"
    ),
    ".github/copilot-instructions.md": (
        "# FluentYTDL — Copilot Instructions\n"
        "\n"
        "> Auto-generated from `docs/RULES_EN.md` by `scripts/sync_rules.py`\n"
        ">\n"
        "> Companion documents (read on demand):\n"
        "> - `docs/ARCHITECTURE_EN.md` — Architecture with 6 parsing flow details\n"
        "> - `docs/YTDLP_KNOWLEDGE_EN.md` — Empirical yt-dlp troubleshooting knowledge\n"
        "\n"
    ),
}


def main():
    if not RULES_SOURCE.exists():
        print(f"Error: source file not found: {RULES_SOURCE}", file=sys.stderr)
        sys.exit(1)

    rules = RULES_SOURCE.read_text(encoding="utf-8")

    for rel_path, header in TARGETS.items():
        target = PROJECT_ROOT / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        content = header + rules
        target.write_text(content, encoding="utf-8")
        print(f"  wrote {rel_path}")

    print(f"\nDone. Generated {len(TARGETS)} files from {RULES_SOURCE.name}")


if __name__ == "__main__":
    main()
