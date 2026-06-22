# TODO

- [ ] Add optional live-auth e2e smoke run against real Graph (deferred — flaky/CI-hostile; gate behind an env flag, separate from fixture-mode suite)
- [x] Harden owa-tui screens/people.py Pilot coverage (64% → 89%): fetch worker (success/no-data/error), detail worker (success/no-token/error/cached), k/up nav, close-detail + focus-pane, _show_cached_detail pane/missing, overlay handlers, token mint
- [x] owa-todo e2e gaps: k/up nav + search-returning-results added to e2e/todo.test.ts; live complete-toggle PATCH path unit-tested (todo.py 99%) since fixture-mode e2e can't reach it
