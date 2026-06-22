# grid + teams action gaps

_Created 2026-06-21. Surfaced by the e2e "all actions" coverage work — these are
implementation gaps (advertised/planned behaviour that the code doesn't do), not
test gaps. Being implemented now._

## Goal

Make the grid screens (sched/doctor) and teams open-browser actually do what the
v2 plan and keybindings advertise, instead of being silent no-ops.

## Steps

- [x] **teams open-browser** — `TeamsScreen` inherits the base `open_browser_for`
  → `None`, so `o` reports "no browser link" even though chats carry `webUrl`.
  Fix: override `open_browser_for` to return `item.get("webUrl")`. (cf. `AdoScreen`
  which already overrides it for `item["url"]`.)
- [x] **grid `enter` cell-detail** — `OwaGridScreen` is read-only with no `enter`.
  The v2 plan described `enter` → show full detail for the selected cell. Add to
  the base: an `enter` binding → `action_show_detail`, an overridable
  `cell_detail(row_label, col_label, value)` hook (default
  `"<row> · <col>: <value>"`), and store the raw rows/cols so the cursor cell can
  be resolved. Set the footer (`_status`) to the detail string.
- [x] **doctor cell-detail** — override `cell_detail` to append the probe's error
  / minutes-remaining (the v2 plan wanted "full error detail"). Store the per-cell
  finding lookup during `fetch_grid`.
- [x] **sched `a` add-attendee** — the v2 plan described `a` → input prompt → add
  attendee → re-fetch grid. Add an `a` binding + `action_add_attendee` that reuses
  the existing `_SearchModal` (prompt "Add attendee:"), appends the email to
  `self._attendees`, and re-runs `_fetch_grid`.

## Notes

- e2e tests currently assert `enter`/`a` are no-ops on the grids — those
  assertions must flip to assert the new behaviour once implemented.
- Keep within ponytail bounds: generic `cell_detail` default in the base; reuse
  `_SearchModal`; no new modal class, no new dep.
