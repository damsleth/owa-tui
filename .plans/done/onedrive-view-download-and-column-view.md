# OneDrive view download and column view

_Created 2026-09-22_ · todos #8, #9, #10

## Goal

From `DriveScreen` a file can be viewed (text) and downloaded; folders can
optionally be browsed in lf-style columns.

## Problem

`src/owa_tui/screens/drive.py` is read-only navigation: files show
metadata in the detail pane, `o` opens `webUrl`. The CLI already has the
primitives: `owa_drive.paths.content_endpoint(path)` and
`owa_drive.api.api_get_binary` (used by `owa-drive get`, `cli.py:196`, with
an overwrite guard raising `ConflictError`). The item path is
`parentPath.strip('/') + '/' + name`, the same derivation `child_node` uses.

## Approach (minimal), in order

Phase 1, download (#9):
- `BINDINGS = LIST_BINDINGS + [Binding("D", "download", "Download")]`
  (pattern: `screens/todo.py:123`).
- `action_download`: current file item -> `content_endpoint` ->
  `api_get_binary` in a worker -> write `~/Downloads/<name>`; refuse if it
  exists (status: `exists: ... (delete it first)`), else status
  `wrote N bytes to ...`. Reuse `self._token`.
- Fixture mode: no bytes seam exists; status `download unavailable in fixture mode`.

Phase 2, view (#8):
- On `on_item_activated` for a file with text-ish `mimeType`
  (`text/*`, json, xml, csv, markdown) and `size` under ~256 KB: fetch bytes
  as above, decode utf-8 (errors=replace), show in the detail pane under the
  metadata. Anything else keeps today's metadata + `o` for browser.
- No renderers for docx/xlsx/pdf: out of scope, browser is the viewer.

Phase 3, column view (#10) — only if wanted:
- Miller columns change `OwaTreeScreen` (`base/tree.py`) from one list +
  detail to N lists; every tree consumer (drive, sites, planner) is affected.
  Cheapest variant: a `column_view` setting that renders the parent folder
  in the left pane and the current folder in the middle, detail right.
  Propose as its own plan after phases 1-2 ship.

## Files

- `src/owa_tui/screens/drive.py`
- `src/tests/drive/test_*.py` (mock `api_get_binary`; assert file write,
  overwrite refusal, fixture-mode status)
- `docs/` key table for `D`

## Verification

- pytest with coverage gate; `npx tui-test` still green (drive e2e unchanged).
- Live: `owa-tui --tool drive`, `D` on a small file -> appears in `~/Downloads`;
  Enter on a .md/.txt file -> content in the detail pane.

## Open questions

- Download target: `~/Downloads`, cwd, or prompt for a path?
- Is a text-only viewer enough for #8, or must docx/pdf show something
  beyond metadata + browser?
- #10: do you actually want lf-style Miller columns, or is drill-in
  (`l`/`h`) enough now that view/download exist? Phase 3 only proceeds on a yes.
