# TODO

- [x] Resolve the coverage threshold drift: bumped `AGENTS.md` 80 → 85 to match `pyproject.toml`, CI, and `.plans/90-release.md`. (2026-06-23)
- [x] Release tags now auto-create GitHub Releases: added `.github/workflows/release.yml` (tag `v*` → gates → `uv build` → `softprops/action-gh-release`). PyInstaller binaries + PyPI publish deferred. (2026-06-23)
- [x] Fixture e2e is now a required CI gate: added Node 20 setup + `npm ci` + `npx tui-test` to `.github/workflows/ci.yml` (and the release gates). (2026-06-23)
- [x] Added the v2 coverage matrix to `.plans/20-v2-coverage.md` (screen → base / API imports / fixtures / unit tests / e2e spec / mutating actions). (2026-06-23)
- [x] Refreshed v1 plan path drift: each v1 plan already carries a "historical path drift" banner mapping to the live `src/owa_tui/screens/` layout; fixed the one runnable command in `11-v1-mail.md` (paths + `--cov-fail-under` 80 → 85). (2026-06-23)
- [x] Added the gated unit live-auth smoke: `src/tests/adapter/test_adapter.py::test_live_access_token_is_usable_jwt`, skipped unless `OWA_TUI_LIVE_TESTS=1`. (2026-06-23)

- [x] Add optional live-auth e2e smoke run against real Graph — `e2e/live.test.ts`, gated behind `OWA_TUI_LIVE_E2E=1` (skipped by default; verified passing against live Graph and skipping in the fixture-mode suite). (2026-06-23)
- [x] Harden owa-tui screens/people.py Pilot coverage (64% → 89%): fetch worker (success/no-data/error), detail worker (success/no-token/error/cached), k/up nav, close-detail + focus-pane, _show_cached_detail pane/missing, overlay handlers, token mint
- [x] owa-todo e2e gaps: k/up nav + search-returning-results added to e2e/todo.test.ts; live complete-toggle PATCH path unit-tested (todo.py 99%) since fixture-mode e2e can't reach it
