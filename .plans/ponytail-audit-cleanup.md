# ponytail audit cleanup

_From a repo-wide over-engineering audit (2026-06-20). Findings only — nothing
applied. Ranked biggest cut first. net: ~-130 src lines (-210 with the settings
dedup), 0 deps removable._

## Goal

Remove dead flexibility and hand-rolled stdlib found in the audit, without
changing behaviour users actually rely on. Each item is independent; do them
in order, keep gates green (ruff + pytest 85% + `npx tui-test`) after each.

## Steps

- [ ] **1. delete: write-only bookmark feature (~75 src lines, biggest cut).**
  _Status (2026-06-22): deferred — owner chose not to delete this feature for now._
  `m` saves bookmarks to config but `get_bookmarks()` has **zero callers** and
  `GraphState.bookmarks` **zero reads** — nothing ever lists or jumps to them.
  Decision: cut vs. finish (it's advertised in help/keybindings, so "write but
  can't recall" is also a latent UX bug). Audit recommends cut. Remove:
  `GraphState.bookmarks` (`graph/state.py`); `action_bookmark` + its
  `screens/graph.py` wrapper + the `m` Binding + 2 help lines;
  `graph/settings.py` `parse_bookmarks`/`dump_bookmarks`/`add_bookmark`/
  `get_bookmarks`/`_bookmarks_list`/`bookmarks` field/`__post_init__`/
  `graph_tui_bookmarks` key; and the bookmark tests in
  `tests/graph/test_graph_actions.py` + `test_graph_settings.py`.
- [x] **2. shrink: three people layout subclasses (~40 → ~15).** Done
  2026-06-22 (commit e9d0239) — collapsed `_LayoutRight`/`_LayoutBottom`/
  `_LayoutOff` into inline `Horizontal`/`Vertical` construction in
  `_build_layout` with styles set there.
- [x] **3. stdlib: hand-rolled ISO parser (~12 → ~4).** Done 2026-06-22
  (commit e9d0239) — replaced the regex-strip + 3-format `strptime` loop with
  `datetime.fromisoformat`. Existing `mail/dates` tests pass.
- [ ] **4. yagni (LOW confidence): dedup 4 settings modules (~80, risky).**
  `people/`, `mail/`, `cal/`, `graph/` settings each repeat the same
  cycle/from_config/to_config skeleton in two idioms (frozen + module-funcs vs
  dataclass-methods). A shared `cycle(settings, field, allowed_map)` + one
  `from_config` driver off a field→key map would centralize it. Different fields
  per screen + cross-screen refactor risk — defer unless touching settings
  anyway.
  _Status (2026-06-22): still deferred. The menu rework (commit cbedbe6) touched
  all four settings modules but only to add a uniform `direction` param to the
  cycle functions; the cross-screen dedup of from_config/to_config remains
  LOW-confidence/high-risk and isn't worth it yet._

## Notes

- Not findings (checked, keep): `adapter.py` `access_token_for` (handles 3
  broker return shapes + fixtures — real seam); the 8 screen adapters on
  `OwaListScreen`/`TreeScreen`/`GridScreen` (genuine per-tool shapes, 3+
  consumers each); `MenuState`/`GraphState` (used; all GraphState fields except
  `bookmarks` have readers).
- No dependencies are removable — everything already rides stdlib + textual.
