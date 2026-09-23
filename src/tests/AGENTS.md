# src/tests

- One directory per screen/domain (`mail/`, `drive/`, ...). Pilot tests run the
  app with `app.run_test()`; no live Microsoft calls (gate live ones behind
  `OWA_TUI_LIVE_TESTS=1`).
- `conftest.py` (repo root) sets `StatusBar.AUTO_CLEAR = 0` so tests can read
  status text at their own pace.

## Snapshots

`snapshots/test_snapshots.py` renders home, mail, people and drive from
`e2e/fixtures/` at 120x40 and diffs against the SVGs in
`snapshots/__snapshots__/`. After an intentional visual change:

```bash
.venv/bin/python -m pytest src/tests/snapshots --snapshot-update
```

Review the SVG diff before committing it. A Textual upgrade can change the
rendering; when CI fails only on snapshots after a Textual release, regenerate
them with that version.
