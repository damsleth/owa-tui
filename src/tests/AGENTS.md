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

## Gotchas

- `conftest.py` stubs `owa_core.config.load_config_file` and `save_config`, so
  no test reads or writes the real `~/.config/owa-*` files. A test that needs a
  saved setting patches `load_config_file` itself.
- `monkeypatch.setattr(fetch_mod.asyncio, "to_thread", …)` replaces
  `asyncio.to_thread` everywhere, including the screen's own token and
  profile calls. The fake must dispatch on `fn` and call anything it doesn't
  mean to stub.
- `-A` (merged profiles) tests use `e2e/fixtures/profiles.json` in fixture mode,
  or patch `adapter.eligible_profiles`. Never let them shell out to owa-piggy.
