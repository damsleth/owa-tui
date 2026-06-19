# Plan 01 — owa-tui Architecture

**Status:** decision-record + design reference  
**Author:** architecture subagent (June 2026)  
**Scope:** all of `owa-tui`; sibling plans 10/11 implement individual adapters against this spec

---

## Status & drift (as of commit 76c2675)

This remains the design reference, but shipped v1 diverged in a few places — noted here so the
doc isn't read as gospel:

- **Layout:** tool screens live under `src/owa_tui/screens/` (`screens/cal/`, `screens/mail.py`,
  `screens/graph.py`, `screens/home.py`), not `src/owa_tui/cal/` etc. `OwaTuiApp` lives in
  `__init__.py`, not `app.py`. The shared kit is `src/owa_tui/widgets/` (`list_browser`,
  `detail_pane`, `settings_overlay`, `menu_state`, `status_bar`) — close to §5 but flatter.
- **Token model (supersedes §4c):** v1 does **per-call token minting** (commit fcfa2bc), not the
  "mint once before `app.run()`" model in §4c. Each fetch/respond worker mints via
  `adapter.access_token_for(...)` / `get_token_for_config(...)`. Simpler, avoids stale tokens.
- **REST base:** cal/mail hit the Outlook REST base (`outlook.office.com/api/v2.0`), not Graph
  (commit 9341db7 fixed a 401 from the wrong base).
- **Testing infra (new, not in original plan):** two layers — (1) in-process **Pilot** tests in
  `src/tests/` that monkeypatch fetch; (2) black-box **tui-test** e2e in `e2e/` that drives the
  real binary in a pty, powered by a **fixture-mode seam** (`src/owa_tui/fixtures.py`):
  `OWA_TUI_FIXTURES=<dir>` short-circuits fetch to canned JSON and token minting to a dummy token,
  so every user action runs deterministically with no live auth. `pytest-textual-snapshot` is a
  declared dep but **no snapshot tests were written** — Pilot + e2e replaced that approach.

### Widget-kit adoption gap (ponytail-audit, 2026-06-19)

The §5 "shared widget kit" only partly landed. Of `src/owa_tui/widgets/`:

- **Live & shared:** `SettingsOverlay` + `MenuState` + `StatusBar` — used by cal/mail/graph/people
  and the base. Keep.
