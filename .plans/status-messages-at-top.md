# status messages at the top overlaying the header row

_Created 2026-09-22_ · todo #6

## Goal

Errors/warnings/status text appear at the top of the screen, on the
`AppHeader` identity row (row 3: `v<version> · profile · upn`), instead of
in the `StatusBar` docked at the bottom.

## Problem

Five screens compose their own `StatusBar` with two different ids:
`src/owa_tui/screens/people.py:404` and `mail.py:485` (`#status-bar`),
`base/screen.py:479`, `base/grid.py:217`, `base/thread.py:189`
(`#owa-status-bar`). Each drives it from its own reactive (`status` /
`_status`). `AppHeader` (`widgets/app_header.py`) is `dock: top; height: 3`
and renders identity itself. `App.notify` toasts (used in `push_tool`) land
bottom-right.

## Approach (minimal)

Move the widget, not the wiring: keep every `StatusBar` instance and
watcher as is; relocate it with CSS only.

1. `src/owa_tui/widgets/base.tcss` / `StatusBar.DEFAULT_CSS`:
   `dock: top; layer: status; margin-top: 2; height: 1;` (+ `layers: base status`
   on `Screen`). The bar now paints over header row 3.
2. `AppHeader.render`: stop appending the identity tail on row 3 when a status
   is showing — simplest is to right-align the tail and left-align the status
   so they share the row; if they collide, drop the tail (identity is also in
   the Esc menu). Decide per open question below.
3. Optional, same PR: `ToastRack { dock: top; }` so `notify()` toasts match.
4. Remove the bottom-row expectation from any pilot/e2e test that asserts
   position (grep `status-bar` in `src/tests`, `e2e/*.test.ts`; tui-test
   asserts on text only, so most survive).

## Files

- `src/owa_tui/widgets/base.tcss`, `src/owa_tui/widgets/status_bar.py`
- `src/owa_tui/widgets/app_header.py` (only if the tail must yield)
- `src/tests/widgets/*` for the header/status render

## Verification

- `.venv/bin/python -m pytest -q --cov --cov-fail-under=85`
- `OWA_TUI_FIXTURES=e2e/fixtures owa-tui --tool mail`: trigger `r` and a
  failed search; message shows on row 3, list no longer loses its bottom row.
- `npx tui-test` (fixture e2e).

## Open questions

- Overlay row 3 (hides `v<version> · profile · upn` while a message shows)
  or add a 4th header row (costs one line of list height everywhere)?
- Should `notify()` toasts move too, or only the StatusBar?
- Should messages auto-clear after N seconds once they are on the header row?
