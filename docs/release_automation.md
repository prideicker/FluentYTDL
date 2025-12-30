# Release Automation (Overview)

This document describes the CI-driven Windows-only release automation for FluentYTDL.

Key points:
- Tools are downloaded at build time (not stored in the repository). Use `scripts/fetch_tools.ps1` (it requires checksum by default; pass `-AllowNoChecksum` to override).
- The packaging script `scripts/package_v2.ps1` expects tools to be available in `assets/bin`.
- CI workflow triggers on tag `v*` and performs packaging on Windows runner.

CI usage example (env variables):
- `TOOLS_URL` — direct URL to the tools zip
- `TOOLS_REPO` and `TOOLS_RELEASE_TAG` — optional to resolve asset by release tag via GitHub API (requires `GITHUB_TOKEN` if tag is private)
- `TEST_UPLOAD_PAT` — repository secret used by the publish job to upload Release assets

Notes:
- The CI release workflow is split into two jobs: `build` (runs on Windows to create artifacts and run smoke tests) and `publish` (runs on Ubuntu and uses `TEST_UPLOAD_PAT` to create the GitHub Release and upload artifacts).
- Build produces `release/*.zip` and `release/*.sha256`, and a JSON artifact metadata file `release/<name>.artifact.json` containing `zip` path, `version`, `arch`, etc., which can be consumed by downstream steps.
