# ponytail audit cleanup

_From a repo-wide over-engineering audit (2026-06-20). Findings only — nothing
applied. Ranked biggest cut first. net: ~-130 src lines (-210 with the settings
dedup), 0 deps removable._

## Goal

Remove dead flexibility and hand-rolled stdlib found in the audit, without
changing behaviour users actually rely on. Each item is independent; do them
in order, keep gates green (ruff + pytest 85% + `npx tui-test`) after each.

## Steps

- [x] **1. finish (not cut): write-only bookmark feature.** Done 2026-06-23 —
  owner chose to finish it rather than delete. `get_bookmarks()` now has a
  caller: `M` opens a `SettingsOverlay` picker over saved bookmarks and jumps
  (audience+path) to the chosen one (`screens/graph.py` `action_bookmarks` /
  `_on_bookmark_chosen` / `_jump_to`). `m` now also persists settings to the
  owa-graph config (`_persist_settings`), skipped in fixture mode so e2e never
  touches the real config. Covered by Pilot (empty/picker/jump/ignore/persist)
  + 3 fixture-mode e2e cases. `GraphState.bookmarks` left as-is (still unused;
  the real store is `GraphSettings._bookmarks_list`).
- [x] **2. shrink: three people layout subclasses (~40 → ~15).** Done
  2026-06-22 (commit e9d0239) — collapsed `_LayoutRight`/`_LayoutBottom`/
  `_LayoutOff` into inline `Horizontal`/`Vertical` construction in
  `_build_layout` with styles set there.
- [x] **3. stdlib: hand-rolled ISO parser (~12 → ~4).** Done 2026-06-22
  (commit e9d0239) — replaced the regex-strip + 3-format `strptime` loop with
  `datetime.fromisoformat`. Existing `mail/dates` tests pass.
- [x] **4. dedup the 4 settings modules — the cycle stepper.** Done 2026-06-23.
  Extracted the one genuinely-duplicated, edge-case-bearing bit (find current in
  allowed → wrap by direction → fall back) into `owa_tui/settings_cycle.py`
  `cycle_value()`, now used by all four (`people`/`mail`/`cal`/`graph`,
  incl. graph's bool toggle + split_ratio sequence). This also unified an
  inconsistency: cal's miss-path stepped from index 0 while mail/people reset to
  the first value — the shared helper resets to the first valid value
  everywhere (a corrupt `split_ratio` now resets to 40 instead of jumping to 50;
  `test_cal_pilot` updated to match). Covered by `test_settings_cycle.py` + a
  `_demo()` self-check.
  _Deliberately NOT done: the from_config/to_config "dedup" the audit floated.
  Those are structurally similar but materially different (key prefixes, type
  coercion, graph's bool/bookmarks); a per-screen descriptor-table driver adds
  about as much indirection as it removes — the audit's own LOW-confidence
  caveat. The stepper was the real duplication; the rest is left alone._

## Notes

- Not findings (checked, keep): `adapter.py` `access_token_for` (handles 3
  broker return shapes + fixtures — real seam); the 8 screen adapters on
  `OwaListScreen`/`TreeScreen`/`GridScreen` (genuine per-tool shapes, 3+
  consumers each); `MenuState`/`GraphState` (used; all GraphState fields except
  `bookmarks` have readers).
- No dependencies are removable — everything already rides stdlib + textual.
