# Plan: CAL v1 — Textual rebuild of owa-cal TUI

## Review update — 2026-06-23

This is now a shipped-behavior reference, not an implementation backlog. The live calendar adapter is under `src/owa_tui/screens/cal/`, with pure helpers and settings kept beside the screen. Treat older mentions of `src/owa_tui/cal/` as historical path drift.

Current hardening checklist:

- Keep `fetch_events` on the stable `owa_cal.api` / `owa_cal.events` surface only; no imports from `owa_cal.tui*`.
- Preserve the two-key response flow (`y` then `a`/`t`/`d`) and verify that every patch path updates status and persists the selected response locally.
- Maintain offline coverage for query construction, declined filtering, attendee search, response JSON, and browser-open failures.
- Keep settings persistence best-effort but visible: a failed config write should set a status message or testable warning path, not fail silently.
- Add any live calendar smoke only behind an explicit gate such as `OWA_TUI_LIVE_TESTS=1`; fixture-mode e2e cannot prove real PATCH semantics.

Done criteria for future calendar changes:

- `src/tests/cal/` still covers rendering, fetch, settings, search, respond mode, and edge/error states.
- `e2e/actions.test.ts` or a calendar-specific e2e covers navigation, settings overlay, and the respond chord in fixture mode.
- Full repo gates pass with the repository's chosen coverage threshold.

**Status:** ✅ shipped (commit b12d1cd). Parity covered by `src/tests/cal/` (Pilot)
and `e2e/actions.test.ts` (tui-test, fixture-mode). Code landed under
`src/owa_tui/screens/cal/`, not the `src/owa_tui/cal/` path this plan sketched.
Kept as the behavioural reference; the checklists below are the parity contract.  
**Phase:** B (source files to be deleted from owa-tools after this plan is complete)  
**Parity source:** `owa-tools/src/owa_cal/tui.py`, `tui_menu.py`, `tui_settings.py`  
**Target file:** `owa-tui/src/owa_tui/cal/screen.py` (primary), plus supporting modules listed below

---

## Background

The curses-based owa-cal TUI (`owa_cal.tui`) is a read-focused interactive browser
with a two-pane layout (agenda list + detail pane), a full settings menu, and a
deliberate two-key respond chord (`y` then `a`/`t`/`d`). This plan rebuilds it as a
Textual application keeping complete behavioural parity with the curses version.

The curses layer is opaque to testing; Textual components are testable with
`textual.testing.Pilot`. Every interaction in the existing `test_tui.py` and
`test_tui_actions.py` must be re-expressed as a Pilot test case.

---

## Exact owa-tools imports permitted (per AGENTS.md stable surface)

```python
from owa_cal.api import api_get, api_request, build_query
from owa_cal.events import normalize_events_detail  # returns list[dict]
# also needed for respond:
from owa_cal.api import api_request
```

Do NOT import any curses-layer symbols from `owa_cal.tui`. The render functions
(`render_row`, `render_detail`) and all state machinery are reimplemented in Textual
widgets. The pure data-shaping functions in `owa_cal.events` (`normalize_event`,
`normalize_event_detail`, `normalize_events_detail`, `to_local`, `build_event_json`,
`build_patch_json`) are stable library surface and may be imported freely.

---

## File layout

```
src/owa_tui/cal/
    __init__.py          # empty
    screen.py            # CalScreen — the Textual App/Screen
    agenda.py            # AgendaList widget (ListView subclass)
    detail.py            # DetailPane widget (ScrollableContainer)
    settings_menu.py     # SettingsOverlay (Screen pushed on Esc)
    fetch.py             # async def fetch_events(…) -> list[dict] (worker)
    settings.py          # CalSettings dataclass — copy verbatim from
                         #   owa_cal.tui_settings (do not import from there)
src/tests/cal/
    test_cal_screen.py   # Pilot tests (mirrors test_tui.py + test_tui_actions.py)
    test_cal_detail.py   # unit tests for DetailPane render logic
    test_cal_fetch.py    # unit tests for fetch_events (monkeypatch api_get)
```

