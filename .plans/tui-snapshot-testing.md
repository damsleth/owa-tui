# TUI snapshot testing

_Created 2026-09-22_ · todo #7 ("automated TUI design testing")

## Goal

Catch unintended visual/layout changes (header, panes, split ratios,
themes) automatically, in the existing pytest run, without a browser or
manual screenshots.

## Problem

Current tests assert behaviour, not appearance: pilot tests check widget
state (`src/tests/test_home_pilot.py`), tui-test checks that text is
visible (`e2e/*.test.ts`). A layout regression (pane widths, header
overlap, theme colours) passes both.

## Approach (minimal)

`pytest-textual-snapshot` is already importable in the venv but is not
declared. Use its `snap_compare` fixture: it runs the app under Pilot,
renders an SVG, and diffs against a committed SVG.

1. Declare `pytest-textual-snapshot` in `pyproject.toml` dev deps (lock it).
2. `src/tests/snapshots/test_snapshots.py`: one parametrised test over the
   screens that have fixtures (`e2e/fixtures/*.json`): set
   `OWA_TUI_FIXTURES`, build `OwaTuiApp`, `push_tool(key)`, `snap_compare`
   at a fixed `terminal_size=(120, 40)`. Start with home, mail, people, drive.
3. Determinism: patch `owa_tui.__version__` (AppHeader renders it, else
   every release churns all SVGs) and freeze `date.today` for sched.
4. Commit the SVGs under `src/tests/snapshots/__snapshots__/`; document
   `pytest --snapshot-update` in `src/tests/AGENTS.md` (create; the file
   AGENTS.md refers to does not exist).
5. CI already runs pytest; no workflow change needed.

Scope out: pixel diffs across themes and sizes (add a second parametrised
size or theme only if the user asks).

## Files

- `pyproject.toml`, `uv.lock`
- `src/tests/snapshots/test_snapshots.py` (+ `__snapshots__/`)
- `src/tests/AGENTS.md`

## Verification

- `.venv/bin/python -m pytest -q src/tests/snapshots` twice: passes and is stable.
- Change a split ratio default; the test fails with an HTML diff report.

## Open questions

- Does "design testing" mean regression snapshots (this plan), or checking
  the design across themes (ansi-dark/light/transparent) and terminal sizes?
- Are committed SVGs acceptable in the repo (a few hundred KB)?
- Which screens first: all 13 registered tools, or the four above?
