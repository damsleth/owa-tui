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
- [ ] **2. shrink: three people layout subclasses (~40 → ~15).**
  `_LayoutRight`/`_LayoutBottom`/`_LayoutOff` (`screens/people.py:763-803`) each
  only set width/height % in `compose()` and yield children. Collapse to one
  container taking orientation + ratio, or build `Horizontal`/`Vertical` inline
  in the screen's `compose` with styles set there.
- [ ] **3. stdlib: hand-rolled ISO parser (~12 → ~4).** `mail/dates.py:24-35`
  `_parse_iso` strips the TZ suffix with a regex then loops 3 `strptime`
  formats. `datetime.fromisoformat` (3.11) parses bare-date, no-seconds, and
  `Z`/offset forms directly. Drop `_STRIP_TZ`, `_PARSE_FMTS`, the loop. Verify
  against the existing `mail/dates` tests.
- [ ] **4. yagni (LOW confidence): dedup 4 settings modules (~80, risky).**
  `people/`, `mail/`, `cal/`, `graph/` settings each repeat the same
  cycle/from_config/to_config skeleton in two idioms (frozen + module-funcs vs
  dataclass-methods). A shared `cycle(settings, field, allowed_map)` + one
  `from_config` driver off a field→key map would centralize it. Different fields
  per screen + cross-screen refactor risk — defer unless touching settings
  anyway.

## Notes

- Not findings (checked, keep): `adapter.py` `access_token_for` (handles 3
  broker return shapes + fixtures — real seam); the 8 screen adapters on
  `OwaListScreen`/`TreeScreen`/`GridScreen` (genuine per-tool shapes, 3+
  consumers each); `MenuState`/`GraphState` (used; all GraphState fields except
  `bookmarks` have readers).
- No dependencies are removable — everything already rides stdlib + textual.
