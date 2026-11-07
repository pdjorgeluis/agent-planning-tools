# Changelog

## 0.1.0

- Shared `aptlib` (config, dotenv loader, backends ladder, log rotation).
- Metis (pre-planning consultant) and Momus (spec reviewer) CLIs.
- Installer with tool selection, five targets, manifest, backups, uninstall
  (uninstall also removes bytecode caches under installed folders).
- Privacy scanner and `scripts/check.sh`.
- `docs/TARGETS.md`: install locations checked against vendor documentation on
  2026-11-07, with unverified items marked.
- Tested on Hermes only; other targets follow the vendors' documented
  conventions and are untested.