---

## Settings (verbatim copy, not import)

Because owa-tui may not import owa-cal internals (only the stable API surface), the
Settings dataclass must be reproduced in `src/owa_tui/cal/settings.py`.

Fields to reproduce exactly:

| Field          | Type | Default  | Allowed values            |
|----------------|------|----------|---------------------------|
| `reading_pane` | str  | `'right'`| `'right'`, `'bottom'`, `'off'` |
| `split_ratio`  | int  | `50`     | `40`, `50`, `60`          |
| `day_range`    | str  | `'today'`| `'today'`, `'week'`, `'month'` |
| `show_declined`| str  | `'no'`   | `'yes'`, `'no'`           |
| `event_detail` | str  | `'full'` | `'full'`, `'basic'`       |

Config key mapping (for persistence via owa-tools `owa_cal.config.save_config`):

```python
_FIELD_TO_KEY = {
    'reading_pane':  'tui_reading_pane',
    'split_ratio':   'tui_split_ratio',
    'day_range':     'tui_day_range',
    'show_declined': 'tui_show_declined',
    'event_detail':  'tui_event_detail',
}
```

`split_ratio` is stored as a string in config; coerce to `int` on load.

---

## Data fetch layer (`fetch.py`)

```python
PAGE_SIZE = 50

async def fetch_events(
    access_token: str,
    api_base: str,
    day_range: str,       # 'today' | 'week' | 'month'
    show_declined: str,   # 'yes' | 'no'
    search: str = '',
    debug: bool = False,
) -> tuple[list[dict], str | None]:
    """Return (events, error_str | None). Never raises."""
```

Internally:
1. Resolve `day_range` -> `(from_date, to_date)` using the same three helpers
   ported verbatim from `tui.py`: `_today_range()`, `_week_range()`, `_month_range()`.
   `_week_range` must import `owa_cal.dates.current_iso_week` and `iso_week_range`
   (these are stable library surface — they are part of `owa_cal`, not `owa_cal.tui`).
2. Build the OData query string via `build_query({...})` with:
   - `startDateTime`, `endDateTime`
   - `$top`: `PAGE_SIZE` (50)
   - `$orderby`: `'Start/DateTime'`
   - `$select`: `'Id,Subject,Start,End,Location,Categories,ShowAs,IsAllDay,OriginalStartTimeZone,OriginalEndTimeZone,Organizer,Attendees,BodyPreview,ResponseStatus,IsOrganizer'`
3. Call `api_get(api_base, f'me/calendarView?{q}', access_token, debug=debug)`.
4. On `None` return: return `([], 'fetch failed')`.
5. Normalize via `normalize_events_detail(data)`.
6. Filter declined: if `show_declined == 'no'`, remove items where
   `showAs.lower() == 'free'` AND `not categories` (same logic as curses version).
7. Apply search filter (client-side): if `search`, keep only items where
   `search.lower()` appears in `subject.lower()` OR in any attendee's
   `name+address` (dict shape) or `str(att)` (bare string shape).
8. Catch `OwaError` -> return `([], f'error: {exc}')`.
9. Catch bare `Exception` -> return `([], f'unexpected error: {exc}')`.

This function is called from a Textual `worker` (see `screen.py` below) so it must
be `async def` and use `asyncio.to_thread` to wrap the synchronous `api_get` call.

---

## Widgets

### `AgendaList` (`agenda.py`)

Subclass `textual.widgets.ListView` (or `DataTable` if row rendering flexibility is
needed — ListView is preferred for simplicity).

```python
class AgendaList(ListView):
    """Scrollable event list. Each row is rendered by render_row()."""
```

Render each row by calling the port of `render_row` (see below).

