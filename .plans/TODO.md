# TODO

- [ ] Resolve the coverage threshold drift: `AGENTS.md` says 80, while `pyproject.toml`, CI, and `.plans/90-release.md` use 85.
- [ ] Decide whether release tags should create GitHub Releases automatically; if yes, add `.github/workflows/release.yml` or update `.plans/90-release.md` to remove the promise.
- [ ] Decide whether fixture e2e (`npx tui-test`) is a required CI/release gate; if yes, add Node setup and e2e execution to CI.
- [ ] Add a v2 coverage matrix to `.plans/20-v2-coverage.md`: screen module, stable API imports, fixture file, unit tests, e2e spec, mutating actions.
- [ ] Refresh old path references in v1 plans when next touched (`src/owa_tui/cal/`, `src/owa_tui/mail/screen.py`, old widget-kit names) so readers follow the live `src/owa_tui/screens/` layout.
- [ ] Add optional live-auth smoke tests only behind explicit gates (`OWA_TUI_LIVE_TESTS=1` or tool-specific equivalents).

- [x] Add optional live-auth e2e smoke run against real Graph — `e2e/live.test.ts`, gated behind `OWA_TUI_LIVE_E2E=1` (skipped by default; verified passing against live Graph and skipping in the fixture-mode suite). (2026-06-23)
- [x] Harden owa-tui screens/people.py Pilot coverage (64% → 89%): fetch worker (success/no-data/error), detail worker (success/no-token/error/cached), k/up nav, close-detail + focus-pane, _show_cached_detail pane/missing, overlay handlers, token mint
- [x] owa-todo e2e gaps: k/up nav + search-returning-results added to e2e/todo.test.ts; live complete-toggle PATCH path unit-tested (todo.py 99%) since fixture-mode e2e can't reach it
