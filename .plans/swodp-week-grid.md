# swodp week grid

_Created 2026-09-23_

## Goal

`owa-tui --tool swodp`: one week of SWODP time cards as an editable grid
(row per task/category, column per weekday, sum row and sum column), vim
navigation with a visible cell cursor, a "fill from calendar" action that
derives rows from the `swon` Outlook calendar, and an optional LLM assist.
Writes only ever produce or change **Pending** cards. `submit` stays a manual
step in the SWODP portal (or `owa-swodp submit`), never a TUI binding.

It is a TUI front-end on `owa-swodp`, nothing more. No new HTTP, no new auth,
no matching logic that does not already exist in the CLI or the
`cj-weekly-review` skill.

Reference shape (what the grid must render), week 38 as filed 2026-09-22:

```
Kort                    man   tir   ons   tor   fre   lør   søn   sum
NOCOS T1PRJTSK4228809   7.5   7     2     7.5   7.5   0     0     31.5
UNE   T1PRJTSK4231733   0     1     4     0     0     0     0     5
Admin                   3     0     0     0     0     0     0     3
per dag                 10.5  8     6     7.5   7.5   0     0     39.5
```

## Constraints (from the code, not negotiable)

- **Import boundary.** `owa_swodp` is not in the stable list in `AGENTS.md`,
  but `screens/ado.py` already imports `owa_ado.api/auth/config/resources`, so
  the precedent is one adapter module per tool that imports the tool's own
  package. Import `owa_swodp.service` and `owa_swodp.session` from a single
  `screens/swodp/adapter.py`; nothing else touches them. Add `owa_swodp` to the
  boundary list in `AGENTS.md` in the same PR.
- **The session is a browser capture.** `owa_swodp.session.capture(instance)`
  launches Edge, reads cookies + `g_ck`, closes Edge, and returns a
  `SwodpSession` held in memory. Seconds, not milliseconds. Capture **once per
  screen lifetime**, keep the session on the screen, re-capture only on
  exit 11 (`r` after an auth error). Never capture per keypress or per fetch.
- **Cards come back range-wide.** `service.week_cards(session, week_start,
  weeks=3)` returns cards for a window around the Monday. Filter on
  `week_starts_on == week_start` client-side, exactly as the skill does.
- **`allocations` 403s on this account.** Task numbers for new rows come from
  the cards already visible in the range (`task.number`), never from
  `allocations`. Treat a 403 there as "no picker", not as an error.
- **Row-plan contract** (`service.validate_write_rows`): exactly one of
  `taskNumber` / `category`, seven Monday-first numbers in `0..24`, non-empty
  `description`, optional `remove` / `split` / `new`. `category` takes the raw
  value from `service.categories` (`admin`, not `Admin`). The TUI builds
  exactly this list and hands it to `service.write_week(session, week_start,
  rows)`. It does **not** reimplement matching or the three-step
  create/PATCH/verify dance.
- **Terminal states are read-only.** `Submitted`, `Approved`, `Processed`
  rows render dimmed and refuse edits. A Pending write against one is skipped
  server-side with exit 15 anyway; the TUI should not let the cursor edit it in
  the first place.
