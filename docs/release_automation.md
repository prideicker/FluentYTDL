# Release Automation (Overview)

This document describes the CI-driven Windows-only release automation for FluentYTDL.

Key points:
- Tools are downloaded at build time (not stored in the repository). Use `scripts/fetch_tools.ps1`.
- The packaging script `scripts/package_v2.ps1` expects tools to be available in `assets/bin`.
- CI workflow triggers on tag `v*` and performs packaging on Windows runner.

Scripts:
- `scripts/fetch_tools.ps1` — download tools zip and checksum from a URL or GitHub Release and unpack to `assets/bin`.

CI usage example (env variables):
- `TOOLS_URL` — direct URL to the tools zip
- `TOOLS_RELEASE_TAG` and `TOOLS_REPO` — optional to resolve asset by release tag via GitHub API (requires `GITHUB_TOKEN` if tag is private)

For full CI integration, see `.github/workflows/release.yml`.
