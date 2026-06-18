# AGENTS.md

Start here for any contributor or coding agent working in `owa-tui`, then
read the nearest local `AGENTS.md` for the files you are editing.

## Project Purpose

`owa-tui` is a Textual terminal UI front-end for the `owa-tools` Microsoft 365
CLI suite. It provides interactive TUI adapters for calendar, mail, graph, and
related data surfaces exposed by `owa-tools`.

## owa-tui depends on the owa-tools stable library-API surface

The only permitted import boundary from owa-tools is the stable library API:

- `owa_core.auth.get_token` / `owa_core.auth.get_token_for_config`
- `owa_cal.api` and `owa_cal.events`
- `owa_mail.api` and `owa_mail.messages`
- `owa_graph.api`

Dependency is strictly one-way: **owa-tui -> owa-tools**. owa-tools must never
import from owa-tui. Never import `owa_piggy` Python modules or read
`~/.config/owa-piggy` directly. Use the `owa-piggy` subprocess JSON surface
(via `owa_core.auth`) to obtain tokens.

## Global Contracts

- JSON data flows through owa-tools API functions. The TUI renders it; it does
  not re-implement HTTP or auth.
- Diagnostics, prompts, warnings, and errors go to stderr or the TUI status
  bar; never silently swallowed.
- No live Microsoft or real broker calls in default tests. Live tests must be
  explicitly gated by environment variables (e.g. `OWA_TUI_LIVE_TESTS=1`).
- No telemetry or update checks.
- No MCP server, now or later. This is a deliberate, permanent non-goal.
  The TUI drives owa-tools through its documented Python library surface; agents
  drive it through the owa-tools JSON/exit-code contract. Do not add a Model
  Context Protocol server or propose one.

## Exit Codes

Inherited from owa-tools for any CLI surface:

- `0` success
- `2` usage error
- `10` network error
- `11` auth expired
- `12` auth scope insufficient
- `13` not found
- `14` rate-limited
- `15` conflict or precondition failure
- `20` internal error

## Repository Map

| Path | Read When |
|---|---|
| `.plans/` | checking local implementation plans, if present |
| `.github/AGENTS.md` | changing CI or release workflows |
| `src/owa_tui/AGENTS.md` | changing TUI widgets, screens, or adapters |
| `src/tests/AGENTS.md` | adding or changing tests |
| `docs/` | changing user documentation |

## Verification

Run before committing:

```bash
.venv/bin/ruff check .
.venv/bin/python -m compileall -q src
.venv/bin/python -m pytest -q --cov --cov-fail-under=80
```

For release or packaging changes also run:

```bash
uv build
```

## Workflow Rules

- Check `.plans/` before non-trivial work. It is intentionally gitignored and
  may contain current operator context.
- Keep changes scoped. One domain per commit is preferred.
- Do not commit build artifacts, virtualenvs, caches, local config, or `.plans/`.

## Cutting a release (only when the user asks)

`owa-tui` ships as a separate distribution on PyPI alongside `owa-tools`.
Follow the same tag-driven release flow as `owa-tools` (see `RELEASING.md`).
The key difference: `owa-tui` has a runtime dependency on a published
`owa-tools>=1.0.0`; coordinate version compatibility across the two packages
before tagging.
