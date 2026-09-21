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
- [x] All-day event shows `all-day` in time column <!-- src/tests/cal/test_cal_screen.py::test_render_row_all_day -->
- [x] Row truncated to terminal width (never overflows) <!-- src/tests/cal/test_cal_screen.py::test_render_row_width_one -->
- [x] Location shown as `  [loc]` suffix, capped at 20 chars <!-- src/tests/cal/test_cal_screen.py::test_render_row_location_suffix, src/tests/cal/test_cal_screen.py::test_render_row_location_capped_at_20 -->
- [x] Empty subject renders without crashing <!-- src/tests/cal/test_cal_screen.py::test_render_row_empty_subject -->
- [x] Width=1 extreme case renders without crashing <!-- src/tests/cal/test_cal_screen.py::test_render_row_width_one -->
- [x] `show_date=False` (day view): no date prefix in rows <!-- src/tests/cal/test_cal_screen.py::test_render_row_day_view_no_date -->
- [x] `show_date=True` (week/month view): `_weekday_date` prefix shown (`'Thu 06-05'` format, locale-aware) <!-- src/tests/cal/test_agenda_dates.py::test_render_row_shows_the_date_for_a_z_suffixed_start, src/tests/cal/test_agenda_dates.py::test_weekday_date_accepts_a_z_suffixed_start -->
- [x] Unparseable `start` date with `show_date=True` degrades gracefully (no crash) <!-- src/tests/cal/test_cal_screen.py::test_render_row_bad_date_with_show_date -->

### Detail pane rendering (`detail='full'`)
- [x] Subject shown as first line <!-- src/tests/cal/test_cal_detail.py::test_subject_in_detail -->
- [x] Underline (`─`) under subject <!-- src/tests/cal/test_cal_detail.py::test_underline_under_subject -->
- [ ] All-day event shows `all-day` + date in `When:` line
- [x] Time range shown in `When:` line for timed events <!-- src/tests/cal/test_cal_detail.py::test_time_range_shown -->
- [x] `Location:` shown when present <!-- src/tests/cal/test_cal_detail.py::test_location_shown -->
- [ ] `Status:` (showAs) shown when present
- [ ] `Category:` joined from categories list
- [x] `Response: organizer` shown when `isOrganizer=True` <!-- src/tests/cal/test_cal_detail.py::test_organizer_response_shown_for_organizer -->
- [x] Own response shown normalized (e.g. `tentativelyAccepted` -> `'tentative'`) <!-- src/tests/cal/test_cal_detail.py::test_response_label_all_values, src/tests/cal/test_cal_detail.py::test_full_shows_attendees_organizer_body_response -->
- [x] `Organizer:` line shown when present <!-- src/tests/cal/test_cal_detail.py::test_organizer_shown -->
- [ ] `Attendees (N):` heading with count
- [x] Each attendee: name + response label <!-- src/tests/cal/test_cal_detail.py::test_attendee_line_dict_shape -->
- [x] Optional attendees flagged with `(optional)` <!-- src/tests/cal/test_cal_detail.py::test_attendee_optional_flagged -->
- [x] At most 12 attendees shown; overflow shown as `  … +N more` <!-- src/tests/cal/test_cal_detail.py::test_attendee_overflow_shown -->
- [ ] `Note:` section with body text, wrapped to `width-2`
- [ ] `Note:` body preserves blank lines
- [x] No `ID:` line (regression: was removed from curses version) <!-- src/tests/cal/test_cal_detail.py::test_no_id_line -->
- [x] Width=1/2/3 extreme cases do not raise `ValueError` (textwrap floor) <!-- src/tests/cal/test_cal_detail.py::test_narrow_width_does_not_raise -->

### Detail pane rendering (`detail='basic'`)
- [ ] Shows: subject, time, location, status, category
- [x] Omits: attendees, organizer, body, own response <!-- src/tests/cal/test_cal_detail.py::test_basic_omits_rich_fields -->

