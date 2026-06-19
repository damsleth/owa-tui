# owa-tui

`owa-tui` is a Textual terminal UI front-end for the `owa-tools` Microsoft 365
CLI suite.

The project is intentionally separate from `owa-tools`: `owa-tui` imports only
the stable `owa-tools` library API and never imports broker internals directly.

## Status

This package currently provides the installable launcher shell. Calendar, mail,
and graph screens are being ported to Textual behind that launcher.

## Install

```bash
pip install owa-tui
```

## Usage

```bash
owa-tui --help
owa-tui --version
owa-tui
```

Running `owa-tui` starts the Textual shell. No Microsoft Graph or broker calls
are made during startup.

## Development

```bash
.venv/bin/ruff check .
.venv/bin/python -m compileall -q src
.venv/bin/python -m pytest -q --cov --cov-fail-under=80
uv build
```

### End-to-end terminal tests (tui-test)

In-process pytest covers widget logic; [`@microsoft/tui-test`](https://github.com/microsoft/tui-test)
covers the real binary by spawning `owa-tui` in a pty and asserting on what it
actually renders. Tests live in `e2e/`.

```bash
npm install          # one-time
npm run test:e2e     # or: npx tui-test
```

`owa-tui` must be importable on `PATH` (e.g. `pip install -e .`). Traces land in
`tui-traces/`; replay with `npx tui-test show-trace`.