**`render_row(event, width, *, show_date=False) -> str`** — port verbatim from
`owa_cal.tui.render_row`. Logic:
- Extract `HH:MM-HH:MM` from ISO datetime fields.
- `isAllDay=True` -> time column shows `'all-day'`.
- `show_date=True` (week/month views) -> prefix `_weekday_date(start)` (10 chars,
  locale-aware `strftime('%a %m-%d')`).
- Date column: 10 chars; time column: 12 chars.
- Subject truncated to fill remaining width; location appended as `  [loc[:20]]`.
- Total row capped at `width`.

Bindings on `AgendaList`:
- `j` / `k` / `↑` / `↓` — move selection (inherited from ListView)
- `g` / `G` — jump to top / bottom
- `u` / `d` — half-page up / down
- `PgUp` / `PgDn` / `Space` — page up / down
- `enter` / `→` / `l` — drill into detail (fires `on_drill`)
- `h` / `←` / `Backspace` — back (no-op in v1; sets status)
- `/` — open search modal
- `r` — refresh
- `y` — arm respond mode (sets `_respond_mode = True`, updates status bar)
- `a` / `t` / `d` — if `_respond_mode`, fire respond action; else normal nav
- `o` — open in browser
- `Escape` — open SettingsOverlay

### `DetailPane` (`detail.py`)

Subclass `textual.widgets.Static` inside a `textual.widgets.ScrollableContainer`.

```python
class DetailPane(ScrollableContainer):
    """Scrollable event detail. Content set via update_event(event, detail_level)."""
```

**`render_detail(event, width, *, detail='full') -> list[str]`** — port verbatim
from `owa_cal.tui.render_detail`. Sections in order:

1. Subject line
2. Underline (`─` * min(len(subject), width))
3. `When:` — `all-day` + date, or ISO range
4. `Location:` (if present)
5. `Status:` = `showAs` (if present)
6. `Category:` = joined `categories` (if present)
7. **Full only:**
   - `Response:` — `'organizer'` if `isOrganizer`, else normalized own response label
   - `Organizer:` (if present)
   - Blank line + `Attendees (N):` heading + up to 12 attendee lines via
     `_attendee_line(att, width)`, then `  … +N more` if overflow
   - Blank line + `Note:` heading + body lines wrapped to `max(width-2, 1)` chars

`_response_label(resp)` mapping (port verbatim):
```python
_RESPONSE_LABEL = {
    'accepted': 'accepted',
    'declined': 'declined',
    'tentativelyaccepted': 'tentative',
    'tentative': 'tentative',
    'notresponded': 'no reply',
    'none': 'no reply',
    'organizer': 'organizer',
}
```

`_attendee_line(att, width)` — handles both dict shape `{name, address, type, response}`
and bare string. Format: `  {name} — {response}[ (optional)]`.

When focus is in the list, DetailPane reflects the currently selected event.
When `Enter` is pressed in the list, keyboard focus transfers to DetailPane.
In DetailPane focus: `j`/`k`/`↑`/`↓` scroll the pane; `h`/`←` returns focus to
the list (status bar shows discoverable hint `'detail focus — j/k scroll · h/← back'`).

When `reading_pane == 'off'`, `Enter` in the list sets status
`'enable the reading pane (Esc → Settings) to view details'` (no focus change).

### `SettingsOverlay` (`settings_menu.py`)

Pushed as a Textual `Screen` when `Escape` is pressed in the main screen.

Top-level menu items (rendered as a centred overlay box):
1. Resume
2. Settings (navigates to settings sub-screen within same overlay)
3. Help (pops overlay, sets status = `HELP_LINE`)
4. Quit

Settings sub-screen items (each cycles to next allowed value on `Enter`):
- Reading pane: right / bottom / off
- Split ratio: 40 / 50 / 60
- Day range: today / week / month
- Show declined: yes / no
- Event detail: full / basic
- (Reset to defaults)
- Back