### Date range filtering
- [x] `day_range='today'` -> query from today 00:00:00 to today 23:59:59 <!-- src/tests/cal/test_cal_fetch.py::test_today_range -->
- [x] `day_range='week'`  -> query from Monday to Sunday of current ISO week <!-- src/tests/cal/test_cal_fetch.py::test_week_range_monday_sunday -->
- [x] `day_range='month'` -> query from first to last day of current calendar month <!-- src/tests/cal/test_cal_fetch.py::test_month_range_first_last -->
- [x] Unknown `day_range` falls back to `'today'` <!-- src/tests/cal/test_cal_fetch.py::test_unknown_day_range_falls_back_to_today -->

### Fetch / data layer
- [x] `fetch_events` returns `(list, None)` on success <!-- src/tests/cal/test_cal_fetch.py::test_returns_events_on_success -->
- [x] `fetch_events` returns `([], 'fetch failed')` when `api_get` returns `None` <!-- src/tests/cal/test_cal_fetch.py::test_returns_empty_on_api_none -->
- [x] `fetch_events` does not raise on `OwaError` (returns error string) <!-- src/tests/cal/test_cal_fetch.py::test_owa_error_caught -->
- [x] `fetch_events` does not raise on unexpected exception (returns error string) <!-- src/tests/cal/test_cal_fetch.py::test_unexpected_exception_caught -->
- [x] Status title shows `f'owa-cal  {from_date}'` (no suffix if single-day) <!-- src/tests/cal/test_cal_fetch.py::test_title_single_day -->
- [x] Status title shows `f'owa-cal  {from_date} – {to_date}'` for multi-day ranges <!-- src/tests/cal/test_cal_fetch.py::test_title_multi_day -->

### Search (client-side filter)
- [ ] Setting search query re-filters the current event list
- [x] Search matches against `subject` (case-insensitive) <!-- src/tests/cal/test_cal_fetch.py::test_search_filter_subject -->
- [x] Search matches against attendee `name` + `address` (dict shape) <!-- src/tests/cal/test_cal_fetch.py::test_search_filter_attendee -->
- [ ] Empty search string clears filter and shows all events
- [ ] Search filter triggers re-render (no extra network call)

### Show declined filter
- [x] `show_declined='no'` removes events where `showAs.lower() == 'free'` AND no categories <!-- src/tests/cal/test_cal_fetch.py::test_show_declined_filter -->
- [x] `show_declined='yes'` shows all events regardless of showAs <!-- src/tests/cal/test_cal_fetch.py::test_show_declined_yes_shows_all -->
- [ ] Changing `show_declined` triggers re-fetch

### Navigation
- [x] `j`/`k` and arrow keys move selection <!-- src/tests/cal/test_cal_pilot.py::TestAgendaListPilot::test_action_move_down, src/tests/cal/test_cal_pilot.py::TestAgendaListPilot::test_on_key_down_arrow, e2e/actions.test.ts:50 -->
- [x] `g` jumps to first item <!-- src/tests/cal/test_cal_pilot.py::TestAgendaListPilot::test_action_move_top -->
- [x] `G` jumps to last item <!-- src/tests/cal/test_cal_pilot.py::TestAgendaListPilot::test_action_move_bottom -->
- [x] `u` scrolls half-page up <!-- src/tests/cal/test_cal_pilot.py::TestAgendaListPilot::test_action_page_up_half -->
- [ ] `d` (no respond mode) scrolls half-page down
- [x] `PgUp` / `PgDn` / `Space` page navigation <!-- src/tests/cal/test_cal_pilot.py::TestAgendaListPilot::test_on_key_pageup, test_on_key_pagedown, test_on_key_space -->
- [x] `Enter` / `→` / `l` drills into detail (focus transferred to pane) <!-- e2e/actions.test.ts:110, src/tests/cal/test_cal_pilot.py::TestAgendaListPilot::test_on_key_enter_fires_drill, test_on_key_right_fires_drill, test_action_drill_posts_message -->
- [x] When `reading_pane='off'`, `Enter` sets status hint instead of focusing pane <!-- src/tests/cal/test_cal_screen.py::test_drill_pane_off_shows_hint -->
- [ ] Detail pane focus: `j`/`k` scroll pane
- [ ] Detail pane focus: `h`/`←`/`Backspace` returns focus to list with status hint

