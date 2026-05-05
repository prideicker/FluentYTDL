# FluentYTDL — Copilot Instructions

> Auto-generated from `docs/RULES_EN.md` by `scripts/sync_rules.py`
>
> Companion documents (read on demand):
> - `docs/ARCHITECTURE_EN.md` — Architecture with 6 parsing flow details
> - `docs/YTDLP_KNOWLEDGE_EN.md` — Empirical yt-dlp troubleshooting knowledge

# FluentYTDL Development Rules

> [中文版](RULES.md)
>
> This is the source file for AI rule generation. CLAUDE.md, AGENTS.md, and .github/copilot-instructions.md are generated from this file by `scripts/sync_rules.py`.

## 1. Project Identity

- **Name**: FluentYTDL — Professional YouTube/video downloader
- **Language**: Python 3.10+
- **UI Framework**: PySide6 (Qt6) + QFluentWidgets (Fluent Design)
- **Download Engine**: yt-dlp CLI subprocess (NOT Python API)
- **Media Processing**: FFmpeg
- **Codebase**: 148 .py files, ~50k LOC, `src/fluentytdl/` package
- **Platform**: Windows primary, cross-platform aspirational

## 2. Architecture Rules

### Layer Separation

```
UI Layer (ui/)
  ↓ depends on
Service Layer (auth/, youtube/, download/, processing/, storage/)
  ↓ depends on
Core Infrastructure (core/)
  ↓ depends on
Foundation (utils/, models/)
```