On any `cycle:` action:
- Mutate `CalSettings` (immutable dataclass: use `dataclasses.replace`).
- Persist via `owa_cal.config.save_config` (best-effort; never crash).
- Invalidate detail cache (force re-render).
- If changed field is `day_range` or `show_declined`, trigger re-fetch.
- Field `event_detail` changes detail render level immediately.

---

## `CalScreen` (`screen.py`)

```python
class CalScreen(App):
    """Main owa-cal Textual App."""
    TITLE = 'owa-cal'
    CSS_PATH = 'cal.tcss'
```

Constructor signature:
```python
def __init__(
    self,
    config: dict,
    access_token: str,
    api_base: str,
    *,
    debug: bool = False,
    day_range: str = '',
) -> None:
```

On compose, apply `day_range` override (same logic as curses `build_session`:
if value is in `('today', 'week', 'month')`, override `settings.day_range`).

Layout driven by `settings.reading_pane` and `settings.split_ratio`:
- `'right'`: horizontal `Horizontal` container — `AgendaList` left (ratio %),
  `Vertical` divider 1 col, `DetailPane` right
- `'bottom'`: vertical `Vertical` container — `AgendaList` top (ratio %),
  `Horizontal` rule 1 row, `DetailPane` bottom
- `'off'`: `AgendaList` fills full screen; `DetailPane` hidden

Status bar: `Label` at bottom, reactive to `_status` reactive attribute.

Header: `Label` at top showing `f'owa-cal  {from_date}'` (with `'– {to_date}'`
suffix when `to_date != from_date`).

Footer: static hint `'j/k move · enter detail · / search · r refresh · y respond (a/t/d) · o browser · esc menu · q quit'`

### State fields on `CalScreen`

```python
_events: reactive[list[dict]] = reactive([])
_status: reactive[str] = reactive('')
_search: str = ''
_respond_mode: bool = False
_settings: CalSettings  # mutated via dataclasses.replace
```

### Event loading (worker)

```python
@work(exclusive=True)
async def load_events(self) -> None:
    events, err = await fetch_events(
        self._access_token, self._api_base,
        self._settings.day_range, self._settings.show_declined,
        self._search, self._debug,
    )
    self._events = events
    self._status = err or ''
    self.query_one(AgendaList).update_rows(events, show_date=self._settings.day_range != 'today')
    if self.query_one(AgendaList).index is not None:
        self._refresh_detail()
```

Trigger `load_events()` on: mount, refresh (`r`), settings changes that affect
data (`day_range`, `show_declined`), and after a search query is submitted.

### Respond action flow

```
y (in list focus)
  -> _respond_mode = True
  -> status = 'respond: (a)ccept · (t)entative · (d)ecline · any other key cancels'

a / t / d (when _respond_mode is True)
  -> _respond_mode = False
  -> _do_respond(state, action)   # action in ('accept', 'tentative', 'decline')

any other key (when _respond_mode is True)
  -> _respond_mode = False
  -> status = 'respond cancelled'
```

**`_do_respond(action: str) -> None`** (async, runs in worker):
1. Get current event from list selection.
2. Verify `event.get('id')` is non-empty; else set status `'event has no id'`.
3. Map action to REST segment: `'accept'` -> `'accept'`, `'tentative'` -> `'tentativelyaccept'`, `'decline'` -> `'decline'`.
4. Build endpoint: `f'me/events/{urllib.parse.quote(event_id, safe="")}/{rest_action}'`
5. POST body: `{'Comment': '', 'SendResponse': True}`
6. Call `api_request('POST', api_base, endpoint, access_token, body=body, debug=debug)`.
7. On `None` result: status `'respond failed'`.
8. On `OwaError`: status `f'respond failed: {exc}'`.
9. On success: status `f'{action}ed: {subject[:30]}'` and trigger `load_events()`.

### Browser open action (`o`)

```python
def action_open_browser(self) -> None:
    item = self._current_event()
    if item is None:
        self._status = 'no event selected'
        return
    link = item.get('webLink') or item.get('web_link') or ''
    if link:
        import webbrowser
        try:
            webbrowser.open(link)
            self._status = 'opened in browser'
        except Exception:
            self._status = 'could not open browser'
    else:
        self._status = 'no web link for this event'
```

