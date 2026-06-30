# Changelog

All notable changes to `owa-tui` are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); this project uses semantic
versioning.

## [0.2.1] - 2026-06-30

Post-release feature batch plus an audit of the v1 plans for genuine gaps.

### Added
- **Mail**: folder side-panel (`F`) scoping the list per folder, live settings
  apply (reading-pane rebuild without re-entering), scroll-to-load pagination,
  and `j`/`k`/`u`/`d` reading-pane scroll mirroring the list keys.
- **People**: `Esc` returns to the list when viewing a person's detail.
- Active theme persists in `~/.config/owa-tui/tui.json`; the transparency
  toggle now round-trips its under-theme so toggling off after a restart
  returns to the real previous theme.
- **Graph**: `n` (next page) extends the list (appends the new page, parks the
  cursor on the first new row, `+N rows` status) instead of replacing it.
- `tui-test` e2e spec for the mail folder panel.

### Fixed
- **Teams**: live `fetch_messages`/`fetch_items` called `access_token_for()`
  without the required `config` argument — a `TypeError` on the real Graph path
  that fixture-mode e2e never exercised. Live-path tests now use `autospec` so a
  missing argument fails loudly.
- `__version__` synced to the package version (was stuck at `0.1.0`, so
  `--version` underreported).

### Known limitations
- **Graph DevOps** continuation-token paging is unreachable: the stable
  `owa_graph.api_request` returns parsed JSON only, so the
  `x-ms-continuationtoken` response header can't be read. First page works;
  2nd+ page of the `devops` audience does not. OData/ARM body cursors are
  unaffected. Fixing needs a headers-returning upstream call.

[0.2.1]: https://github.com/damsleth/owa-tui/releases/tag/v0.2.1

## [0.2.0] - 2026-06-24

First published release: a Textual TUI front-end for the `owa-tools` Microsoft
365 CLI suite, covering all twelve tools.

### Added
- Launcher shell with tool menu, `--help`/`--version` CLI, and baseline tests.
- **v1 screens** for the three flagship tools — `owa-cal`, `owa-mail`, and
  `owa-graph` — on a shared Textual widget kit.
- **v2 coverage** adapters for the remaining tools, each on a reusable base
  screen:
  - `owa-people` (v1.x adapter) and `owa-todo` (T1) on `OwaListScreen`.
  - `owa-planner` (T5) and `owa-ado` (T6, read-only work items) on
    `OwaListScreen`.
  - `owa-drive` (T2) and `owa-sites` (T3, SharePoint lists) on `OwaTreeScreen`.
  - `owa-sched` (T4 free/busy grid) and `owa-doctor` (T8 health grid) on
    `OwaGridScreen`.
  - `owa-teams` (T7, chats → thread) on `OwaThreadScreen`.
- Reusable base screens: `OwaListScreen`, `OwaTreeScreen`, `OwaGridScreen`,
  `OwaThreadScreen`.
- Header shows the current profile + UPN in the top row.
- Settings overlay shows values with in-place cycling; a shared cycle stepper
  drives all four modules.
- `owa-graph` bookmarks: `M` jump-to picker with config persistence.
- Grid/Teams cell-detail, add-attendee, and open actions.
- UI: content padding and `Ctrl+T` transparent-background toggle.
- Env-gated live integration tests against real M365 — unit token smoke
  (`OWA_TUI_LIVE_TESTS=1`) and full-render e2e (`OWA_TUI_LIVE_E2E=1`).
- `tui-test` e2e harness covering all bound actions across all twelve TUIs.
- CI: auto-release on tags with an e2e gate; 85% coverage gate.

### Changed
- Centralized per-call token minting in the auth layer.
- Theme follows the selected theme instead of pinning dark colours.
- `q` returns to the tool menu instead of quitting to the terminal.
- Stdlib ISO parsing; collapsed people layout subclasses; dropped the dead
  fetch layer, unused widget kit, and base auth wrapper.

### Fixed
- Packaging: wheel/sdist now include all `owa_tui` subpackages (`screens`,
  `screens.base`, `people`, …) via automatic discovery. Previously
  `packages = ["owa_tui"]` shipped only the top-level package, so an installed
  `owa-tui --help` crashed with `ModuleNotFoundError: No module named
  'owa_tui.screens'`.
- `owa-cal`/`owa-mail` use the Outlook REST base, not Graph — fixes 401 "auth
  expired".
- `OwaGridScreen` accepts config positionally in its base.

[0.2.0]: https://github.com/damsleth/owa-tui/releases/tag/v0.2.0