- **UI must NOT call yt-dlp directly** — go through `youtube_service`
- **Services must NOT import from ui/** — communicate via Qt Signals
- **Models are self-contained** — no circular dependencies

### Singletons

The project uses singleton pattern extensively. Key singletons: `config_manager`, `download_manager`, `auth_service`, `cookie_sentinel`, `youtube_service`, `pot_manager`, `task_db`.

When creating a new singleton, document it in this list.

### Qt Signal/Slot

All UI-backend communication MUST use Qt Signal/Slot mechanism. Never call backend methods directly from UI event handlers — emit a signal instead.

### Six Parsing Modes

The project supports 6 distinct parsing modes. See `docs/ARCHITECTURE_EN.md` Section 3 for the complete flow of each mode:

1. **Video** — standard single video download
2. **VR** — VR video with `android_vr` client, EAC conversion
3. **Channel** — channel tab listing with lazy loading
4. **Playlist** — playlist with batch operations
5. **Subtitle** — standalone subtitle download (lightweight extract)
6. **Cover** — standalone thumbnail download (direct or lightweight)

When modifying download logic, consider the impact on ALL 6 modes.

## 3. Code Style

### Ruff (enforced)

```toml
target-version = "py310"
line-length = 100
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501"]  # long lines allowed
```

- `F401` ignored in `__init__.py` files (re-exports are intentional)
- isort: `known-first-party = ["fluentytdl"]`

### Pyright (advisory)

```toml
pythonVersion = "3.10"
# Many report* settings are relaxed — do not add new type:ignore without discussion
```

### UI Rules

- **MUST** use QFluentWidgets (FluentWindow, InfoBar, etc.)
- **NEVER** use raw QMessageBox, QDialog, or QWidget for new UI
- Use QPainter delegates for list items (avoids QWidget overhead for large lists)
- Dark mode support: use `CustomInfoBar`, not raw InfoBar

### File Naming

- Snake_case for all Python files
- One class per file preferred (especially in ui/components/)
- Prefix `_` for private module-level functions

## 4. yt-dlp Integration Rules [CRITICAL]

These rules are hard-won from production issues. Violating them WILL cause user-facing bugs.

1. **NEVER force `player_client`** — trust yt-dlp's default strategy (tv → web_safari → android_vr)
2. **NEVER enable `sleep_interval`** — causes signed URL expiry → HTTP 403
3. **NEVER use `--cookies-from-browser`** — causes DPAPI file lock on Windows
4. **Language format injection** — `-S lang:xx` cannot override `language_preference=10`; use `_inject_language_into_format()`
5. **Validate file size on non-zero exit** — Windows `.part-Frag` deletion fails but download is complete
6. **Sync POT plugins to exe directory** — compiled yt-dlp cannot discover plugins via PYTHONPATH
7. **TUN mode: no proxy env vars** — injecting `HTTPS_PROXY` causes double-proxying
8. **web_music needs `disable_innertube=True`** — InnerTube challenges broken for that client
9. **BCP-47 alias expansion** — `zh-Hans` must match `zh-CN`, `zh-SG`, etc.
10. **Sandbox download model** — temp dir per task, move on success, sweep on cancel

See `docs/YTDLP_KNOWLEDGE_EN.md` for the full empirical knowledge base.

## 5. Cookie System Rules

- `CookieSentinel` manages the single `bin/cookies.txt` lifecycle
- **Lazy cleanup**: NEVER delete old cookies until new extraction succeeds
- **Required cookies**: SID, HSID, SSID, SAPISID, APISID
- **Chromium v130+**: needs admin for App-Bound Encryption decryption
- **403 recovery**: auto-detect cookie expiry keywords, prompt refresh
- **JSON cookie files**: reject with warning (yt-dlp expects Netscape format)

## 6. Post-Processing Pipeline Order

1. `SponsorBlockFeature` — sponsorblock_remove/mark
2. `MetadataFeature` — FFmpegMetadata postprocessor
3. `SubtitleFeature` — bilingual merge, embed, cleanup
4. `ThumbnailFeature` — embed via AtomicParsley (MP4) > FFmpeg (MKV) > mutagen (audio)
5. `VRFeature` — EAC→Equi conversion + spatial metadata (VR mode only)

## 7. Testing Rules

- pytest >= 7.0
- Test files in `tests/` directory
- **No conftest.py yet** — each test does its own `sys.path` setup
- 2 tests require GUI (QApplication) — cannot run in headless CI
- 1 test has no assertions (test_error_parser.py) — needs fixing
- CI uses `continue-on-error: true` on all checks — nothing blocks merges
- When adding tests: prefer plain pytest functions over unittest.TestCase

## 8. What NOT To Do

- **Do not** use raw Qt widgets in UI (must use QFluentWidgets)
- **Do not** import yt-dlp as Python library (always use CLI subprocess)
- **Do not** use `cookies_from_browser` (DPAPI lock)
- **Do not** force sleep intervals (signed URL expiry)
- **Do not** create new singletons without documenting in Section 2
- **Do not** add dependencies without updating `pyproject.toml`
- **Do not** commit `config.json`, credentials, API tokens, or cookies
- **Do not** use `type:ignore` without discussion
- **Do not** bypass the sandbox download model for video downloads

## 9. Companion Documents

| Document | Purpose |
|----------|---------|
| `docs/ARCHITECTURE_EN.md` | Current architecture with 6 parsing flow details |
| `docs/YTDLP_KNOWLEDGE_EN.md` | Empirical yt-dlp troubleshooting knowledge |
| `docs/RULES.md` | Chinese version of this document |
| `CONTRIBUTING.md` | Contribution guidelines |
| `SECURITY.md` | Security policy |

## 10. Build & Release Rules

### Version Management

- **Source of truth**: `VERSION` file (project root)
- **Do not manually edit** version numbers in `__init__.py` or `pyproject.toml`
- `build.py` auto-syncs version to all files before building

### Version Prefixes

| Prefix | Meaning | Distribution | GitHub Release |
|--------|---------|-------------|---------------|
| `v-` | Stable release | GitHub Release | Latest |
| `pre-` | Pre-release candidate | GitHub Release | Pre-release |
| `beta-` | Test/beta build | Project lead distributes in groups/channels | Not published |

Format: `{prefix}-{major}.{minor}.{patch}` — e.g., `v-3.0.18`, `pre-3.0.18`, `beta-0.0.5`

**PEP 440 / Inno Setup / PE resources only accept numeric versions** (e.g., `3.0.18`). The build script automatically extracts the numeric part from `v-3.0.18`.

### AI Agent: Release Workflow

**Stable release (v-)**:
1. `python scripts/version_manager.py set v-3.0.18`
2. `python scripts/version_manager.py check` (verify consistency)
3. `git add -A && git commit -m "release: v-3.0.18"`
4. `git tag v-3.0.18`
5. `git push && git push --tags`
6. CI auto-triggers `release.yml` → build → GitHub Release (Latest)

**Pre-release (pre-)**:
1. `python scripts/version_manager.py set pre-3.0.18`
2. Same steps 2-5 above
3. CI auto-triggers → GitHub Release (Pre-release)

**Beta (beta-)**:
1. `python scripts/version_manager.py set beta-0.0.5`
2. Same steps 2-5 above
3. CI auto-triggers → Artifacts only (no GitHub Release)
4. Project lead downloads from GitHub Actions Artifacts

### Local Build

- GUI: `python scripts/build_gui.py` → enter version → click Build
- CLI: `python scripts/build.py --target all --version v-3.0.18`
- `--target` options: `all`, `7z` (or `full`), `setup`

### Notes

- `build.py` syncs version to all files (VERSION, pyproject.toml, __init__.py, .iss) before building
- beta builds only produce Artifacts, not GitHub Releases
- Output filenames include full prefix: `FluentYTDL-v-3.0.18-win64-full.7z`