### Resize handling

Textual handles terminal resize natively. Re-layout on `on_resize` by
calling `self.refresh(layout=True)`.

### Error display

On fetch errors, display the error string in the status bar. A last-resort
`on_exception` hook logs to stderr without crashing the app.

---

## Key bindings summary

| Key(s)            | Context         | Action                                      |
|-------------------|-----------------|---------------------------------------------|
| `j` / `↓`        | list            | move selection down                         |
| `k` / `↑`        | list            | move selection up                           |
| `g`               | list            | jump to first                               |
| `G`               | list            | jump to last                                |
| `u`               | list            | half-page up                                |
| `d` (no respond)  | list            | half-page down                              |
| `PgUp`            | list            | page up                                     |
| `PgDn` / `Space`  | list            | page down                                   |
| `Enter` / `→` / `l` | list         | drill / focus detail pane                   |
| `h` / `←` / `Bksp` | detail        | return focus to list                        |
| `j` / `k` / `↑` / `↓` | detail   | scroll detail pane                          |
| `/`               | list            | open search modal                           |
| `r`               | list            | refresh events                              |
| `y`               | list            | arm respond mode                            |
| `a`               | respond mode    | accept                                      |
| `t`               | respond mode    | tentative                                   |
| `d`               | respond mode    | decline                                     |
| any other         | respond mode    | cancel respond mode                         |
| `o`               | list            | open event in browser                       |
| `Escape`          | list/detail     | open settings overlay                       |
| `q`               | anywhere        | quit                                        |

Note: `d` for half-page-down and `d` for decline are mutually exclusive by context
(respond mode gate), matching the curses design intent.

---

## Parity checklist

Every item below maps directly to an interaction in `owa_cal/tui.py`.

### Agenda list rendering
- [ ] Row shows `HH:MM-HH:MM` time range extracted from ISO datetime
- [ ] All-day event shows `all-day` in time column
- [ ] Row truncated to terminal width (never overflows)
- [ ] Location shown as `  [loc]` suffix, capped at 20 chars
- [ ] Empty subject renders without crashing
- [ ] Width=1 extreme case renders without crashing
- [ ] `show_date=False` (day view): no date prefix in rows
- [ ] `show_date=True` (week/month view): `_weekday_date` prefix shown (`'Thu 06-05'` format, locale-aware)
- [ ] Unparseable `start` date with `show_date=True` degrades gracefully (no crash)

### Detail pane rendering (`detail='full'`)
- [ ] Subject shown as first line
- [ ] Underline (`─`) under subject
- [ ] All-day event shows `all-day` + date in `When:` line
- [ ] Time range shown in `When:` line for timed events
- [ ] `Location:` shown when present
- [ ] `Status:` (showAs) shown when present
- [ ] `Category:` joined from categories list
- [ ] `Response: organizer` shown when `isOrganizer=True`
- [ ] Own response shown normalized (e.g. `tentativelyAccepted` -> `'tentative'`)
- [ ] `Organizer:` line shown when present
- [ ] `Attendees (N):` heading with count
- [ ] Each attendee: name + response label
- [ ] Optional attendees flagged with `(optional)`
- [ ] At most 12 attendees shown; overflow shown as `  … +N more`
- [ ] `Note:` section with body text, wrapped to `width-2`
- [ ] `Note:` body preserves blank lines
- [ ] No `ID:` line (regression: was removed from curses version)
- [ ] Width=1/2/3 extreme cases do not raise `ValueError` (textwrap floor)

### Detail pane rendering (`detail='basic'`)
- [ ] Shows: subject, time, location, status, category
- [ ] Omits: attendees, organizer, body, own response