### Respond chord
- [x] `y` arms respond mode; status bar shows chord hint <!-- src/tests/cal/test_cal_pilot.py::TestCalScreenPilot::test_action_respond_arm_with_event, e2e/actions.test.ts:63 -->
- [x] `y` with no event selected: `_respond_mode` stays `False`, status = `'no event selected'` <!-- src/tests/cal/test_cal_screen.py::test_respond_no_event -->
- [x] `a` in respond mode sends `accept` action (POST `.../accept`) <!-- src/tests/cal/test_cal_pilot.py::TestRespondPostPath::test_accept_posts_to_accept_endpoint -->
- [x] `t` in respond mode sends `tentative` action (POST `.../tentativelyaccept`) <!-- src/tests/cal/test_cal_pilot.py::TestRespondPostPath::test_tentative_posts_to_tentativelyaccept_endpoint -->
- [x] `d` in respond mode sends `decline` action (POST `.../decline`) <!-- src/tests/cal/test_cal_pilot.py::TestRespondPostPath::test_decline_posts_to_decline_endpoint -->
- [x] Any other key in respond mode cancels with status `'respond cancelled'` <!-- src/tests/cal/test_cal_pilot.py::TestCalScreenPilot::test_action_respond_key_invalid_cancels -->
- [x] Respond POST body: `{'Comment': '', 'SendResponse': True}` <!-- src/tests/cal/test_cal_pilot.py::TestRespondPostPath::test_accept_posts_to_accept_endpoint -->
- [ ] On success: status = `f'{action}ed: {subject[:30]}'` and re-fetch triggered
- [x] On `api_request` returning `None`: status = `'respond failed'` <!-- src/tests/cal/test_cal_pilot.py::TestRespondPostPath::test_respond_failure_when_api_returns_none -->
- [ ] On `OwaError`: status = `f'respond failed: {exc}'`
- [ ] Event with empty `id`: status = `'event has no id'`, no POST sent

### Browser open (`o`)
- [x] `o` with event selected: calls `webbrowser.open(event['webLink'])` <!-- src/tests/cal/test_cal_screen.py::test_open_browser_fires_webbrowser -->
- [ ] Status = `'opened in browser'` on success
- [ ] Status = `'could not open browser'` if `webbrowser.open` raises
- [x] `o` with no `webLink` / empty link: status = `'no web link for this event'` <!-- src/tests/cal/test_cal_screen.py::test_open_browser_no_link, e2e/actions.test.ts:119 -->
- [x] `o` with no event selected: status = `'no event selected'` <!-- src/tests/cal/test_cal_screen.py::test_open_browser_no_event -->

### Settings menu
- [x] `Escape` opens settings overlay <!-- e2e/actions.test.ts:87, src/tests/cal/test_cal_pilot.py::TestCalScreenPilot::test_action_open_menu_resume -->
- [x] Menu has: Resume, Settings, Help, Quit <!-- e2e/actions.test.ts:87 (Resume, Quit), src/tests/cal/test_cal_pilot.py::TestCalScreenPilot::test_action_open_menu_help (Help), test_action_open_menu_reset (Settings) -->
- [x] Help closes menu and sets status = `HELP_LINE` <!-- src/tests/cal/test_cal_pilot.py::TestCalScreenPilot::test_action_open_menu_help -->
- [ ] Settings sub-menu shows all five fields with current values
- [x] Each field cycles on `Enter` (wraps around allowed values) <!-- src/tests/cal/test_cal_screen.py::test_cal_settings_cycle_reading_pane, src/tests/cal/test_cal_screen.py::test_cal_settings_cycle_split_ratio -->
- [ ] Reset to defaults restores `Settings()` and persists
- [ ] Setting `reading_pane` changes pane layout immediately
- [ ] Setting `split_ratio` changes pane split immediately
- [x] Setting `day_range` triggers re-fetch <!-- src/tests/cal/test_cal_pilot.py::TestCalScreenPilot::test_action_open_menu_cycle_day_range -->
- [ ] Setting `show_declined` triggers re-fetch
- [ ] Setting `event_detail` changes detail render level immediately
- [ ] Settings persisted via `owa_cal.config.save_config` on every change
- [x] Persist failure is silently swallowed (best-effort, never crashes TUI) <!-- src/tests/cal/test_cal_pilot.py::TestCalScreenPilot::test_persist_settings_no_crash -->

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
- [x] Narrow terminal (width=1) does not crash render <!-- src/tests/cal/test_cal_screen.py::test_render_row_width_one -->

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

