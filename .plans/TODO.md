# TODO

- [x] Add optional live-auth e2e smoke run against real Graph — `e2e/live.test.ts`, gated behind `OWA_TUI_LIVE_E2E=1` (skipped by default; verified passing against live Graph and skipping in the fixture-mode suite). (2026-06-23)
- [x] Harden owa-tui screens/people.py Pilot coverage (64% → 89%): fetch worker (success/no-data/error), detail worker (success/no-token/error/cached), k/up nav, close-detail + focus-pane, _show_cached_detail pane/missing, overlay handlers, token mint
- [x] owa-todo e2e gaps: k/up nav + search-returning-results added to e2e/todo.test.ts; live complete-toggle PATCH path unit-tested (todo.py 99%) since fixture-mode e2e can't reach it