### Date range filtering
- [ ] `day_range='today'` -> query from today 00:00:00 to today 23:59:59
- [ ] `day_range='week'`  -> query from Monday to Sunday of current ISO week
- [ ] `day_range='month'` -> query from first to last day of current calendar month
- [ ] Unknown `day_range` falls back to `'today'`

### Fetch / data layer
- [ ] `fetch_events` returns `(list, None)` on success
- [ ] `fetch_events` returns `([], 'fetch failed')` when `api_get` returns `None`
- [ ] `fetch_events` does not raise on `OwaError` (returns error string)
- [ ] `fetch_events` does not raise on unexpected exception (returns error string)
- [ ] Status title shows `f'owa-cal  {from_date}'` (no suffix if single-day)
- [ ] Status title shows `f'owa-cal  {from_date} – {to_date}'` for multi-day ranges

### Search (client-side filter)
- [ ] Setting search query re-filters the current event list
- [ ] Search matches against `subject` (case-insensitive)
- [ ] Search matches against attendee `name` + `address` (dict shape)
- [ ] Empty search string clears filter and shows all events
- [ ] Search filter triggers re-render (no extra network call)

### Show declined filter
- [ ] `show_declined='no'` removes events where `showAs.lower() == 'free'` AND no categories
- [ ] `show_declined='yes'` shows all events regardless of showAs
- [ ] Changing `show_declined` triggers re-fetch

### Navigation
- [ ] `j`/`k` and arrow keys move selection
- [ ] `g` jumps to first item
- [ ] `G` jumps to last item
- [ ] `u` scrolls half-page up
- [ ] `d` (no respond mode) scrolls half-page down
- [ ] `PgUp` / `PgDn` / `Space` page navigation
- [ ] `Enter` / `→` / `l` drills into detail (focus transferred to pane)
- [ ] When `reading_pane='off'`, `Enter` sets status hint instead of focusing pane
- [ ] Detail pane focus: `j`/`k` scroll pane
- [ ] Detail pane focus: `h`/`←`/`Backspace` returns focus to list with status hint

### Respond chord
- [ ] `y` arms respond mode; status bar shows chord hint
- [ ] `y` with no event selected: `_respond_mode` stays `False`, status = `'no event selected'`
- [ ] `a` in respond mode sends `accept` action (POST `.../accept`)
- [ ] `t` in respond mode sends `tentative` action (POST `.../tentativelyaccept`)
- [ ] `d` in respond mode sends `decline` action (POST `.../decline`)
- [ ] Any other key in respond mode cancels with status `'respond cancelled'`
- [ ] Respond POST body: `{'Comment': '', 'SendResponse': True}`
- [ ] On success: status = `f'{action}ed: {subject[:30]}'` and re-fetch triggered
- [ ] On `api_request` returning `None`: status = `'respond failed'`
- [ ] On `OwaError`: status = `f'respond failed: {exc}'`
- [ ] Event with empty `id`: status = `'event has no id'`, no POST sent

### Browser open (`o`)
- [ ] `o` with event selected: calls `webbrowser.open(event['webLink'])`
- [ ] Status = `'opened in browser'` on success
- [ ] Status = `'could not open browser'` if `webbrowser.open` raises
- [ ] `o` with no `webLink` / empty link: status = `'no web link for this event'`
- [ ] `o` with no event selected: status = `'no event selected'`

### Settings menu
- [ ] `Escape` opens settings overlay
- [ ] Menu has: Resume, Settings, Help, Quit
- [ ] Help closes menu and sets status = `HELP_LINE`
- [ ] Settings sub-menu shows all five fields with current values
- [ ] Each field cycles on `Enter` (wraps around allowed values)
- [ ] Reset to defaults restores `Settings()` and persists
- [ ] Setting `reading_pane` changes pane layout immediately
- [ ] Setting `split_ratio` changes pane split immediately
- [ ] Setting `day_range` triggers re-fetch
- [ ] Setting `show_declined` triggers re-fetch
- [ ] Setting `event_detail` changes detail render level immediately
- [ ] Settings persisted via `owa_cal.config.save_config` on every change
- [ ] Persist failure is silently swallowed (best-effort, never crashes TUI)

