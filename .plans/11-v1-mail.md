# Plan 11 — owa-tui v1 Mail Screen

## Review update — 2026-06-23

This is a shipped-behavior reference. The live mail screen is the single module `src/owa_tui/screens/mail.py`, with pure mail helpers under `src/owa_tui/mail/`. Older instructions that expect `src/owa_tui/mail/screen.py`, `message_list.py`, or `reader_pane.py` are blueprint drift unless a future refactor deliberately splits the module.

Current hardening checklist:

- Keep list fetch and body fetch on `owa_mail.api` / `owa_mail.messages`; do not import `owa_mail.tui*`.
- Preserve lazy body fetch caching by message id, including the failure path that leaves the list usable and reports status.
- Keep sort/date helpers pure and separately tested. The screen should consume helper results rather than duplicate ordering or date parsing.
- Verify read/unread toggles, browser-open failure, cancelled search, and empty folder behavior in offline tests.
- Keep live mail smoke optional and gated; default tests must not contact Microsoft Graph or Outlook.

Done criteria for future mail changes:

- `src/tests/mail/` covers sort, dates, settings, list rendering, reader mode, fetch failures, search, and read/unread PATCH behavior.
- Fixture e2e exercises list navigation, reader entry/back, settings overlay, and at least one status-bar error branch.
- Full repo gates pass with the repository's chosen coverage threshold.

**Status:** ✅ shipped (commit b12d1cd). Implemented as a single `src/owa_tui/screens/mail.py`
(plus `src/owa_tui/mail/` helpers), not the multi-file `mail/` tree this plan sketched.
Covered by `src/tests/mail/` (Pilot) and `e2e/actions.test.ts` (tui-test, fixture-mode).
Kept as the behavioural reference.

## Objective

Port the `owa-mail` interactive TUI from its curses implementation in
`owa-tools` to a Textual-based `MailScreen` in `owa-tui`. The curses
source is being deleted in Phase B of the split; this plan is the
authoritative reference extracted from that live source.

---

## Files to create

| Path | Purpose |
|---|---|
| `src/owa_tui/mail/__init__.py` | Package marker |
| `src/owa_tui/mail/screen.py` | `MailScreen` — main Textual screen |
| `src/owa_tui/mail/message_list.py` | `MessageList` widget (scrollable list) |
| `src/owa_tui/mail/reader_pane.py` | `ReaderPane` widget (inline / full reader) |
| `src/owa_tui/mail/sort.py` | Pure sort logic ported from `tui_sort.py` |
| `src/owa_tui/mail/dates.py` | Pure date formatters ported from `tui_dates.py` |
| `src/owa_tui/mail/settings.py` | `MailSettings` dataclass + cycle / persist |
| `src/owa_tui/mail/list_row.py` | `list_row()` row renderer (from `tui_layout.list_row`) |
| `src/tests/mail/__init__.py` | Package marker |
| `src/tests/mail/test_sort.py` | Port of `test_tui_sort.py` |
| `src/tests/mail/test_dates.py` | Port of `test_tui_dates.py` |
| `src/tests/mail/test_list_row.py` | Port of layout tests from `test_tui.py` |
| `src/tests/mail/test_settings.py` | Port of `test_tui_settings.py` |
| `src/tests/mail/test_screen.py` | Pilot tests for `MailScreen` via Textual pilot |

---

## Pure logic to port (framework-agnostic)

These two modules contain **zero curses / zero I/O**. Port them verbatim
(rename only, keep identical logic and docstrings):

### `src/owa_tui/mail/sort.py`

Source: `owa_tools/src/owa_mail/tui_sort.py`

- Copy the entire file unchanged.
- Public API: `sort_messages(messages: list[dict], sort_by: str) -> list[dict]`
- Supported `sort_by` values (frozenset `_SORT_KEYS`):
  - `date_desc` — newest first by `received`; missing dates sort last
  - `date_asc` — oldest first by `received`; missing dates sort last
  - `sender` — A-Z by `from` casefold; missing last
  - `subject` — A-Z by `subject` casefold; missing last
  - `unread_first` — unread (is_read=False/None) group 0, read group 1; newest-first within each group using `_Desc` wrapper