- **Built, never adopted, now removed:** `ListBrowser` (§5a) and `DetailPane` (§5b) were deleted
  (commit follows). v1 screens each rolled their own list/detail (`AgendaList`, `MessageList`,
  graph's list, people's `DetailPane`, the base's `_OwaList`/`_DetailPane`) and none ever subclassed
  the kit versions — they were dead. The §5a/§5b **specs remain the blueprint**: if a v2 list card
  wants a shared list/detail widget, rebuild from those sections (and have the new screen actually
  use it) rather than resurrecting unused code. The base's `_OwaList`/`_DetailPane` are now the
  canonical list/detail impls.
- **Removed:** the central `adapter.py` fetch layer — `fetch_token`,
  `fetch_cal_events`, `fetch_mail_messages`, `fetch_graph_request`, and `FetchMixin` — was
  superseded by the per-screen fetch modules (`screens/cal/fetch.py`, mail inline, `graph/fetch.py`)
  and is referenced by no screen. Only `access_token_for` is live. v2 tools get their **own**
  per-tool `adapter.py` (plan 20), so nothing depends on these. Safe to delete with their tests.

---

## 0. Context

`owa-tui` is the Textual terminal-UI front-end for the `owa-tools` Microsoft 365 CLI suite.
It replaces the curses-based TUI layers that live inside `owa_cal`, `owa_mail`, and `owa_graph`
in owa-tools — those will be deleted from owa-tools once the Textual ports are shipped.

`owa-tui` is a separate PyPI distribution that depends on `owa-tools>=1.0.0`. The dependency
is strictly one-way: owa-tui → owa-tools. owa-tools must not import from owa-tui.

---

## 1. Resolved Decision: App Model

**Recommendation: one unified multi-tool Textual app (`owa-tui`) with per-tool Screens.**

### Rationale

The per-tool alternative — a separate standalone Textual `App` per tool — was the curses model:
each binary (`owa-cal tui`, `owa-mail tui`) stood up its own `curses.wrapper` session and ran
independently. It was natural in curses because there was no concept of shared screens or
navigation stacks. Textual changes the calculus in three ways:

1. **Textual `Screen` stack.** A single `App` can push and pop `Screen` instances at runtime.
   "Switching tools" is just pushing a different `Screen`. The overhead of a common `App` shell
   is negligible (one event loop, one terminal session).

2. **Auth and config reuse.** All tools share `owa_core.auth.get_token`. Factoring that into a
   shared `App.__init__` means each `Screen` receives an already-minted token rather than
   redoing auth on every tool switch. The curses model had no way to share state across tools
   without forking a subprocess.

3. **Shared widget kit.** Plan 10 (cal) and plan 11 (mail) define identical structural widgets:
   a scrollable list widget, a reading/detail pane, a settings overlay `ModalScreen`, and a
   status bar. A unified shell lets these live in `owa_tui.widgets` and be imported by every
   `Screen` without duplication or circular imports.

**The entry point (`owa-tui`) runs a single `App` (`OwaTuiApp`) that launches a tool-select
screen at startup, then pushes the chosen tool's `Screen`.** Each tool is also reachable
directly via entrypoints aliased from the underlying tools' CLIs (`owa-cal tui`, `owa-mail tui`),
which bypass the tool-select screen and push the relevant `Screen` directly. This preserves the
existing CLI UX while enabling future cross-tool navigation.

**Tool-select screen** (v1 stub): a simple `SelectionList` or `ListView` listing available
tools. In v1 the list is static (`cal`, `mail`, `graph`). Picking one pushes the tool's
`Screen`. The tool-select screen is tested with `Pilot` just like any other `Screen`.

---

## 2. Repo and Module Layout

```
owa-tui/
  src/
    owa_tui/
      __init__.py          # version + main() entrypoint
      app.py               # OwaTuiApp — the single App; tool-select screen
      widgets/
        __init__.py
        list_browser.py    # ListBrowser: generic ListView + status bar base
        detail_pane.py     # DetailPane: ScrollableContainer for right/bottom slot
        settings_overlay.py  # SettingsOverlay: ModalScreen with top/settings screens
        menu_state.py      # MenuState: pure dataclass driving SettingsOverlay nav
        status_bar.py      # StatusBar: reactive Label at the bottom of every screen
        theme.py           # CSS string constants; load_theme() helper
      cal/
        __init__.py
        screen.py          # CalScreen(Screen)
        agenda.py          # AgendaList(ListView)
        detail.py          # CalDetailPane(DetailPane)
        settings_menu.py   # CalSettingsOverlay(SettingsOverlay)
        fetch.py           # async fetch_events(…) -> (list[dict], str|None)
        settings.py        # CalSettings dataclass + cycle/from_config/to_config_dict
      mail/
        __init__.py
        screen.py          # MailScreen(Screen)
        message_list.py    # MessageList(ListView)
        reader_pane.py     # ReaderPane(DetailPane)
        settings_menu.py   # MailSettingsOverlay(SettingsOverlay)
        fetch.py           # async fetch_messages / fetch_body
        settings.py        # MailSettings dataclass + helpers
        sort.py            # pure sort helpers (ported from owa_mail.tui_sort)
        dates.py           # format_received, validate_custom_format
        list_row.py        # list_row() render helper
      graph/
        __init__.py
        screen.py          # GraphScreen(Screen)
        # ... (planned in future phase, not v1)
  src/tests/
    __init__.py
    conftest.py            # shared Pilot fixtures, monkeypatch helpers
    cal/
      test_cal_screen.py
      test_cal_detail.py
      test_cal_fetch.py
    mail/
      test_mail_screen.py
      test_mail_sort.py
      test_mail_dates.py
      test_mail_list_row.py
    widgets/
      test_settings_overlay.py
      test_menu_state.py
      test_layout_helpers.py  # pure unit tests for any layout math in widgets/
```

---

## 3. Adapter Layer (owa-tools imports)

owa-tui calls into owa-tools' stable library surface for data and auth. No curses symbols are
imported. The permitted boundary, per `AGENTS.md`:

```python
# Auth — same for all tools
from owa_core.auth import get_token, get_token_for_config

# Calendar
from owa_cal.api import api_get, api_request, build_query
from owa_cal.events import (
    normalize_event, normalize_event_detail, normalize_events_detail,
    to_local, build_event_json, build_patch_json,
)
from owa_cal.dates import current_iso_week, iso_week_range
from owa_cal.config import load_config as cal_load_config, save_config as cal_save_config

# Mail
from owa_mail.api import api_get, api_request
from owa_mail.messages import build_list_query, normalize_messages, normalize_message
from owa_mail.config import load_config as mail_load_config, save_config as mail_save_config

# Graph (v2+)
from owa_graph.api import api_get, api_request
```

The tui_kit modules (`owa_core.tui_kit.*`) are NOT imported. They are the curses-era shared
kit — analogous to what `owa_tui.widgets` becomes in Textual. `owa_core.tui_kit.layout` contains
pure geometry helpers (`pad`, `truncate`, `wrap_body`); those can be imported if a Textual
context requires them, but in practice the equivalent Textual `Rich` markup and `Static.update`
are used instead. `owa_core.tui_kit.settings` (`cycle`, `from_config`, `to_config_dict`) is
pure logic — these may be imported by `owa_tui.*.settings` modules if desired, but the sibling
plans (10, 11) call for re-implementing cycle/from_config/to_config_dict inline. Either approach
is acceptable; consistency wins — pick one and use it everywhere.

**Recommended:** import `owa_core.tui_kit.settings` helpers (they are pure, tested, and stable)
to avoid divergence bugs in cycling logic. Do NOT import `owa_core.tui_kit.app`, `.menu`,
`.layout`, or `.screen`.

---

## 4. Async Worker Fetch Pattern

### 4a. The Old Invariant (curses tui_kit)

The curses `BrowserSpec.fetch_items(state)` contract was:
- Synchronous.
- Mutates `state.items` and `state.status`.
- Must never print or write to stdout/stderr.
- Called from the main loop before the next redraw; the loop called `stdscr.getch()` after
  drawing, so a slow `fetch_items` blocked the entire terminal session.

owa-graph deviated from this by pre-fetching before entering curses and refreshing on `_ensure_token`
side-effects, deferring blocking network I/O to a token-refresh path. This was workable but
opaque — the deviation was load-bearing but undocumented.

### 4b. The Textual Worker Pattern (replacement)

Textual provides `@work(thread=True)` (or `@work` for async workers). The standard pattern:

```python
from textual.worker import work

class SomeScreen(Screen):
    _items: reactive[list[dict]] = reactive([])
    _status: reactive[str] = reactive('')

    @work(exclusive=True)
    async def load_data(self) -> None:
        """Fetch data off the UI thread; update reactives when done."""
        items, err = await fetch_fn(
            self._access_token, self._api_base, ...
        )
        # These assignments happen on the worker thread; Textual posts them
        # back to the event loop via call_from_thread.
        self.app.call_from_thread(self._apply_results, items, err)

    def _apply_results(self, items: list[dict], err: str | None) -> None:
        """Called on the main loop — safe to mutate reactives and update widgets."""
        self._items = items
        self._status = err or ''
        self.query_one(SomeList).update_rows(items)
```

All `fetch_*` functions in `owa_tui.*.fetch` are `async def`. They wrap synchronous
`owa-tools` API calls with `asyncio.to_thread`:

```python
import asyncio

async def fetch_events(access_token, api_base, day_range, show_declined, search='', debug=False):
    """Returns (list[dict], str|None). Never raises."""
    try:
        data = await asyncio.to_thread(
            api_get, api_base, f'me/calendarView?{q}', access_token, debug=debug
        )
        ...
    except Exception as exc:
        return [], f'unexpected error: {exc}'
```

**`exclusive=True` on the worker** ensures that a rapid succession of key presses (e.g.,
toggling `day_range` twice) does not pile up redundant network calls — the second `load_data()`
invocation cancels the in-flight first one.

### 4c. Replacing owa-graph's Deferred Pre-fetch Deviation

In the curses `owa_graph/tui.py`, `_ensure_token` was called inside `fetch_items` to mint or
refresh the token, blocking the terminal. The "pre-fetch before curses" approach avoided the
worst blocking but created a split-brain: token minting happened outside the curses session but
refreshing happened inside it.

In owa-tui, token minting is handled before any `Screen` is pushed: `OwaTuiApp.__init__` (or
the per-tool CLI entrypoint) mints the token synchronously before `app.run()`. A token refresh
during a live session is handled by `GraphScreen.load_data()` re-calling
`get_token_for_config(...)` inside the worker — blocking is safe on a worker thread, invisible
to the UI thread. The pattern:

```python
@work(exclusive=True)
async def load_data(self) -> None:
    # Refresh token if near expiry — safe here (worker thread, not UI thread).
    token_info = await asyncio.to_thread(
        get_token_for_config, self._config, tool_name=TOOL_NAME, audience=self._audience
    )
    if token_info is None:
        self.app.call_from_thread(setattr, self, '_status', 'auth failed')
        return
    data = await asyncio.to_thread(api_get, ...)
    ...
```

This replaces the `_ensure_token` / `_apply_token` / `token_cache` machinery from the curses
GraphState with a simpler, stateless pattern: each worker call re-validates expiry via
`get_token_for_config` (which hits the owa-piggy cache, not AAD, on cache hit).

---

## 5. Shared Textual Widget Kit

This is the owa-tui analog of `owa_core.tui_kit`. It lives in `src/owa_tui/widgets/`.

### 5a. `ListBrowser` (`list_browser.py`)

Not a standalone `App` — a `Widget` that can be composed into any `Screen`.
Wraps `textual.widgets.ListView` with:
- Keyboard bindings: `j`/`k`/`↑`/`↓` move; `g`/`G` top/bottom; `u`/`d` half-page;
  `PgUp`/`PgDn`/`Space` page; `Enter`/`→`/`l` drill; `h`/`←` back.
- A `Message` subclass `ItemSelected(Widget.Message)` fired when selection changes.
- A `Message` subclass `ItemDrilled(Widget.Message)` fired on Enter/→/l.
- A `Message` subclass `BackPressed(Widget.Message)` fired on h/←.
- `update_rows(items: list[Any]) -> None` — repopulates the list.
- `current_item() -> Any | None` — returns the selected item or `None`.

Individual tool screens subclass their list widget from `ListBrowser` (e.g., `AgendaList`,
`MessageList`) and override `render_item(item) -> str | Text` to produce the row string.

### 5b. `DetailPane` (`detail_pane.py`)

```python
class DetailPane(ScrollableContainer):
    """Generic scrollable detail pane. Content set via update_content()."""

    DEFAULT_CSS = """
    DetailPane {
        overflow-y: scroll;
        padding: 0 1;
    }
    """

    def update_content(self, lines: list[str]) -> None:
        """Replace pane content with rendered lines."""
        self.query_one(Static).update('\n'.join(lines))
```

Tool-specific subclasses (`CalDetailPane`, `ReaderPane`) inherit from `DetailPane` and add
tool-specific `render_*` methods. They do not add their own `DEFAULT_CSS` — all theming comes
from the app-level `tcss` file.

### 5c. `SettingsOverlay` (`settings_overlay.py`)

A `ModalScreen` that implements the two-level menu (top screen → settings screen) pattern used
by all tool screens. Accepts configuration at construction time:

```python
class SettingsOverlay(ModalScreen[str]):
    """Generic top/settings overlay.

    Parameters
    ----------
    title_lines     : header lines for the overlay box.
    top_items       : list of (label, action_str) tuples.
    settings_fields : list of (field_name, display_label) tuples.
    settings        : the current tool settings dataclass instance.
    """

    def __init__(self, title_lines, top_items, settings_fields, settings): ...

    def compose(self) -> ComposeResult:
        # Renders the centred box using Rich renderables or Static widgets.
        # Navigation: ↑/↓ move cursor; Enter fires action; Esc goes back/closes.
        yield Static(id='overlay-box')

    def action_select(self) -> None:
        """Dismiss with the action string for the current item."""
        self.dismiss(self._menu_state.select(self._settings))
```

`SettingsOverlay` is pushed with `self.push_screen(overlay, callback)`. The callback receives
the `action_str` (`'resume'`, `'quit'`, `'cycle:day_range'`, `'reset_settings'`, etc.) and
the tool `Screen` handles the action.

### 5d. `MenuState` (`menu_state.py`)

A **pure Python dataclass** (no Textual imports) driving `SettingsOverlay` navigation — the
direct successor to `owa_core.tui_kit.menu.Menu`. It is a thin port of `Menu` with the curses
render method removed and the `select()` / `move()` / `back()` / `open_settings()` / `reset()`
logic preserved verbatim. Tests are pure unit tests (no Pilot needed).

```python
@dataclass
class MenuState:
    title_lines: list[str]
    top_items: list[tuple[str, str]]     # (label, action)
    settings_fields: list[tuple[str, str]]  # (field, label)
    screen: str = 'top'                  # 'top' | 'settings'
    cursor: int = 0

    def move(self, delta: int) -> None: ...
    def select(self, settings: Any) -> str: ...
    def back(self) -> None: ...
    def open_settings(self) -> None: ...
    def reset(self) -> None: ...
    def items(self) -> list[tuple[str, str]]: ...
```

### 5e. `StatusBar` (`status_bar.py`)

```python
class StatusBar(Label):
    """Reactive status line at the bottom of every tool screen.

    Usage: screen._status reactive is watched; on change, status_bar.update() is called.
    The footer hint (static bindings text) is a separate Label above the StatusBar,
    or embedded as a Textual Footer widget.
    """
```

### 5f. Layout helpers

Layout geometry (split-ratio math, placement modes) is a thin internal helper in
`owa_tui.widgets.theme` or a standalone `owa_tui.widgets.layout` module. The existing
`owa_core.tui_kit.layout.regions()` function can be imported directly for geometry math since
it is pure and tested; however, Textual's CSS-driven layout (`Horizontal`, `Vertical`,
`width: X%`) makes `regions()` unnecessary for the pane split. Use `width: {ratio}%` and
`width: 1fr` in the tcss instead.