### CLI entrypoint
- [ ] Refused when `OWA_AGENT=1` (not an interactive terminal)
- [ ] Refused when `is_interactive()` returns `False` (no tty)
- [ ] `--day-range` flag accepted; overrides persisted setting
- [ ] Auth (`outlook` audience) obtained before entering TUI
- [ ] Auth failure exits cleanly before TUI is launched
- [ ] Unknown flags produce a `UsageError`
- [ ] `tui` command marked `interactive: True` in schema
- [ ] `tui` command schema includes `auth.audience = 'outlook'`

### Resize / edge cases
- [ ] Terminal resize (`SIGWINCH`) handled without crashing
- [ ] Empty event list shows `'(no events)'` placeholder
- [ ] Narrow terminal (width=1) does not crash render

---

## Pilot test cases (mirrors existing tests)

Each test uses `textual.testing.Pilot`; no real network calls (monkeypatch `api_get`).

### `test_cal_screen.py`

```python
# T1: basic render — events loaded and displayed
async def test_events_appear_in_list(monkeypatch):
    # monkeypatch api_get to return two events
    # mount CalScreen, await worker
    # assert AgendaList has 2 items
    # assert first item shows expected time string

# T2: search filter
async def test_search_filters_events(monkeypatch):
    # mount with two events
    # send '/' + search query + Enter
    # assert only matching event remains in list

# T3: respond chord — accept
async def test_respond_accept_posts_to_api(monkeypatch):
    # monkeypatch api_request to capture calls
    # mount with one event, select it
    # press 'y', then 'a'
    # assert api_request called with endpoint ending '/accept'
    # assert status starts with 'accepted'

# T4: respond chord — tentative endpoint
async def test_respond_tentative_endpoint(monkeypatch):
    # same as T3 but press 't'
    # assert endpoint ends '/tentativelyaccept'

# T5: respond chord cancel
async def test_respond_chord_cancel(monkeypatch):
    # press 'y', then 'x'
    # assert status == 'respond cancelled'
    # assert no api_request called

# T6: respond with no event
async def test_respond_no_event(monkeypatch):
    # mount with empty event list
    # press 'y'
    # assert _respond_mode is False
    # assert status == 'no event selected'

# T7: drill — focuses detail pane
async def test_drill_focuses_detail(monkeypatch):
    # mount with one event, reading_pane='right'
    # press Enter
    # assert DetailPane has focus
    # assert status contains 'back'

# T8: drill with pane off
async def test_drill_pane_off_shows_hint(monkeypatch):
    # mount with reading_pane='off'
    # press Enter on event
    # assert focus remains in AgendaList
    # assert 'reading pane' in status

# T9: back from detail
async def test_back_from_detail_returns_to_list(monkeypatch):
    # drill into detail, then press 'h'
    # assert AgendaList has focus

# T10: refresh
async def test_refresh_triggers_reload(monkeypatch):
    # mount, track api_get call count
    # press 'r'
    # assert api_get called again

# T11: open browser
async def test_open_browser_fires_webbrowser(monkeypatch):
    # monkeypatch webbrowser.open
    # mount with event that has webLink
    # press 'o'
    # assert webbrowser.open called with event's webLink

# T12: open browser — no link
async def test_open_browser_no_link(monkeypatch):
    # mount with event, webLink=''
    # press 'o'
    # assert status == 'no web link for this event'

# T13: settings cycle day_range triggers re-fetch
async def test_settings_day_range_triggers_refetch(monkeypatch):
    # open settings overlay, navigate to Day range, press Enter
    # assert api_get called second time

# T14: render_row week view date prefix
async def test_render_row_week_view_shows_date():
    # call render_row(event, 80, show_date=True)
    # assert '06-05' in row (for event with start='2026-06-05T...')

# T15: render_row day view no date prefix
async def test_render_row_day_view_no_date():
    # call render_row(event, 80, show_date=False)
    # assert '06-05' not in row

# T16: empty list placeholder
async def test_empty_list_shows_placeholder(monkeypatch):
    # monkeypatch api_get to return {'value': []}
    # assert placeholder text '(no events)' visible
```

