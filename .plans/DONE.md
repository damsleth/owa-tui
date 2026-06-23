# Done

- [x] Release-prep TODO closed (2026-06-23): coverage aligned to 85 everywhere; `release.yml` auto-creates GitHub Releases on `v*` tags; fixture e2e (`npx tui-test`) is now a required CI + release gate; v2 coverage matrix added; gated unit live-auth smoke added; README/AGENTS/RELEASING docs refreshed.
- [x] Reviewed and enriched all active `.plans/*.md` files with 2026-06-23 drift notes, hardening checklists, and release blockers.

- [x] Commit fixture-mode seam + tui-test e2e suite (src/owa_tui/fixtures.py, e2e/actions.test.ts, e2e/fixtures/) and the 3 bug fixes: graph menu crash, cal respond status persistence, cal declined/tentative verb typo (2026-06-19)
- [x] UI theme: optional transparent background (use native terminal background) (2026-06-22)
- [x] All TUIs: add left and top padding (2026-06-22)
- [x] All TUIs: configurable top row, default shows current profile + current user's UPN (2026-06-22)
- [x] owa-cal & owa-graph: 'q' should return to the tuis menu (like other tools), not quit to terminal (2026-06-22)