The text-fitting helpers (`pad`, `truncate`, `truncate_ellipsis`, `wrap_body`) are imported
directly from `owa_core.tui_kit.layout` — they are pure Python with no curses dependency.

---

## 6. Theming and Config Location

### 6a. Textual CSS (`tcss`)

Each tool screen has its own `CSS_PATH` pointing to a `.tcss` file alongside the screen module:

```
src/owa_tui/
  cal/
    screen.py
    cal.tcss
  mail/
    screen.py
    mail.tcss
  widgets/
    base.tcss     # shared colours, status bar, overlay styles
```

`OwaTuiApp` loads `base.tcss` at the `App` level via `CSS_PATH`. Individual screens augment
with tool-specific rules. Colours follow Textual's dark theme by default; a light-mode toggle
is a v2 feature.

Colour palette (dark theme, applied in `base.tcss`):

| Token            | Value        | Use                                  |
|------------------|--------------|--------------------------------------|
| `$primary`       | `#4fc3f7`    | Selected row highlight, header text  |
| `$secondary`     | `#81c784`    | Status success messages              |
| `$error`         | `#e57373`    | Status error messages                |
| `$surface`       | `#1e1e1e`    | App / pane background                |
| `$border`        | `#444444`    | Divider lines, overlay borders       |
| `$text`          | `#e0e0e0`    | Default text                         |
| `$text-muted`    | `#9e9e9e`    | Footer hints, attendee details       |