- Unknown `sort_by` falls back to `date_desc` silently.
- Input list is never mutated (returns a new list).
- Key helpers to keep: `_key_date_desc`, `_key_date_asc`, `_key_sender`,
  `_key_subject`, `_key_unread_first`, `_Desc`.

### `src/owa_tui/mail/dates.py`

Source: `owa_tools/src/owa_mail/tui_dates.py`

- Copy the entire file unchanged.
- Public API:
  - `format_received(iso: str, fmt: str, custom: str = "") -> str`
  - `validate_custom_format(s: str) -> bool`
- Supported `fmt` values: `iso8601`, `ddmm`, `ddmm_hhmm`, `custom`.
- `iso8601` → `"%Y-%m-%d"` (10 chars)
- `ddmm` → `"%d.%m"` (5 chars)
- `ddmm_hhmm` → `"%d.%m %H:%M"` (11 chars)
- `custom` → user-supplied strftime string; falls back to `"%Y-%m-%d"` if
  `custom` is empty; returns `""` if strftime raises.
- Empty or unparseable `iso` → returns `""`.
- Strips trailing `Z` and fixed offset (`+HH:MM` / `-HH:MM`) before parsing.
- Parses formats in order: `%Y-%m-%dT%H:%M:%S`, `%Y-%m-%dT%H:%M`, `%Y-%m-%d`.
- `validate_custom_format` uses a fixed sample datetime (`2000-01-02 03:04:05`)
  and returns `False` on empty string, whitespace-only, or strftime error.
  Note: `%Z` on a naive datetime returns `""` → returns `False`.

### `src/owa_tui/mail/list_row.py`

Source: `owa_tools/src/owa_mail/tui_layout.py` (`list_row` function only)

- Port `list_row(msg, width, *, date_fmt="iso8601", custom_fmt="") -> str`.
- Layout: `<date> <*!@> <sender ~30%>  <subject fills rest>`
- Fixed column widths by format:
  - `iso8601`: 10, `ddmm`: 5, `ddmm_hhmm`: 11, `custom`: 10 (default)
- Marker column (3 chars): unread=`*`/` `, flag=`!`/` ` (flag=`"Flagged"`), attachment=`@`/` `
- Sender gets `max(min(int(remaining * 0.30), remaining - sep - 1), 0)` cols.
- Subject fills the rest; `sep = "  "` (2 chars).
- Final output hard-truncated to `width` via `truncate_ellipsis`.
- Import `format_received` from `owa_tui.mail.dates` (not from owa_mail).
- Import `truncate_ellipsis` from `owa_core.tui_kit.layout` (still available
  via owa-tools stable API).

---

## Imports from owa-tools stable API

Per `AGENTS.md`, owa-tui may only import:

```python
from owa_mail.api import api_get, api_request, build_query
from owa_mail.messages import build_list_query, normalize_messages, normalize_message
```

The `api_get` / `api_request` signatures:

```python
def api_get(base: str, endpoint: str, access_token: str, debug: bool = False) -> dict | None: ...
def api_request(method, base, endpoint, access_token, body=None, debug=False) -> dict | None: ...
def build_query(params: dict) -> str: ...
```

`build_list_query` signature (from `owa_mail.messages`):

```python
def build_list_query(
    unread=False, sender='', subject_q='', search='',
    since='', until='', limit=25, select=None
) -> dict: ...
```

`normalize_messages(data, keep_body=False) -> list[dict]` — normalises the
`value` array from a Graph messages response to snake_case dicts.

`normalize_message(raw) -> dict` — normalises a single message (used when
fetching the full body for the reader).

Normalised message dict keys used by the TUI:

| Key | Type | Notes |
|---|---|---|
| `id` | str | Graph message ID |
| `conversation_id` | str | Thread grouping |
| `received` | str | ISO 8601 e.g. `"2026-05-11T09:30:00Z"` |
| `subject` | str | May be empty → render as `"(no subject)"` |
| `from` | str | Display name + address, e.g. `"Alice <alice@x.com>"` |
| `preview` | str | BodyPreview (≤255 chars) |
| `is_read` | bool | |
| `has_attachments` | bool | |
| `flag` | str | `"Flagged"` or `"NotFlagged"` |
| `web_link` | str | OWA deep link for browser open |
| `body` | str | Only present when fetched with body |
| `body_type` | str | `"html"` or `"text"` |
| `importance` | str | `"Low"` / `"Normal"` / `"High"` |

---

## Settings model (`src/owa_tui/mail/settings.py`)

Port from `owa_tools/src/owa_mail/tui_settings.py`. The settings are stored
in the owa-tools config file via `owa_mail.config.save_config` / `load_config`
(same file as owa-mail uses — owa-tui shares the user's mail config).

```python
from dataclasses import dataclass
from typing import Final

READING_PANE_VALUES: Final[tuple[str, ...]] = ('right', 'bottom', 'off')
SPLIT_RATIO_VALUES: Final[tuple[int, ...]] = (40, 50, 60)
SORT_BY_VALUES: Final[tuple[str, ...]] = (
    'date_desc', 'date_asc', 'sender', 'subject', 'unread_first',
)
DATE_FORMAT_VALUES: Final[tuple[str, ...]] = ('iso8601', 'ddmm', 'ddmm_hhmm', 'custom')

@dataclass(frozen=True)
class MailSettings:
    reading_pane: str = 'right'   # 'right' | 'bottom' | 'off'
    split_ratio: int = 50         # 40 | 50 | 60  (% for the list pane)
    sort_by: str = 'date_desc'
    date_format: str = 'iso8601'
    date_custom: str = ''

DEFAULTS = MailSettings()
```

Public helpers to implement (same semantics as the owa_mail originals):

- `cycle(settings: MailSettings, field: str) -> MailSettings` — advance field
  to next allowed value, wrapping. `date_custom` is free-text; calling cycle
  on it returns the same object unchanged. Unknown field raises `ValueError`.
- `from_config(config: dict) -> MailSettings` — read from raw config dict;
  unknown/invalid values fall back to defaults; `split_ratio` is coerced to
  `int`.
- `to_config_dict(settings: MailSettings) -> dict[str, str]` — serialise to
  `{tui_reading_pane, tui_split_ratio, tui_sort_by, tui_date_format, tui_date_custom}`.

Config key mapping:

| Field | Config key |
|---|---|
| `reading_pane` | `tui_reading_pane` |
| `split_ratio` | `tui_split_ratio` |
| `sort_by` | `tui_sort_by` |
| `date_format` | `tui_date_format` |
| `date_custom` | `tui_date_custom` |

Do **not** import `owa_core.tui_kit.settings` (that is an internal owa_mail
detail, not on the stable API surface). Implement `cycle` / `from_config` /
`to_config_dict` inline in `settings.py` without that helper.

---

## Screen architecture (`src/owa_tui/mail/screen.py`)

Use Textual. The screen replaces the curses `_loop` / `_State` / `_draw_*`
trio with reactive Textual widgets.

### Class hierarchy

```
MailScreen(Screen)
  ├── Header (Textual built-in or custom Label)
  ├── Horizontal / Vertical (depending on reading_pane)
  │   ├── MessageList(ListView)   — left / top pane
  │   └── ReaderPane(ScrollableContainer)  — right / bottom pane (hidden when 'off')
  └── Footer (status bar Label)
```

### MailScreen state (reactive attributes)

```python
class MailScreen(Screen):
    messages: reactive[list[dict]]     # full normalised list, unsorted
    selected: reactive[int]            # index into sorted list
    folder: reactive[str]              # folder display name
    search: reactive[str]              # active KQL search term
    settings: reactive[MailSettings]
    status: reactive[str]              # footer status line
    mode: reactive[str]                # 'list' | 'reader'
    _body_cache: dict[str, dict]       # message id → full normalised message
```

### Reading pane modes

Three modes controlled by `settings.reading_pane`:

| Mode | Layout | Behaviour |
|---|---|---|
| `right` | `Horizontal`: list left, pane right | `split_ratio`% width for list |
| `bottom` | `Vertical`: list top, pane bottom | `split_ratio`% height for list |
| `off` | list fills screen | pane widget hidden; Enter/`l` opens full-screen reader |

When switching modes (via menu cycle), re-compose the layout without
reloading messages.

### MessageList widget (`message_list.py`)

- Subclass `ListView` (Textual).
- Each item is a `ListItem` containing a `Static` that renders `list_row(msg,
  terminal_width, date_fmt=..., custom_fmt=...)`.
- Bold items where `is_read is False`.
- Reactive update: when `messages` or `settings` change, rebuild all list
  items.
- Scroll viewport to keep selected item visible (same clamping as curses
  `_draw_list`: scroll `top` up if `selected < top`, scroll down if
  `selected >= top + visible_rows`).
- Emits `MessageSelected(msg: dict)` message to `MailScreen` when selection
  changes.

### ReaderPane widget (`reader_pane.py`)

- Subclass `ScrollableContainer` (or `VerticalScroll`).
- Content: `Static` widget populated with `format_message_pretty(full_msg)`
  wrapped to pane width.
- `format_message_pretty` is imported from `owa_mail.format` (not on the
  documented stable API, but it is a stable module — check AGENTS.md for
  owa-tools; if not permitted, inline a plain-text fallback that renders
  subject/from/date header + `body` field with HTML stripped via stdlib
  `html.parser`).
- Shows scroll indicator `{top+1}-{end}/{total}` at top-right when content
  overflows (match curses behaviour).
- When `settings.reading_pane == 'off'`, this widget is not mounted in the
  normal layout; instead `MailScreen` pushes a `ReaderScreen` (see below).

### Full-screen reader (inline in `screen.py` or separate `reader_screen.py`)

When `reading_pane == 'off'` and the user opens a message (Enter / `l`),
push a new `Screen` (`ReaderScreen`) containing only the `ReaderPane`.
Back-navigation (`q` / `Escape` / left-arrow) pops back to `MailScreen`.

### Key bindings

Implement via `BINDINGS` on `MailScreen`:

| Key | Action | Notes |
|---|---|---|
| `j` / `down` | `move_down` | Move selection down 1 |
| `k` / `up` | `move_up` | Move selection up 1 |
| `d` | `page_down` | Move selection down half page |
| `u` | `page_up` | Move selection up half page |
| `g` | `go_top` | Jump to first message |
| `G` | `go_bottom` | Jump to last message |
| `enter` / `l` | `open_message` | Open reader |
| `h` / `left` | `close_reader` | Return focus to list (or pop ReaderScreen) |
| `tab` | `focus_pane` | Toggle focus between list and reading pane (only when pane visible) |
| `r` | `toggle_read` | Toggle is_read on selected message |
| `o` | `open_browser` | Open web_link in browser via `webbrowser.open` |
| `/` | `search` | Prompt for KQL search; re-fetch |
| `escape` | `open_menu` | Open settings overlay menu |
| `q` | `quit` | Quit screen |

### Overlay settings menu

Implement as a `ModalScreen` (Textual) mounted on Escape. Replaces the
curses `Menu` class. Menu structure mirrors the original:

**Top level:**
- Resume
- Settings >
- Help
- Quit

**Settings submenu:**
- Reading pane: `right` / `bottom` / `off` (cycle)
- Split ratio: `40` / `50` / `60` (cycle)
- Sort by: `date_desc` / `date_asc` / `sender` / `subject` / `unread_first` (cycle)
- Date format: `iso8601` / `ddmm` / `ddmm_hhmm` / `custom` (cycle)
- Edit custom date format (text input, validates with `validate_custom_format`)
- Reset to defaults
- Back

Each "cycle" action calls `cycle(settings, field)` and calls
`_persist_settings(settings)` immediately after (write to owa-mail config via
`owa_mail.config.save_config`).

---

## Data flow

### Initial load

```python
params = build_list_query(search='', limit=PAGE_SIZE)   # PAGE_SIZE = 50
path = folder_messages_path(folder)                      # from owa_mail.folders
data = api_get(api_base, f'{path}?{build_query(params)}', token)
messages = normalize_messages(data, keep_body=False)
# Sort on display via sort_messages(messages, settings.sort_by)
```

`owa_mail.folders` is **not** on the documented stable API surface. Use
`f"me/mailFolders/{folder}/messages"` as the path if `folder` is an ID, or
`"me/messages"` for the inbox default. Verify against owa_tools source.

### Body fetch (lazy, cached)

```python
path = f"me/messages/{msg_id}?$select={SHOW_SELECT}"
raw = api_get(api_base, path, token)
full_msg = normalize_message(raw)   # from owa_mail.messages
_body_cache[msg_id] = full_msg
```

`SHOW_SELECT` (from `owa_mail.messages`): `'Id,ConversationId,ReceivedDateTime,SentDateTime,Subject,From,ToRecipients,CcRecipients,BccRecipients,Body,BodyPreview,IsRead,HasAttachments,Importance,Flag,WebLink,ParentFolderId,InternetMessageHeaders'`

Cache on `MailScreen` keyed by message `id`; never re-fetch if cached.

### Mark read/unread (toggle)

```python
patch = {"IsRead": not msg["is_read"]}
api_request("PATCH", api_base, f"me/messages/{msg_id}", token, body=patch)
msg["is_read"] = not msg["is_read"]   # optimistic local update
```

### Search

Prompt for KQL search string (Textual `Input` widget in a `ModalScreen`).
Re-fetch with `build_list_query(search=query, limit=PAGE_SIZE)`. Reset
`selected = 0`, `_body_cache = {}`.

### Date-range filter

`build_list_query` supports `since` and `until` (ISO date strings). Expose
these as optional parameters on the search modal (date filter tab or
additional prompt fields). The filter translates to `$filter=ReceivedDateTime
ge {since}T00:00:00Z and ReceivedDateTime le {until}T23:59:59Z`.

---

## Settings persistence

```python
from owa_mail.config import save_config, load_config

def _persist_settings(settings: MailSettings) -> None:
    config = load_config()
    config.update(to_config_dict(settings))
    save_config(config)
```

Load settings on `MailScreen` construction via `from_config(load_config())`.

---

## Parity checklist

### Reader-pane modes (3 items)

- [ ] `reading_pane = 'right'` — list left, reader pane right; TAB switches focus; pane shows body of selected message; scroll indicator shown when content overflows
- [ ] `reading_pane = 'bottom'` — list top, reader pane bottom; same focus/scroll behaviour
- [ ] `reading_pane = 'off'` — pane widget absent; Enter/`l` pushes full-screen `ReaderScreen`; `q`/Escape/left pops back to list

### Sort orders (5 items)

- [ ] `date_desc` — newest first by `received`; messages with missing/None `received` sort last
- [ ] `date_asc` — oldest first by `received`; missing `received` still sorts last (not first)
- [ ] `sender` — A-Z by `from` casefold; missing/None `from` sorts last
- [ ] `subject` — A-Z by `subject` casefold; missing/None `subject` sorts last
- [ ] `unread_first` — unread (is_read=False or None) group before read; newest-first within each group; `_Desc` wrapper inverts ISO string comparison

### Date formats (4 items)

- [ ] `iso8601` — `YYYY-MM-DD` (10 chars); date column width = 10; unread marker at index 11
- [ ] `ddmm` — `DD.MM` (5 chars); date column width = 5; unread marker at index 6
- [ ] `ddmm_hhmm` — `DD.MM HH:MM` (11 chars); date column width = 11; unread marker at index 12
- [ ] `custom` — user strftime string; width = 10 (fixed budget); validates via `validate_custom_format`; falls back to `YYYY-MM-DD` if custom string is empty; returns `""` on strftime error; `%Z` on naive datetime → `""` → validate returns `False`

### Keyboard / navigation (12 items)

- [ ] `j`/down moves selection down; `k`/up moves up; viewport scrolls to keep selection visible
- [ ] `g` jumps to first message; `G` jumps to last message
- [ ] `d` half-page down; `u` half-page up (both clamped at list bounds)
- [ ] `Enter`/`l` opens message in reader (inline pane when visible, full screen when `off`)
- [ ] `h`/left returns focus to list from pane (or pops `ReaderScreen`)
- [ ] `tab` toggles focus between list and reading pane (no-op when pane is `off`)
- [ ] `r` toggles is_read; status bar updated; PATCH issued; pane_top reset if selection unchanged
- [ ] `o` opens `web_link` in browser via `webbrowser.open`; status bar shows "no web link" if absent
- [ ] `/` prompts for KQL search; re-fetches; resets selection + cache; `None`/empty cancels
- [ ] `Escape` opens settings overlay; second Escape or "Resume" closes it
- [ ] `q` quits (returns to previous screen or exits app)
- [ ] In full reader: `j`/`k` scroll line; Space/PgDn page down; PgUp/`k` page up; `g` top; `G` bottom

### Settings & persistence (5 items)

- [ ] Settings loaded from `owa_mail.config.load_config()` on screen construction
- [ ] Each cycle action immediately persists via `save_config`
- [ ] Reset-to-defaults restores all five fields to `MailSettings()` defaults and persists
- [ ] Custom date format validated with `validate_custom_format` before applying; invalid → status "invalid strftime format: …"
- [ ] `from_config` coerces `split_ratio` to int; invalid string or out-of-range value falls back to `50`

### Data / fetch (4 items)

- [ ] Initial fetch uses `build_list_query` + `api_get`; returns `None` on failure (screen shows error in status bar)
- [ ] Body fetch is lazy and cached by message `id`; second open does not re-fetch
- [ ] Date-range filter (`since`/`until`) passed to `build_list_query`; surfaced in search modal
- [ ] `normalize_messages(data, keep_body=False)` used for list; `normalize_message(raw)` for full body

### Error / edge cases (5 items)

- [ ] Empty message list renders placeholder "(no messages)" in list area
- [ ] Body fetch failure shows "failed to load message" in status bar; mode stays `list`
- [ ] Search failure (api returns None) shows "search failed" in status bar; existing messages preserved
- [ ] Search cancelled (empty/Escape prompt) leaves messages and search term unchanged
- [ ] Browser open with no `web_link` sets status "no web link" without crashing

---

## Pilot test cases (`src/tests/mail/test_screen.py`)

Use `pytest-textual-snapshot` / `textual.testing.Pilot` where available.
For unit-level coverage use a `FakeScreen` pattern analogous to the curses
version.

```python
# Helper fixtures
@pytest.fixture
def msgs():
    return [
        {"id": f"m{i}", "received": f"2026-05-{10+i:02d}T09:00:00Z",
         "from": f"user{i}@example.com", "subject": f"Subject {i}",
         "is_read": i % 2 == 0, "web_link": "https://example.test/m"}
        for i in range(6)
    ]
```

### Pilot tests

1. **test_screen_renders_message_list** — construct `MailScreen` with 6 messages and `reading_pane='off'`; assert list contains "Subject 0" … "Subject 5" in the rendered output.

2. **test_screen_reading_pane_right_shows_body** — `reading_pane='right'`; mock `_fetch_body`; assert reader pane widget is mounted and has CSS class matching right-layout.

3. **test_screen_reading_pane_bottom_shows_body** — same for `reading_pane='bottom'`.

4. **test_screen_reading_pane_off_no_pane_widget** — `reading_pane='off'`; assert no `ReaderPane` widget is mounted in the DOM.

5. **test_screen_j_moves_selection_down** — pilot presses `j` twice; assert `screen.selected == 2` (started at 0).

6. **test_screen_G_jumps_to_last** — pilot presses `G`; assert `screen.selected == 5` for 6-message list.

7. **test_screen_sort_date_asc** — set `settings.sort_by='date_asc'`; assert first list item is the oldest message.

8. **test_screen_sort_sender** — set `settings.sort_by='sender'`; assert list items are A-Z by `from` field casefold.

9. **test_screen_sort_unread_first** — set `settings.sort_by='unread_first'`; assert first 3 items are all unread messages.

10. **test_screen_sort_subject** — set `settings.sort_by='subject'`; assert list items are A-Z by `subject` casefold.

11. **test_screen_date_fmt_iso8601** — row text contains `"2026-05-10"` for the first message.

12. **test_screen_date_fmt_ddmm** — `date_format='ddmm'`; row text contains `"10.05"`.

13. **test_screen_date_fmt_ddmm_hhmm** — `date_format='ddmm_hhmm'`; row text contains `"10.05 09:00"`.

14. **test_screen_date_fmt_custom** — `date_format='custom'`, `date_custom='%Y/%m/%d'`; row text contains `"2026/05/10"`.

15. **test_screen_open_message_sets_reader_mode** — mock body fetch; pilot presses Enter; assert `screen.mode == 'reader'` and `ReaderScreen` is pushed (when `off`) or `ReaderPane` is populated (when pane visible).

16. **test_screen_toggle_read_flips_and_patches** — mock `api_request`; pilot presses `r`; assert message `is_read` flipped and PATCH was issued.

17. **test_screen_search_re_fetches** — mock `_fetch_list` returning 3 messages; pilot inputs search `"budget"` via `/`; assert `screen.search == "budget"` and `len(screen.messages) == 3`.

18. **test_screen_search_cancelled** — pilot presses `/` then Escape; assert `screen.search` unchanged.

19. **test_screen_escape_opens_menu** — pilot presses Escape; assert menu `ModalScreen` is on the screen stack.

20. **test_screen_menu_cycle_reading_pane** — open menu; navigate to "Reading pane" and cycle; assert `screen.settings.reading_pane != 'right'` (was default).

21. **test_screen_menu_reset_settings** — open menu → Settings → Reset; assert `screen.settings == MailSettings()`.

22. **test_screen_empty_list_shows_placeholder** — construct with 0 messages; assert "(no messages)" visible.

23. **test_screen_body_fetch_failure_stays_list** — mock body fetch returning `None`; press Enter; assert `screen.mode == 'list'` and "failed" in status.

24. **test_screen_browser_open** — mock `webbrowser.open`; pilot presses `o`; assert mock was called with the message's `web_link`.

25. **test_screen_browser_no_link** — all messages have `web_link=''`; pilot presses `o`; assert "no web link" in `screen.status`.

---

## Verify step

All checklist items above are ticked if:

1. The three reader-pane mode items pass (right / bottom / off rendering and
   focus model).
2. All five sort-order items pass (date_desc, date_asc, sender, subject,
   unread_first — including the `_Desc` inversion for unread_first).
3. All four date-format items pass (iso8601, ddmm, ddmm_hhmm, custom —
   including the column-width positions for unread markers and the validate
   guard on `%Z`).
4. The 12 keyboard/navigation items all have corresponding pilot test cases.
5. Settings persistence round-trips (to_config_dict → from_config) for all
   five fields.
6. The 5 data/fetch items are covered by mocked pilot tests.
7. The 5 error/edge-case items each have a dedicated pilot test.

Run before declaring done:

```bash
.venv/bin/python -m pytest src/tests/mail/ -q --cov=owa_tui.mail --cov=owa_tui.screens.mail --cov-fail-under=85
.venv/bin/ruff check src/owa_tui/mail/ src/owa_tui/screens/mail.py src/tests/mail/
```