### `test_cal_detail.py` (pure unit tests, no Pilot)

```python
# mirrors TestRenderDetail from test_tui.py

def test_subject_in_detail(): ...
def test_time_range_shown(): ...
def test_location_shown(): ...
def test_organizer_shown(): ...
def test_body_shown(): ...
def test_all_day_label(): ...
def test_returns_list_of_strings(): ...
def test_full_shows_attendees_organizer_body_response(): ...
def test_basic_omits_rich_fields(): ...
def test_no_id_line(): ...
def test_organizer_response_shown_for_organizer(): ...
def test_narrow_width_does_not_raise(): ...  # width 1, 2, 3
def test_attendee_optional_flagged(): ...
def test_attendee_bare_string_shape(): ...
def test_attendee_overflow_shown(): ...      # > 12 attendees -> '… +N more'
def test_response_label_all_values(): ...    # all keys in _RESPONSE_LABEL
```

### `test_cal_fetch.py` (pure unit tests, no Pilot)

```python
# mirrors TestFetchItems from test_tui.py

async def test_returns_events_on_success(monkeypatch): ...
async def test_returns_empty_on_api_none(monkeypatch): ...
async def test_does_not_raise_on_error(monkeypatch): ...
async def test_search_filter_subject(monkeypatch): ...
async def test_search_filter_attendee(monkeypatch): ...
async def test_show_declined_filter(monkeypatch): ...
async def test_owa_error_caught(monkeypatch): ...
async def test_unexpected_exception_caught(monkeypatch): ...
async def test_title_single_day(): ...       # from_date == to_date
async def test_title_multi_day(): ...        # week/month range
```

---

## Verify step

The following checklist covers every distinct interaction present in `owa_cal/tui.py`.
Use this as the final gating check before marking the plan complete.

- [x] `render_row` — all branch paths (timed, all-day, show_date, width edge cases)
- [x] `render_detail` — full vs basic; attendee shapes; response labels; body wrap; narrow width
- [x] `_build_event_query` / `fetch_events` — query string construction; success; failure; search; show_declined
- [x] `on_search` — sets `_search`, triggers re-render
- [x] `on_refresh` — triggers re-fetch
- [x] `on_drill` — focus to detail; pane-off hint
- [x] `on_back` — returns focus to list (no navigation stack in v1)
- [x] `on_menu_action` — help; reset_settings; cycle:field (each field variant); day_range/show_declined re-fetch gate
- [x] `_persist_settings` — called on every cycle; failure silently swallowed
- [x] `_enter_respond_mode` (`y`) — arms mode; no-event guard
- [x] `_do_respond` (`a`/`t`/`d`) — each action; endpoint mapping; empty-id guard; api failure; owa error; success + re-fetch
- [x] `_do_open_browser` (`o`) — with link; without link; no event
- [x] `_KEY_RESPOND`=`y`, `_KEY_OPEN`=`o` wired in actions dict
- [x] `_RESPOND_KEYS` = `{a: accept, t: tentative, d: decline}`
- [x] `build_session` / `CalScreen.__init__` — day_range override; unknown day_range ignored
- [x] `_cal_loop` — respond chord consumes second key before normal dispatch; resize handling
- [x] CLI: non-interactive refusal; agent-mode refusal; `--day-range` flag; auth before TUI entry
- [x] Footer `HELP_LINE` text wired to spec
- [x] `empty_text='(no events)'` wired to spec
- [x] Settings: all five fields cycle; reset; persist; layout-affecting fields re-layout immediately

Total parity items: 55 discrete interactions mapped.