- **Calendar reads go through the existing seam.** Token via
  `adapter.access_token_for(config, tool_name="owa-cal", audience="outlook")`,
  events via `owa_cal.api` / `owa_cal.events`, the same path `screens/cal/fetch.py`
  uses. Profile is pinned to `swon` (Kim's master calendar per ledger pref);
  make it a config key, not a constant.
- **No `rtk`, no subprocess to `owa-swodp`.** The skills warn that filtering
  proxies dropped rows on `cards`. The TUI is in-process, so this is moot, but
  do not "simplify" to shelling out either.
- **Fixture seam.** `OWA_TUI_FIXTURES=<dir>` with `swodp.json` (the raw
  `cards` array; a real sample is in this plan's Notes) and `cal.json` must
  drive the whole screen offline, including fill-from-calendar and a dry-run
  write. Default tests never touch Edge or ServiceNow.

## Design

### Screen

`screens/swodp/screen.py`: `SwodpScreen(OwaGridScreen)`. Reuse `base/grid.py`
for DataTable, `hjkl`, `r`, `Esc` menu, status bar, worker plumbing. Extend it
in the subclass, do not fork it:

- **Cursor.** `DataTable.cursor_type = "cell"`, `show_cursor = True`. The
  "blinking" ask is the DataTable cursor style plus a `set_interval(0.5)` that
  toggles a `blink` CSS class on the table (`.blink > .datatable--cursor
  { background: $accent 30% }`). One interval, one class, no custom widget.
  Drop the interval if Textual's built-in cursor reads clearly enough in the
  first manual test; the requirement is *visible focus*, not blinking per se.
- **Grid data.** Columns `man tir ons tor fre lør søn sum`. One row per card,
  label `"<Kort> <task.number>"` or the category display name, plus a final
  computed `per dag` row. Cells are decimals with one place, `0` rendered
  dim. `cell_style`: terminal-state rows `dim`, Pending rows default, dirty
  (locally edited, unwritten) cells `bold yellow`, sums `bold`.
- **Week navigation.** `[` / `]` previous / next ISO week, `t` this week.
  Header row 1 shows `Uke <n> · <mandag>–<søndag> · <instance>`. Each change
  refetches cards for that Monday through the held session.
- **Edit.** `Enter` or `i` on a Pending numeric cell opens a one-line `Input`
  in the status row (pattern: `OwaListScreen.action_search`), accepts
  `0..24` in steps of `0.5` (`0.25` allowed, matches SWODP), writes back into
  the in-memory plan and marks the cell dirty. `x` zeroes a cell. `D` on a
  row toggles `remove` (renders struck-through). `a` adds a row: picker of
  `task.number`s seen in the range + raw categories from
  `service.categories`; new row gets `"new": true` only if a terminal-state
  card with the same identity already exists in this week (that is the one
  case where SWODP needs it, per `docs/swodp.md`). `e` edits the row
  description (required by SWODP; an empty one is refused before write).
- **Write.** `w` shows a confirm modal listing the diff (`created` /
  `updated` / `remove`, per row, per day delta) and the target instance, then
  calls `service.write_week` in a worker and refetches. The confirm text is
  the same table the CLI would print; nothing is written without it. No
  `submit` binding, deliberately. Status row after write: `N created, M
  updated, K skipped` straight from the `results[].action` values.
- **Fill from calendar.** `c` fetches `swon` events for the visible week,
  drops all-day and `showAs == free`, keeps events that carry a category, maps
  category → row identity through a config map, sums hours per day, rounds to
  nearest `0.5`, and merges into the plan as dirty cells (overwrite a Pending
  row's day only when the row is empty for that day or the user confirms;
  never touch terminal rows). The mapping is `swodp.category_map` in
  `~/.config/owa-tui/tui.json`, seeded on first run with the four in use:

  ```json
  {"NC NOCOS": {"taskNumber": "T1PRJTSK4228809", "description": "NOCOS forvaltning"},
   "UNE 4LYF": {"taskNumber": "T1PRJTSK4231733", "description": "UNE"},
   "CC ADM":   {"category": "admin",            "description": "Intern"},
   "CC LUNCH": null}
  ```

  `null` means ignore. An event whose category is not in the map lands in a
  `?`-row that cannot be written; the status row says which categories are
  unmapped so the user extends the map. This is exactly cj-weekly-review Step
  4b in code; keep the numbers identical (nearest 0.5, no padding toward 7.5).
- **Diff view.** Fill-from-calendar and manual edits both leave the grid in a
  dirty state; `d` toggles a second column group showing `card / calendar /
  delta` for the cursor row, so the user sees *why* a cell changed before `w`.
  This can slip to a later PR; the dirty styling alone is enough for v1.

### Adapter

`screens/swodp/adapter.py`: the only file importing `owa_swodp`.

```python
def capture(instance) -> SwodpSession            # wraps session.capture, maps CdpError/exit 11
def week(session, monday) -> list[dict]          # week_cards + client-side week filter
def categories(session) -> dict[str, str]        # display -> raw
def write(session, monday, rows) -> list[dict]   # validate_write_rows, then write_week
```

All blocking; called via `asyncio.to_thread` from the screen like
`cal/fetch.py`. Fixture short-circuit first in each, before any session use.

`screens/swodp/plan.py`: pure functions, no Textual, unit-tested:

```python
cards_to_grid(cards, monday) -> GridData + row identities
grid_to_rows(grid_state) -> list[row]            # only dirty rows, contract shape
events_to_hours(events, category_map) -> {identity: [7 floats]}   # nearest 0.5
diff(cards, rows) -> list[str]                   # lines for the confirm modal
```

### Entry points

- `owa-tui --tool swodp` is the real entry point; register `swodp` /
  `"Timesheet (SWODP)"` in `screens/__init__._bootstrap_screens`.
- `owa-swodp tui` lives in owa-tools and **cannot import owa-tui** (one-way
  dependency). If wanted at all, it is a three-line shim in `owa_swodp/cli.py`:
  `shutil.which("owa-tui")` → `os.execvp("owa-tui", ["owa-tui", "--tool",
  "swodp"])`, else print the install hint and exit 2. Separate PR in owa-tools;
  not required for this plan to ship.

### LLM assist (phase 3, optional)

`?` opens a prompt. The model gets the week's calendar events, the current
grid, the category map, and (if present) the 🪵 lines from that week's daily
notes under `~/brain/notes/90-journal/`, and must answer with a row-plan JSON
array plus one line of reasoning per changed cell. The TUI validates the array
with `validate_write_rows`, shows it as a dirty diff, and the user still goes
through `w`. Implementation: shell out to `claude -p --model haiku
--output-format json` with a strict system prompt; no SDK dependency, no
API key handling in owa-tui. Off unless `swodp.llm = true` in `tui.json`.
Skip entirely if fill-from-calendar already gets the week right nine times
out of ten, which the first month of use will tell.

## Steps

- [x] `screens/swodp/plan.py` + `src/tests/swodp/test_plan.py`: cards→grid,
      grid→rows, events→hours (rounding, ignore-map, unmapped bucket), diff.
      Fixture data: the week-38 `cards` sample below and a `cal.json` of the
      19 backfilled events from 2026-09-14..22.
- [x] `screens/swodp/adapter.py`: capture/week/categories/write with fixture
      seam; map `CdpError` and exit-11 to a status-row hint that names
      `owa-swodp setup --instance <x>`.
- [x] `screens/swodp/screen.py`: read-only grid first (`OwaGridScreen`
      subclass, week nav, cursor, terminal-state dimming, sums). Register in
      `_bootstrap_screens`. Manual check against live prod, read only.
- [x] Editing: cell input, `x`, `a`, `e`, `D`, dirty styling, description
      guard.
- [~] `w` with confirm modal and `write_week`; verify by refetch. (built and
      tested in fixture mode; the first live write is still to do.) First live
      write against a week that already has Pending cards, one row, then
      `owa-swodp cards` from the shell to cross-check (the skill's snapshot /
      one row / verify rule).
- [x] `c` fill-from-calendar with `swodp.category_map` in `tui.json`, seeded
      defaults, unmapped-row handling.
- [x] `AGENTS.md`: add `owa_swodp` to the import list; `docs/`: one page with
      the key table. `CHANGELOG.md` entry.
- [x] tui-test e2e: open, navigate, edit one cell, `w` in fixture mode, assert
      the confirm text and the post-write status line.
- [ ] (owa-tools, separate) `owa-swodp tui` exec shim.
- [ ] (later, only if needed) `d` diff columns; LLM assist.

## Verification

```bash
.venv/bin/ruff check .
.venv/bin/python -m compileall -q src
.venv/bin/python -m pytest -q --cov --cov-fail-under=85
OWA_TUI_FIXTURES=e2e/fixtures owa-tui --tool swodp    # offline: nav, edit, c, w
npx tui-test
owa-tui --tool swodp                                   # live, read-only pass first
owa-swodp cards --week-start <mandag>                  # bare binary, cross-check after any live write
```

## Open questions

- Grid rows for **all** cards in the 3-week range (like the portal's list) or
  only the selected week? Plan assumes selected week, with `[`/`]` to move.
- Should `c` be allowed to *lower* an existing Pending cell, or only fill empty
  ones? Plan: fill empty by default, overwrite behind a confirm.
- `0.25` granularity: SWODP accepts it, the skill rounds to `0.5`. Keep the
  editor at `0.25` and the calendar fill at `0.5`?
- Is the blink interval worth the redraws, or does the DataTable cursor style
  already read as focus? Decide after the first read-only build.

## Notes

`owa-swodp cards --week-start 2026-09-14` on 2026-09-22 (Pending, right after
`write`), the fixture seed:

```json
[{"task.number":"T1PRJTSK4228809","category":"Project/Project Task","state":"Pending",
  "week_starts_on":"2026-09-14","monday":"7.5","tuesday":"7","wednesday":"2","thursday":"7.5",
  "friday":"7.5","saturday":"0","sunday":"0","total":"31.5",
  "comments":"NOCOS forvaltning: prodsetting 14.09, 18648 nav-repair, ADO-triage, TechCon26"},
 {"task.number":"T1PRJTSK4231733","category":"Project/Project Task","state":"Pending",
  "week_starts_on":"2026-09-14","monday":"0","tuesday":"1","wednesday":"4","thursday":"0",
  "friday":"0","saturday":"0","sunday":"0","total":"5",
  "comments":"UNE: Storgata med Qlik-konsulenten, deploy-forarbeid"},
 {"category":"Admin","state":"Pending","week_starts_on":"2026-09-14","monday":"3",
  "tuesday":"0","wednesday":"0","thursday":"0","friday":"0","saturday":"0","sunday":"0",
  "total":"3","comments":"Intern tooling (brain, yaams)"}]
```

Category rows have no `task.number`; `category` is the display name
(`Admin`), while the write contract wants the raw value (`admin`) from
`service.categories`. `total` and day values are strings.

Origin: timeføring uke 38 on 2026-09-22, done by hand through
`cj-weekly-review` step 4 and `owa-swodp write`. The table in this plan's Goal
is the literal output of that session; the TUI should make that session a
two-minute one.

## Status 2026-09-23

Built: plan/adapter/screen, editing, `w` with confirm, `c` fill, e2e, AGENTS.md,
CHANGELOG. Live read-only check against prod week 38: grid and calendar fill
both reproduce the reference table cell for cell.

Simplified vs. this plan (each has a `ponytail:` comment in the code):
- `c` fills empty cells only and reports "kept" cells; no overwrite confirm.
- Unmapped calendar categories are named in the status row; no `?` row.
- `a` refuses an identity already in the week, so the `"new": true` case
  (second card beside a Submitted one) goes through `owa-swodp write`.
- No blink interval; the DataTable cell cursor is the focus marker.
- `docs/` does not exist; the key table is the Esc → Help line.

Left: first live write (one row, then `owa-swodp cards` cross-check),
`owa-swodp tui` shim in owa-tools, `d` diff columns, LLM assist.