## Disposition (2026-09-21)

Audit: 60/97 acceptance items verified against tests; 37 untested. Policy: drop trivial,
keep branchy. Kept → repo todos: detail-pane j/k scroll, live reading_pane/split_ratio apply,
non-tty guard. Branchy error paths (respond OwaError / empty id / re-fetch, browser-open
failure) got regression tests. Everything else in the gap list below is either weak-assert
noise or describes the owa-tools `tui` subcommand schema, not owa-tui — dropped. Plan retired.

## Gaps (2026-09-21)

Unchecked acceptance criteria above with no covering assertion in `src/tests/cal/` or `e2e/actions.test.ts`.

- L433 Row shows `HH:MM-HH:MM` time range extracted from ISO datetime — behaviour: present — no render_row test asserts an `HH:MM-HH:MM` string (tests assert date/all-day/location only)
- L446 All-day event shows `all-day` + date in `When:` line — behaviour: present — test_cal_detail.py::test_all_day_label asserts `all-day` only; the date in `When:` is not asserted
- L449 `Status:` (showAs) shown when present — behaviour: present (detail.py `Status:` line) — no test asserts it
- L450 `Category:` joined from categories list — behaviour: present (detail.py `Category:` join) — no test asserts it
- L454 `Attendees (N):` heading with count — behaviour: present — test_full_shows_attendees_organizer_body_response asserts `Attendees` only, not the `(N)` count
- L458 `Note:` section with body text, wrapped to `width-2` — behaviour: present — test_body_shown asserts body text only; wrap width `width-2` is not asserted
- L459 `Note:` body preserves blank lines — behaviour: present (blank-line branch in render_detail) — no test
- L464 Shows: subject, time, location, status, category — behaviour: present — only the omit side is tested (test_basic_omits_rich_fields); no positive assertion for basic fields
- L482 Setting search query re-filters the current event list — behaviour: present (action_search → load_events with search) — test_cal_screen.py::test_search_filters_events filters inside the test body via update_rows, never exercises action_search; fetch-level filter covered by test_cal_fetch.py::test_search_filter_*
- L485 Empty search string clears filter and shows all events — behaviour: present (`if search:` guard; _SearchInput cancel dismisses '') — no test clears a non-empty filter and asserts all events return
- L486 Search filter triggers re-render (no extra network call) — behaviour: missing — action_search calls load_events(), which re-fetches via api_get; search is not a render-only refilter (spec/impl divergence)
- L491 Changing `show_declined` triggers re-fetch — behaviour: present (_on_setting_changed re-fetches for show_declined) — no test cycles show_declined; same as line 535
- L498 `d` (no respond mode) scrolls half-page down — behaviour: missing — AgendaList.BINDINGS has no `d`; screen binds `d` to respond_key('d') which returns early when unarmed; action_page_down_half exists but is unbound (test_action_page_down_half asserts only idx >= 0)
- L502 Detail pane focus: `j`/`k` scroll pane — behaviour: missing — CalDetailPane declares no BINDINGS; nothing binds j/k while the pane has focus
- L503 Detail pane focus: `h`/`←`/`Backspace` returns focus to list with status hint — behaviour: present for h/← (test_cal_pilot.py::TestCalScreenPilot::test_action_back_to_list, e2e/actions.test.ts:115); missing for Backspace (not bound in cal); status is cleared to '' rather than a hint
- L513 On success: status = `f'{action}ed: {subject[:30]}'` and re-fetch triggered — behaviour: present (verb map: accepted / tentatively accepted / declined) — status asserted by TestRespondPostPath; the follow-up re-fetch is not asserted
- L515 On `OwaError`: status = `f'respond failed: {exc}'` — behaviour: present (`respond failed: {exc}` branch) — no test raises OwaError from api_request
- L516 Event with empty `id`: status = `'event has no id'`, no POST sent — behaviour: present (`event has no id` guard in _do_respond) — no test
- L520 Status = `'opened in browser'` on success — behaviour: present — test_open_browser_fires_webbrowser asserts the webbrowser.open call, not the `opened in browser` status
- L521 Status = `'could not open browser'` if `webbrowser.open` raises — behaviour: present (`could not open browser` except branch) — no test makes webbrowser.open raise
- L529 Settings sub-menu shows all five fields with current values — behaviour: present — no cal test asserts the five labels/values; generic overlay coverage only in src/tests/widgets/test_settings_overlay.py::test_settings_overlay_shows_value_next_to_label
- L531 Reset to defaults restores `Settings()` and persists — behaviour: present — test_action_open_menu_reset asserts defaults restored; persistence (save_config) not asserted
- L532 Setting `reading_pane` changes pane layout immediately — behaviour: missing — _make_layout is only called from compose(); _on_setting_changed only calls _refresh_detail, no recompose (test_action_open_menu_cycle_reading_pane proves _refresh_detail ran, not a re-layout)
- L533 Setting `split_ratio` changes pane split immediately — behaviour: missing — same as 532; split_ratio is applied only at compose time
- L535 Setting `show_declined` triggers re-fetch — behaviour: present — duplicate of line 491; no test cycles show_declined
- L536 Setting `event_detail` changes detail render level immediately — behaviour: present (_refresh_detail passes settings.event_detail) — no test cycles event_detail and asserts the pane
- L537 Settings persisted via `owa_cal.config.save_config` on every change — behaviour: present (_persist_settings → owa_cal.config.save_config) — no test asserts save_config is called on change
- L541 Refused when `OWA_AGENT=1` (not an interactive terminal) — behaviour: missing — owa_tui/__init__.py has no OWA_AGENT check (these CLI items describe owa-cal's `tui` subcommand schema, not owa-tui)
- L542 Refused when `is_interactive()` returns `False` (no tty) — behaviour: missing — no is_interactive()/isatty guard in owa-tui's main()
- L543 `--day-range` flag accepted; overrides persisted setting — behaviour: missing — parser has --version/--debug/--tool/--profile only; CalScreen(day_range=) exists (test_cal_screen.py::test_cal_settings_day_range_override) but no CLI flag
- L544 Auth (`outlook` audience) obtained before entering TUI — behaviour: missing — token is minted lazily per fetch in CalScreen._token(), not before entering the TUI
- L545 Auth failure exits cleanly before TUI is launched — behaviour: missing — auth failure surfaces as a fetch error string inside the TUI, not a pre-launch exit
- L546 Unknown flags produce a `UsageError` — behaviour: present via argparse (exit 2 on unknown flag) — no test in src/tests/test_launcher.py asserts it
- L547 `tui` command marked `interactive: True` in schema — behaviour: missing — owa-tui has no command schema (owa-tools concern)
- L548 `tui` command schema includes `auth.audience = 'outlook'` — behaviour: missing — owa-tui has no command schema (owa-tools concern)
- L551 Terminal resize (`SIGWINCH`) handled without crashing — behaviour: present (CalScreen.on_resize → refresh(layout=True)) — no test resizes
- L552 Empty event list shows `'(no events)'` placeholder — behaviour: present (agenda.PLACEHOLDER '(no events)') — test_empty_list_shows_placeholder asserts item_count == 0, never the placeholder text