These are Textual CSS variables; tools reference them as `color: $primary;` etc.

### 6b. Config persistence

Each tool continues to persist settings via its own owa-tools config function:
- Cal: `owa_cal.config.save_config` / `load_config`
- Mail: `owa_mail.config.save_config` / `load_config`
- Graph: `owa_graph.config.save_config` / `load_config`

owa-tui does not introduce a separate config file. The config location remains wherever
`owa-tools` stores it (typically `~/.config/owa-<tool>/config.json`). This avoids a migration
story and keeps settings visible to the existing CLI.

---

## 7. Coverage Gate

### 7a. Current state

CI (`ci.yml`) runs `pytest -q --cov --cov-fail-under=80`. `pyproject.toml` has
`fail_under = 80` in `[tool.coverage.report]`. Both are consistent at **80%**.

### 7b. Recommendation: raise to **85%** line coverage

**Why 85% and not 95% (owa-tools' gate)?**

owa-tools' 95% gate is achievable because it has no async UI event loop to test — its TUI layer
is curses, which is opaque to pytest, so coverage is measured over pure-Python library code
where 95% is realistic.

owa-tui's codebase has two layers with distinct testability profiles:

- **Pure-Python logic** (fetch functions, render helpers, settings, sort, dates, layout math):
  easily unit-testable; these should hit 95%+ individually.
- **Textual App/Screen/Widget code**: testable with `textual.testing.Pilot`, but Pilot tests
  are inherently slower, more brittle on CI (terminal emulation, timing), and some code paths
  (resize handlers, rare error branches, `on_exception` hooks) are difficult to exercise
  without a real terminal. 10–15% of widget code is realistically in this category.

**85% is the right target** because:
1. It forces meaningful Pilot test coverage (not just the pure-Python layer) — if all Pilot
   tests in plans 10/11 are written, the pure layer alone would carry coverage well past 85%.
2. It leaves headroom for async/event-loop edge cases without requiring `# pragma: no cover`
   on every difficult path.
3. It is a realistic upgrade path: start at 80% (current), land at 85% once plans 10 and 11
   are complete, target 90% in v2 as the Pilot suite matures.

### 7c. Change required to enforce 85%

Two places to update (not done yet — do this when the first tool Screen is implemented and
coverage is measured):

**`.github/workflows/ci.yml`** line:
```yaml
# Change:
run: pytest -q --cov --cov-fail-under=80
# To:
run: pytest -q --cov --cov-fail-under=85
```

**`pyproject.toml`** section:
```toml
[tool.coverage.report]
fail_under = 85   # was 80
```

Until the first tool screen lands and coverage is measured, the 80% gate stays. The
architecture plan records the **intent** to raise to 85%; the implementation plans (10/11)
should note that they are responsible for writing sufficient tests to keep coverage at or above
the 85% target before the gate is raised.

---

## 8. OwaTuiApp Shell (`app.py`)

```python
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, SelectionList

class OwaTuiApp(App):
    """Top-level owa-tui application shell.

    Launched by `owa-tui` entrypoint. Presents a tool-select screen at startup.
    Tool entrypoints (e.g. `owa-cal tui`) call run_tool(tool_name) directly,
    bypassing the select screen.
    """
    TITLE = 'owa-tui'
    CSS_PATH = 'widgets/base.tcss'

    def __init__(self, config: dict, *, tool: str | None = None, debug: bool = False) -> None:
        super().__init__()
        self._config = config
        self._tool = tool   # None → show selector; 'cal'/'mail'/'graph' → push directly
        self._debug = debug

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def on_mount(self) -> None:
        if self._tool:
            self._push_tool(self._tool)
        else:
            self.push_screen(ToolSelectScreen(self._config, debug=self._debug))

    def _push_tool(self, tool: str) -> None:
        from owa_tui.cal.screen import CalScreen
        from owa_tui.mail.screen import MailScreen
        screens = {'cal': CalScreen, 'mail': MailScreen}
        cls = screens.get(tool)
        if cls is None:
            self.exit(message=f'unknown tool: {tool}')
            return
        self.push_screen(cls(self._config, debug=self._debug))
```

### Tool-select screen (v1 stub)

```python
class ToolSelectScreen(Screen):
    BINDINGS = [('q', 'quit', 'Quit')]

    def compose(self) -> ComposeResult:
        yield Label('owa-tui — select a tool', id='title')
        yield SelectionList(('cal — calendar', 'cal'), ('mail — mail', 'mail'))

    def on_selection_list_selected_changed(self, event) -> None:
        tool = event.selection.value
        self.app._push_tool(tool)
```

---

## 9. Entrypoint Wiring

`owa-tui` ships one top-level entrypoint (`owa-tui`) plus re-exports for `owa-cal tui` and
`owa-mail tui`. Each tool's `tui` sub-command (in owa-tools) calls into owa-tui if installed,
or prints a helpful message if it is not.

`src/owa_tui/__init__.py`:

```python
__version__ = '0.1.0'

def main(argv=None):
    import sys
    from owa_tui.app import OwaTuiApp
    from owa_core.auth import get_token
    # ... load config, mint token, run app
    OwaTuiApp(config, debug='--debug' in (argv or sys.argv)).run()
```

Per-tool entrypoints in owa-tools call:
```python
# owa_cal/cli.py cmd_tui():
from owa_tui.app import OwaTuiApp
OwaTuiApp(config, tool='cal', debug=debug).run()
```

---

## 10. Testing Conventions

All tests live in `src/tests/`. Import structure mirrors `src/owa_tui/`.

### Fixtures (shared `conftest.py`)

```python
import pytest
from textual.testing import Pilot

@pytest.fixture
def fake_events():
    return [
        {'id': f'evt{i}', 'subject': f'Event {i}',
         'start': '2026-06-18T09:00:00', 'end': '2026-06-18T10:00:00',
         'isAllDay': False, 'showAs': 'busy', 'categories': [],
         'webLink': f'https://example.test/evt{i}', ...}
        for i in range(3)
    ]

@pytest.fixture
def no_network(monkeypatch):
    """Block any real owa-tools HTTP calls from reaching the network."""
    from owa_cal import api as cal_api
    monkeypatch.setattr(cal_api, 'api_get', lambda *a, **kw: None)
    monkeypatch.setattr(cal_api, 'api_request', lambda *a, **kw: None)
```

### Unit tests (no Pilot)

Tests for pure-Python modules: `fetch.py`, `settings.py`, `render_*` helpers, `sort.py`,
`dates.py`, `menu_state.py`, layout helpers. Use `pytest` + `monkeypatch` only. These run
fast and count heavily toward the 85% target.

### Pilot tests (Textual integration)

Tests for `Screen` and `Widget` classes. Use `textual.testing.Pilot`. The pattern:

```python
import pytest
from textual.testing import Pilot

@pytest.mark.asyncio
async def test_example(monkeypatch, fake_events):
    from owa_tui.cal.screen import CalScreen
    monkeypatch.setattr('owa_tui.cal.fetch.fetch_events',
                        lambda *a, **kw: (fake_events, None))
    async with CalScreen(...).run_test() as pilot:
        await pilot.pause()   # let workers settle
        assert pilot.app.query_one(AgendaList).item_count == 3
```

`await pilot.pause()` (or `await pilot.pause(delay=0.1)`) is the standard idiom to let
`@work` workers complete before asserting. Never use `asyncio.sleep` in tests.

### Coverage exclusions

Add `# pragma: no cover` only for:
- `on_exception` last-resort error hooks
- `if TYPE_CHECKING:` blocks
- `__main__` guard (`if __name__ == '__main__':`)
- Branches that require a real terminal (explicitly documented)

---

## 11. Open Questions (not blocking v1)

1. **Graph screen (v2):** owa-graph's TUI has more complex state (multi-audience token cache,
   bookmarks, history stack, audience overlay). The architecture above accommodates it as a
   `GraphScreen(Screen)` with a per-screen `token_cache: dict[str, TokenInfo]` — the `_ensure_token`
   pattern translates cleanly to a `@work` call. Resolved in plan 30 (not yet authored).

2. **`owa_core.tui_kit.settings` import vs inline copy:** plans 10/11 implement `cycle` /
   `from_config` / `to_config_dict` inline in each tool's `settings.py`. A future cleanup could
   unify under `from owa_core.tui_kit.settings import cycle, from_config, to_config_dict`.
   Either is correct; document the choice in each `settings.py` header.

3. **Snapshot tests:** `pytest-textual-snapshot` (already in dev deps) enables SVG screenshot
   regression tests. These are optional in v1 but should be considered for the settings overlay
   and layout variants (right/bottom/off). One snapshot per layout variant per tool is
   recommended.

4. **`owa-cal tui` / `owa-mail tui` entrypoint coordination:** until owa-tools cuts a release
   that calls into owa-tui, the per-tool `tui` sub-commands in owa-tools and the new
   owa-tui screens will coexist. This is intentional — the delete-from-owa-tools step is Phase B
   (post-v1 release of owa-tui). No compatibility shims needed; the two code paths simply
   exist in parallel until Phase B is merged and owa-tools cuts a major release.
