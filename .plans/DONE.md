# Done

- [x] all tuis: emoji from list rows no longer bleed through the Esc/settings menu — `SettingsOverlay` background was the default ModalScreen 60% alpha (transparent in ansi mode), which composited the dimmed list behind it; emoji don't dim so they punched through. Set background to opaque `$background` (+ `&:ansi`). (2026-06-24)
- [x] mail tui: settings apply immediately — reading-pane mode change rebuilds the `#mail-layout` container live (preserving selection + shown body); split-ratio change resizes panes in place. (2026-06-24)
- [x] mail tui: scrolling to the last list item loads the next $skip page and appends it (de-duped by id; cursor held in place). (2026-06-24)
- [x] mail tui: folder panel — `FolderList` left pane, `tui_show_folders` setting (+ menu entry), `F` shortcut to toggle live, selecting a folder reloads the list scoped to it via `folder_messages_path`. (2026-06-24)
- [x] owa-tui: persist the active theme across tools and sessions in `~/.config/owa-tui/tui.json` (skipped in headless/fixture runs). (2026-06-24)
- [x] mail tui: j/k (line) and u/d (half-page) scroll the reading pane when it's focused, mirroring the list-pane keys. (2026-06-24)
- [x] mail tui: toggling read-status keeps the email selected instead of deselecting on list rebuild. (2026-06-24)
- [x] people tui: Esc returns to the list when viewing a person's detail (split mode), otherwise opens the menu; off-mode detail already handles its own Esc. (2026-06-24)
- [x] people tui: Enter on a focused person opens full details — already implemented (`action_open_detail`); covered by existing tests, no change needed. (2026-06-24)

- [x] Release-prep TODO closed (2026-06-23): coverage aligned to 85 everywhere; `release.yml` auto-creates GitHub Releases on `v*` tags; fixture e2e (`npx tui-test`) is now a required CI + release gate; v2 coverage matrix added; gated unit live-auth smoke added; README/AGENTS/RELEASING docs refreshed.
- [x] Reviewed and enriched all active `.plans/*.md` files with 2026-06-23 drift notes, hardening checklists, and release blockers.

- [x] Commit fixture-mode seam + tui-test e2e suite (src/owa_tui/fixtures.py, e2e/actions.test.ts, e2e/fixtures/) and the 3 bug fixes: graph menu crash, cal respond status persistence, cal declined/tentative verb typo (2026-06-19)
- [x] UI theme: optional transparent background (use native terminal background) (2026-06-22)
- [x] All TUIs: add left and top padding (2026-06-22)
- [x] All TUIs: configurable top row, default shows current profile + current user's UPN (2026-06-22)
- [x] owa-cal & owa-graph: 'q' should return to the tuis menu (like other tools), not quit to terminal (2026-06-22)
- [x] Resolve the coverage threshold drift: bumped `AGENTS.md` 80 → 85 to match `pyproject.toml`, CI, and `.plans/90-release.md`. (2026-06-23)
- [x] Release tags now auto-create GitHub Releases: added `.github/workflows/release.yml` (tag `v*` → gates → `uv build` → `softprops/action-gh-release`). PyInstaller binaries + PyPI publish deferred. (2026-06-23)
- [x] Fixture e2e is now a required CI gate: added Node 20 setup + `npm ci` + `npx tui-test` to `.github/workflows/ci.yml` (and the release gates). (2026-06-23)
- [x] Added the v2 coverage matrix to `.plans/20-v2-coverage.md` (screen → base / API imports / fixtures / unit tests / e2e spec / mutating actions). (2026-06-23)
- [x] Refreshed v1 plan path drift: each v1 plan already carries a "historical path drift" banner mapping to the live `src/owa_tui/screens/` layout; fixed the one runnable command in `11-v1-mail.md` (paths + `--cov-fail-under` 80 → 85). (2026-06-23)
- [x] Added the gated unit live-auth smoke: `src/tests/adapter/test_adapter.py::test_live_access_token_is_usable_jwt`, skipped unless `OWA_TUI_LIVE_TESTS=1`. (2026-06-23)
- [x] Add optional live-auth e2e smoke run against real Graph — `e2e/live.test.ts`, gated behind `OWA_TUI_LIVE_E2E=1` (skipped by default; verified passing against live Graph and skipping in the fixture-mode suite). (2026-06-23)
- [x] Harden owa-tui screens/people.py Pilot coverage (64% → 89%): fetch worker (success/no-data/error), detail worker (success/no-token/error/cached), k/up nav, close-detail + focus-pane, _show_cached_detail pane/missing, overlay handlers, token mint (2026-06-23)
- [x] owa-todo e2e gaps: k/up nav + search-returning-results added to e2e/todo.test.ts; live complete-toggle PATCH path unit-tested (todo.py 99%) since fixture-mode e2e can't reach it (2026-06-23)
- [x] ~/.config/owa-tui/tui.json should save config about whether background is transparent or not (2026-06-30)
