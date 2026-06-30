# Plan: GRAPH v1 — Textual rebuild of owa-graph TUI (flagship tui_kit adapter)

## Audit update — 2026-06-30

Gap audit ("find real gaps only"). Two behavioral gaps found:

- **`n` next-page now extends, not replaces.** `fetch_items` appends the new page
  to `state.items` and parks the cursor on the first new row, status `+N rows
  (T total)` (`graph/fetch.py`, cursor restore in `screens/graph.py
  _apply_fetch_result`). Regression tests: `test_fetch_next_page_appends_rows`,
  `test_fetch_fresh_replaces_rows`. The plan's "strip the dim sentinel row" step
  was moot — no such sentinel row exists in the shipped design.
- **DevOps continuation-token paging is unreachable — deferred, documented.**
  `fetch.py` can't read the `x-ms-continuationtoken` response header because the
  stable `owa_graph.api.api_request` returns parsed JSON only (no headers). First
  page of the `devops` audience works; 2nd+ page can't. Marked with a `ponytail:`
  comment naming the upgrade path (a headers-returning owa_graph call). OData/ARM
  body cursors are unaffected. Not fixed: would need an upstream library change.

## Review update — 2026-06-23

This is a shipped-behavior reference for the most complex v1 adapter. The live surface is `src/owa_tui/screens/graph.py` plus `src/owa_tui/graph/` helpers. Bookmarks and settings coercion have since been finished as part of the ponytail audit cleanup, so this plan should not be read as asking to remove that state.

Current hardening checklist:

- Keep per-audience token minting/refresh in `src/owa_tui/graph/auth.py`; do not collapse it into app-start auth.
- Keep row building, next-link handling, audience metadata, and settings serialization pure enough to unit test without a terminal.
- Preserve graceful degradation for AADSTS65002/AADSTS53003 and other scope/conditional-access errors; switching audience must not strand the UI.
- Keep the Escape/settings-overlay regression covered. `SettingsOverlay` now consumes the shared `MenuState` shape.
- Maintain fixture coverage for Graph default path, `/me`, continuation shapes, bookmarks, and the copy/open actions; live Graph smoke must remain explicitly gated.

Done criteria for future graph changes:

- `src/tests/graph/` covers auth/token expiry, fetch classification, navigation rows, settings/bookmarks, actions, and screen behavior.
- Fixture e2e covers audience/path navigation, settings overlay, drill/back history, search or path entry, and at least one degraded auth/fetch state.
- Full repo gates pass with the repository's chosen coverage threshold.

**Status:** ✅ shipped (commit b12d1cd); auth reworked to per-call token minting in fcfa2bc.
Implemented as `src/owa_tui/screens/graph.py` + `src/owa_tui/graph/` (auth/fetch/nav/state).
Covered by `src/tests/graph/` (Pilot) and `e2e/actions.test.ts` (tui-test, fixture-mode).
Note: the e2e pass found and fixed a real regression — Escape→menu crashed because
`SettingsOverlay` was called with the old `MenuState` signature. Kept as the reference.
**Phase:** B (source files read; curses source will be deleted in a later phase)
**Parity source:** `owa-tools/src/owa_graph/tui.py`, `tui_nav.py`, `tui_settings.py`, `tui_menu.py`; `src/tests/graph/test_tui_loop.py`, `test_tui_nav.py`, `test_tui_actions.py`, `test_tui_auth.py`; `.plans/owa-graph-explorer-tui.md`
**Target file:** `owa-tui/src/owa_tui/graph/screen.py`
**Sibling plans:** `10-v1-cal.md` (CAL), `11-v1-mail.md` (MAIL)

---

## Context

owa-graph TUI is the **flagship and most complex** adapter on `owa_core/tui_kit/`. It is
more complex than owa-cal and owa-mail because it must navigate **17 FOCI audiences**
across 4 explorability tiers, with per-audience exp-aware token caching, 3 pagination
continuation shapes, graceful AADSTS65002/AADSTS53003 degradation, and a breadcrumb
history that restores without network round-trips.

The curses implementation lives in `owa_graph/tui.py` (frontend + token cache),
`owa_graph/tui_nav.py` (navigation engine — curses-free, correctness-critical),
and `owa_graph/tui_settings.py` (settings dataclass + bookmark helpers). These are
deleted after this plan's target is shipped; extract behavior now.

The Textual rebuild does NOT re-implement tui_kit scaffolding (the kit's
`BrowserSpec`/`BrowserState` loop, list/detail layout, menu, settings cycle, key
handling). It provides **graph-specific callbacks** fed to `tui_kit.app.BrowserSpec`.

---

## Import contract (what owa-tui/graph may import)

**Do import** from owa_graph (the data/logic package, not its curses layer):
- `owa_graph.api.api_request` — NOT used inside loop (curses-unsafe); used only for
  pre-loop validation if needed
- `owa_graph.tui_nav._fetch_page`, `build_rows`, `next_path`, `FetchResult`, `Row`,
  `classify_response`, `build_prefix_index`, `MAX_ROWS`, `MAX_KEYS` — the pure nav
  engine; these are the graph-specific computations `tui_kit` does not absorb
- `owa_graph.tui_nav._tui_get` — curses-safe HTTP wrapper (never raises/prints)
- `owa_graph.auth.AUDIENCE_API_BASE`, `AUDIENCE_DESC`, `TOOL_NAME`, `resolve_api_base`
- `owa_graph.tui_settings.Settings`, `DEFAULTS`, `READING_PANE_VALUES`,
  `SPLIT_RATIO_VALUES`, `TOGGLE_VALUES`, `_FIELD_TO_KEY`, `from_config`,
  `to_config_dict`, `parse_bookmarks`, `dump_bookmarks`
- `owa_graph.format.format_pretty` — graph-gated (Tier A graph audience only)
- `owa_graph.emit.render_curl`
- `owa_core.auth.get_token_for_config`
- `owa_core.errors.OwaError` and subtypes
- `owa_core import jwt as jwt_mod` — `jwt_mod.scopes_in_token`, `jwt_mod.tenant_id`
- `owa_core.secrets.redact`
- `owa_core.tui_kit.app.BrowserSpec`, `BrowserState`
- `owa_core.tui_kit.layout.truncate_ellipsis`, `wrap_body`
- `owa_core.tui_kit.screen.silence_os_fds` — used by `o` action (browser launch)

**Do NOT import** from `owa_graph.tui` (the curses module being deleted). Re-implement
`TokenInfo`, `GraphState`, `_ensure_token`, `_apply_token`, `_exp_epoch_from_broker`,
`render_row`, `render_detail`, `fetch_items`, `on_drill`, `on_back`, `on_search`,
`on_refresh`, `_action_*`, `build_spec`, `run` in `owa-tui`.

**Do NOT import** `owa_graph.tui_menu` (mail-coupled title/fields). Re-implement
`GraphMenu` in `owa-tui/src/owa_tui/graph/menu.py`.

---

## Settings dataclass (`src/owa_tui/graph/settings.py`)

Reproduce `owa_graph.tui_settings.Settings` in `src/owa_tui/graph/settings.py`.
Import helpers from owa_graph.tui_settings rather than re-implementing them.

Fields:

| Field              | Type  | Default   | Allowed values                          |
|--------------------|-------|-----------|-----------------------------------------|
| `reading_pane`     | str   | `'right'` | `'right'`, `'bottom'`, `'off'`          |
| `split_ratio`      | int   | `50`      | `40`, `50`, `60`                        |
| `pretty_json`      | str   | `'on'`    | `'on'`, `'off'`                         |
| `scope_warnings`   | str   | `'on'`    | `'on'`, `'off'`                         |
| `default_audience` | str   | `'graph'` | any key in `AUDIENCE_API_BASE`          |
| `default_path`     | str   | `''`      | free text                               |
| `bookmarks`        | str   | `'[]'`    | free text (JSON-encoded list)           |

Config key mapping:

```python
_FIELD_TO_KEY = {
    'reading_pane':     'graph_tui_reading_pane',
    'split_ratio':      'graph_tui_split_ratio',
    'pretty_json':      'graph_tui_pretty_json',
    'scope_warnings':   'graph_tui_scope_warnings',
    'default_audience': 'graph_tui_default_audience',
    'default_path':     'graph_tui_default_path',
    'bookmarks':        'graph_tui_bookmarks',
}
```

`split_ratio` coerced to `int` on load. `bookmarks` parsed/serialized via
`parse_bookmarks`/`dump_bookmarks` (import from `owa_graph.tui_settings`).
`from_config`/`to_config_dict` delegate to `tui_kit.settings` helpers exactly as
the curses implementation does.

---

## Audience model and tiers

17 FOCI audiences keyed in `AUDIENCE_API_BASE` (key-set-equal to owa-piggy 0.16.2
`KNOWN_AUDIENCES`). The tiers drive per-audience UX and seed paths:

| Tier | Description                        | Audiences                                              |
|------|------------------------------------|--------------------------------------------------------|
| A    | Self-describing OData/discovery    | `graph`, `outlook`, `outlook365`, `azure`, `powerbi`   |
| B    | REST collections (response-driven) | `flow`, `manage`, `substrate`, `devops`                |
| C    | Opaque internal Teams APIs         | `teams`, `ic3`, `csa`, `presence`, `uis`               |
| D    | Data-plane, not browseable         | `keyvault`, `storage`, `sql`                           |

The complete 17-name set: `graph`, `outlook`, `outlook365`, `azure`, `powerbi`,
`flow`, `manage`, `substrate`, `devops`, `teams`, `ic3`, `csa`, `presence`, `uis`,
`keyvault`, `storage`, `sql`.

Tier-D audiences (`keyvault`, `storage`, `sql`) receive a persistent footer note:
`'Tier D: raw target — not a browse surface'`.

`format_pretty` is gated **strictly** to `audience == 'graph'` (never widen to all
of Tier A — ARM/devops mislabelling is the exact defect this guard prevents).

---

## Token cache and auth layer (`src/owa_tui/graph/auth.py`)

Port these symbols verbatim from `owa_graph.tui` (the curses module being deleted).
They are pure-data / non-curses and belong in owa-tui as graph-specific logic.

### `TokenInfo` (frozen dataclass)

```python
@dataclass(frozen=True)
class TokenInfo:
    token: str
    scopes: frozenset
    api_base: str
    exp_epoch: int  # always a concrete int, never None
```

### Constants

```python
_DEFAULT_TTL = 300   # seconds; guards against both fields absent from broker
_EXP_SKEW = 60       # seconds; re-mint this early to avoid racing the boundary
```

### `_exp_epoch_from_broker(broker, now) -> int`

Coerce broker expiry to a concrete int: prefer `expires_at`, then `now + expires_in`,
then `now + _DEFAULT_TTL`. Never returns `None` — guards `time.time() >= None - 60`
TypeError in the cache-hit check.

### `_apply_token(state, audience, info)`

Atomically point the session at a token's context:
```
state.audience = audience
state.token = info.token
state.api_base = info.api_base
state.scopes = info.scopes
state.exp_epoch = info.exp_epoch
```

### `_ensure_token(audience, state) -> TokenInfo | None`

Cache hit: `time.time() < info.exp_epoch - _EXP_SKEW` → call `_apply_token` + return
cached `TokenInfo`. No AAD round-trip.

Cache miss: set `state.status = f'minting token for {audience}…'`, then call
`get_token_for_config(state.config, tool_name=TOOL_NAME, audience=audience, debug=False)`
inside `try/except OwaError`. On failure: set `state.status` to `redact(error.message)`,
evict `state.token_cache[audience]`, return `None`.

On success: populate `TokenInfo`:
- `token = broker.access_token`
- `scopes = frozenset(jwt_mod.scopes_in_token(broker.access_token))` — from `scp`
  claim, NOT from the broker's requested `.default` scope string
- `api_base = resolve_api_base(audience)`
- `exp_epoch = _exp_epoch_from_broker(broker, now)`

Store in `state.token_cache[audience]`, call `_apply_token`, return `TokenInfo`.

**Curses-safe invariants (must hold in Textual too):**
- Never calls `api_mod.api_request`, `auth_mod.setup_auth`, `_refresh_via_owa_piggy`
- Never prints to stdout/stderr
- On failure: sets `state.status`, evicts cache entry, returns `None` — never raises
- owa-piggy invoked via `get_token_for_config` (carries `expires_at`/`expires_in`);
  `setup_auth` discards those fields and must not be used

The "minting…" status is set before the blocking subprocess. In the Textual rebuild
the worker model removes the old curses deviation ("status drawn after fetch_items
returns") — Textual workers post progress notifications so the "minting…" frame
actually paints before the subprocess blocks.

---

## `GraphState` (`src/owa_tui/graph/screen.py`)

Extends `tui_kit.BrowserState`. The kit owns: `selected`, `top`, `status`,
`detail_lines`, `items`, `menu_open`, `dirty`, `running`. Graph session fields:

```python
class GraphState(BrowserState):
    def __init__(self, config, *, audience='graph', path='', settings=None,
                 menu=None, debug=False):
        super().__init__(settings=settings, menu=menu, title=audience)
        self.config = config
        self.debug = debug
        self.audience = audience
        self.api_base = ''
        self.token = ''
        self.scopes: frozenset = frozenset()
        self.exp_epoch = 0
        self.token_cache: dict[str, TokenInfo] = {}
        self.path = path
        self.query = ''
        self.response = None
        self.kind = ''
        self.next_link = None
        self.history: list[tuple] = []   # 7-tuples, see on_drill
        self.overlay = None              # None | 'audience' | 'bookmarks' | 'help' | 'debug'
        self.stderr_buf = io.StringIO()  # lifecycle: owned by run(), redirected in/out
```

---

## Navigation / breadcrumb logic to port from `tui_nav.py`

**PORT THESE FRAMEWORK-AGNOSTICALLY** — these are already pure Python (no curses):

### `next_path(current_path, target) -> str`

Three id-shapes, in priority order:
1. Absolute URL (`https://…`) → navigate by the full URL verbatim (used for
   `@odata.nextLink`, `@odata.id` pointing to a different host segment, ARM ids)
2. Absolute path (`/subscriptions/…`) → **replace** `current_path` (ARM `id` fields
   like `/subscriptions/{s}/resourceGroups/{g}` — do NOT append)
3. Relative segment (GUID, `messages`, bare segment) → append to `current_path`

```python
def next_path(current_path, target):
    if not isinstance(target, str) or not target:
        return current_path
    if target.startswith('https://') or target.startswith('http://'):
        return target
    if target.startswith('/'):
        return target
    cur = (current_path or '').strip('/')
    return f'{cur}/{target}' if cur else target
```

### Pagination continuation shapes (in `_fetch_page`/`_next_cursor`)

Three disjoint shapes by audience family:

| Shape | Audiences                                                    | Cursor location                                      |
|-------|--------------------------------------------------------------|------------------------------------------------------|
| OData | `graph`, `outlook`, `outlook365`, `powerbi`, `flow`, `manage`, `substrate` | `payload['@odata.nextLink']`            |
| ARM   | `azure`, `keyvault`, `storage`, `sql`                        | `payload['nextLink']` (bare, top-level)              |
| DevOps| `devops`                                                     | `x-ms-continuationtoken` response header, re-appended as `?continuationToken=` |

DevOps header lookup **must be case-insensitive** (`_header_get(headers, 'x-ms-continuationtoken')`
iterates `headers.items()` lowercasing keys) because server may send
`X-MS-ContinuationToken` with mixed casing.

Do NOT use `api_mod.paginate` (eager, `@odata.nextLink`-only — silently truncates ARM
and devops responses).

### History frame shape

Each `on_drill` push stores a 7-tuple:
```
(audience, path, query, selected, top, rows, next_link)
```
`on_back` restores all seven with **no network call** — `state.dirty` remains `False`
so `fetch_items` is not re-triggered. `r` (refresh) clears `next_link`, resets
`top`/`selected`, and sets `dirty=True` — discards cached rows for the current level
only, does not touch history.

### `classify_response(result: FetchResult) -> (kind, payload)`

`json.loads(result.body)` ourselves (never use `api_request`/`http` decode):
- `JSONDecodeError` → `('opaque', body_bytes)` — the ONLY way `opaque` is reachable
- `dict` with `isinstance(payload.get('value'), list)` → `('collection', payload)`
- `dict` (no `value` list) → `('object', payload)`
- `list` → `('collection', {'value': payload})`
- anything else → `('scalar', payload)`

Empty body → `('object', {})`.

### `build_rows(kind, payload, *, host=None) -> list[Row]`

- `opaque` → single non-drillable `Row('(binary / non-JSON response — y to yank URL)', None, False)`
- `scalar` → single non-drillable `Row(_preview(payload, limit=200), None, False)`
- `collection` (empty `value` list) → single `Row('(no items)', None, False)`
- `collection` (non-empty) → one `Row` per item up to `MAX_ROWS=500`; if truncated,
  append `Row(f'… {extra} more (n to page)', None, False, dim=True)`
- `object` → one `Row` per key up to `MAX_KEYS=100`; navigation-link rows drillable;
  if truncated, append `Row(f'… {extra} more keys', None, False, dim=True)`

Link-field deny list (never drillable): `@odata.context`, `@odata.editlink`,
`editlink`, `@odata.type`, `type`, `metadata`, `etag`, `@odata.etag`, `@odata.count`,
`count`, `@odata.id`.

Navigation-link fields (drillable if same-host or relative):
- keys ending in `@odata.navigationLink`
- keys ending in `@odata.associationLink`
- bare `@odata.nextLink`
- bare `nextLink`

Cross-host absolute URLs (CDN/photo/portal) → detail-pane only, not drillable.

Human-readable label fields (best-first): `displayName`, `name`, `subject`, `title`,
`givenName`, `userPrincipalName`, `mail`, `id`.

Drill target preference: `@odata.id` then `id`. Non-dict collection items → not drillable.

---

## Fetch layer (`src/owa_tui/graph/fetch.py`)

Import `_tui_get`, `_fetch_page`, `classify_response`, `build_rows`, `next_path`,
`FetchResult`, `Row` from `owa_graph.tui_nav` (the navigation engine is pure Python
and is NOT deleted — only the curses frontend is).

### `fetch_items(state: GraphState) -> None`

Called by the Textual worker. Always mutates `state.items` and `state.status` — never
raises or prints.

```
1. info = _ensure_token(state.audience, state)
   → if None: state.items = []; return (status already set by _ensure_token)
2. Build URL: api_base.rstrip('/') + '/' + state.path.strip('/')
   Special case: if path is already an absolute URL, use it verbatim
3. kind, payload, cursor = _fetch_page(state.audience, url, state.token, debug=state.debug)
4. If kind in _FAILURE_KINDS: state.items = []; state.status = str(payload); return
5. state.response = payload; state.kind = kind; state.next_link = cursor
6. Resolve host from URL (urlsplit(url).netloc, catch Exception → None)
7. state.items = build_rows(kind, payload, host=host)
8. state.selected = 0; state.top = 0
9. state.title = f'{state.audience}:{state.path or "/"}'
10. state.status = ''
11. Catch bare Exception → state.status = f'internal error: {exc!r}'
```

`_FAILURE_KINDS = frozenset({'auth', 'scope', 'notfound', 'ratelimit', 'error'})`

This function is called from a Textual `@work` worker, so it must be `async def` and
use `asyncio.to_thread` to wrap the synchronous `_fetch_page` call.

The `@work` async-worker model removes the old curses deviation where "minting token
for `<audience>`…" status was set but never painted before the blocking subprocess —
the Textual worker posts `state.status` to the reactive and the framework schedules
a redraw before the blocking call returns.

---

## Widgets (`src/owa_tui/graph/screen.py`)

### `ExplorerList`

Subclass `textual.widgets.ListView`. Each row rendered by `render_row(item, width)`:

```python
def render_row(item: Row, width: int) -> str:
    label = item.label if not item.dim else f'  {item.label}'
    return truncate_ellipsis(label, max(width, 1))
```

Dim sentinel rows (`item.dim=True`) receive a leading 2-space indent to visually
recede from real content.

### `DetailPane`

`ScrollableContainer` (Textual). Lines produced by `render_detail(item, width, *, state)`.

### `render_detail(item, width, *, state) -> list[str]`

Branches on `state.kind` and `state.audience`:

| `state.kind`            | `state.audience`     | Detail content                                          |
|-------------------------|---------------------|---------------------------------------------------------|
| `opaque`                | any                 | hex dump first 4 KB (`binascii`); header line showing total bytes |
| `scalar`                | any                 | `str(payload)`                                          |
| `collection` or `object`| `'graph'`           | `_format_pretty(payload)` — Textual `Text` / split on `\n` |
| `collection` or `object`| any other           | `json.dumps(payload, indent=2, ensure_ascii=False)`     |
| anything else           | any                 | `json.dumps(state.response, indent=2, ensure_ascii=False)` |

Tier-D audiences always append an empty line then
`'Tier D: raw target — not a browse surface'`.

`item is None` → return `[]`.

Each line fed through `wrap_body(ln, width) or ['']`.

`_DETAIL_MAXBYTES = 4096` (hex preview ceiling).

Header (`GraphScreen`) shows `f'{audience} · {profile} · {tenant}'` where
`tenant = jwt_mod.tenant_id(state.token)` (fallback `'myorganization'`) and
`profile` is fixed for the session.

---

## `GraphScreen` (`screen.py`)

```python
class GraphScreen(App):
    TITLE = 'owa-graph'
    CSS_PATH = 'graph.tcss'

    def __init__(
        self,
        config: dict,
        *,
        start_audience: str = 'graph',
        start_path: str | None = None,
        debug: bool = False,
    ) -> None:
```

`start_path` overrides the seed path from `audience_seeds.json`.

`run()` lifecycle (mirrors curses `run()` with Textual idioms):

1. Load settings via `from_config(config)`
2. Resolve `seed = start_path or _seed_path(start_audience, settings)`
3. Build `GraphState(config, audience=start_audience, path=seed, settings=settings, debug=debug)`
4. Build menu + spec
5. Enter Textual event loop (`App.run()`)
6. **The initial mint + first fetch happen inside the first worker call** (on `on_mount`),
   not before entering the event loop — mirrors the curses "first iteration" model.
   A failed seed (401, AADSTS65002/53003) lands as `state.status` + empty list with
   the audience switcher (`a`) reachable — **never a clean exit** (graceful degradation
   is the whole point; this inverts cal/mail, which exit cleanly on auth failure).

Header `Label`: `f'{state.audience} · {profile} · {tenant}'`.

Status bar: `state.status` (reactive, updated by worker posts).

---

## Key bindings

| Key(s)              | Action                                                      |
|---------------------|-------------------------------------------------------------|
| `j` / `↓`           | move selection down                                         |
| `k` / `↑`           | move selection up                                           |
| `g`                 | jump to first item                                          |
| `G`                 | jump to last item                                           |
| `u`                 | half-page up                                                |
| `d`                 | half-page down                                              |
| `PgUp`              | page up                                                     |
| `PgDn` / `Space`    | page down                                                   |
| `Enter` / `→` / `l` | drill into selected item (on_drill)                         |
| `h` / `←` / `Bksp` | back (on_back — no network, restores 7-tuple history frame) |
| `r`                 | re-fetch current path (on_refresh — clears next_link)       |
| `a`                 | audience switch (round-robin cycle; commit even on failure) |
| `n`                 | next page via `state.next_link`                             |
| `/`                 | jump to path (prompt; graph → prefix-index completion; non-graph → free-text) |
| `e`                 | edit query params (OData: `$select/$top/$filter/$expand`; non-OData: raw `?k=v`) |
| `c`                 | curl emit: `render_curl('GET', url, state.token, include_token=False)` |
| `y`                 | yank URL to clipboard (pbcopy/xclip/xsel; `capture_output=True` always) |
| `o`                 | open in browser: graph→Graph Explorer URL; other audiences→status + no-op |
| `m`                 | add `(audience, path)` bookmark (dedup by audience+path)    |
| `D`                 | debug overlay: `state.stderr_buf` contents; scrollable; toggle |
| `Esc`               | toggle menu                                                 |
| `q`                 | quit                                                        |
| `SIGWINCH` / resize | `curses.resizeterm` equivalent — Textual handles natively   |

### Action detail

**`a` — audience switch**

Current implementation is round-robin cycle (interim — full overlay deferred pending
kit enhancement to pass `stdscr` to action callbacks). Key behavior:
- Commit the new audience to `state.audience` **even if the subsequent fetch fails** —
  so `r` can retry the new audience. Never silently revert.
- Clear `state.next_link`, reset `selected`/`top`, set `dirty=True`.
- In Textual: open a `Select` overlay from the widget layer (the `@work` model makes
  this straightforward; pass a callback).

**`/` — jump to path**

Prompt for path. Graph audience → prefix-index completion (`build_prefix_index`).
Non-graph → free-text, tolerate `None` prefix-index (never crash). Failed jump (404 /
unknown) → set `state.status`, do NOT push history or replace `rows` (stay on prior
valid view). `on_search` only sets `path`+`dirty`; it does NOT pre-emptively clear
`state.items`.

**`e` — edit query**

OData audiences → prompt for `$select/$top/$filter/$expand` params. Non-OData/Tier-D
→ raw `?k=v` only. Persisted into `state.query` + the history frame.

**`n` — next page**

Fetch `state.next_link`. If `None`: `state.status = 'no next page'`, no-op. On
success: remove trailing `dim` sentinel row if present, extend `state.items` with
new rows, update `state.next_link`. Status: `f'+{len(new_rows)} rows'`.

**`c` — curl emit**

```python
url = (state.path if _HTTP_RE.match(state.path)
       else f'{state.api_base.rstrip("/")}/{state.path.strip("/")}')
cmd = render_curl('GET', url, state.token, include_token=False)
state.stderr_buf.write(f'curl:\n{cmd}\n')
state.status = truncate_ellipsis(cmd.replace('\n', ' '), 120)
```
`include_token=False` emits the `$OWA_TOKEN` placeholder — never pass `True`.

**`y` — yank URL**

Same URL construction as `c`. Try `pbcopy`, then `xclip -selection clipboard`,
then `xsel`. `capture_output=True` **always** — keeps `xclip`/`xsel` diagnostics
("Can't open display") off inherited fd 2, which would corrupt the curses frame (or
in Textual, land on the terminal). Fallback when all clipboard tools missing:
`state.status = f'url: {url}'`.

**`o` — open in browser**

- `graph` audience: build `https://developer.microsoft.com/en-us/graph/graph-explorer?request={path}&method=GET&version=v1.0`, then call `webbrowser.open` inside `silence_os_fds()` context (silences inherited OS fds 1/2 around the launcher subprocess; `sys.stderr` redirection alone can't reach an inherited fd).
- Any other audience: `state.status = 'no browser target (graph audience only)'`; no `webbrowser.open` (a raw API URL returns JSON/401, useless; also no-ops cleanly headless/over-SSH).

**`m` — bookmark**

```python
marks = parse_bookmarks(state.settings.bookmarks)
entry = {'audience': state.audience, 'path': state.path or '', 'label': ''}
if not any(m['audience'] == entry['audience'] and m['path'] == entry['path'] for m in marks):
    marks.append(entry)
state.settings = dataclasses.replace(state.settings, bookmarks=dump_bookmarks(marks))
state.status = f'bookmarked {state.audience}:{state.path}'
```
Dedup by `(audience, path)`. Never persist bodies.

**`D` — debug overlay**

Toggle `state.overlay` between `'debug'` and `None`. Render `state.stderr_buf.getvalue().splitlines()` in a scrollable overlay (`j`/`k`/`u`/`d` scroll, `q`/`Esc` close). If buffer non-empty on first open, also surface last 400 chars in `state.status` (visible without the overlay).

---

## `GraphMenu` (`src/owa_tui/graph/menu.py`)

Re-implement (do NOT import from `owa_graph.tui_menu` or `owa_mail.tui_menu`).

```python
_TITLE_LINES = ['owa-graph', '─' * 16]
_TOP_ITEMS = ['Resume', 'Audiences', 'Settings', 'Bookmarks', 'Help', 'Quit']
```

Settings fields: all 7 from `tui_settings` (`reading_pane`, `split_ratio`,
`pretty_json`, `scope_warnings`, `default_audience`, `default_path`, `bookmarks`).

Menu dispatch:
- `'open_audiences'` → `state.overlay = 'audience'`
- `'open_bookmarks'` → `state.overlay = 'bookmarks'`
- `'open_help'` → `state.overlay = 'help'`
- `'Quit'` → return `True` (quit signal)

Copy `_pad`/`_truncate` helpers verbatim. Port the generic nav state machine
(`move/select/back/open_settings`) from the curses implementation.

In Textual: use `tui_kit.menu` with graph title + items list (the menu is
generic in the kit; `GraphMenu` provides only the graph-specific metadata).

---

## `HELP_LINES` constant

Multi-line, grouped:

```
Navigation
  j/k/↑/↓  move         g/G  first/last    u/d  half-page
  PgUp/PgDn/Space  page  Enter/→/l  drill  h/←/Bksp  back

Audience & path
  a  switch audience (17 FOCI audiences across 4 tiers)
  /  jump to path (graph: completion; others: free-text)
  e  edit query params  n  next page  r  re-fetch

Clipboard & bookmarks
  y  yank URL (pbcopy/xclip/xsel)  c  curl command
  o  open Graph Explorer (graph audience only)
  m  bookmark current path

General
  Esc  menu   D  debug overlay   q  quit
```

`FOOTER` constant (single line for the status bar):
```
j/k move · enter drill · h/← back · / jump · r refresh · a aud · n page · c curl · y yank · o browser · m bm · D debug · q quit
```

---

## `run()` lifecycle

```python
def run(config, *, start_audience='graph', start_path=None, debug=False):
```

Deliberately omits `access_token`/`api_base` (contrast cal/mail `run()` which takes a
pre-minted token). Graph re-mints per audience inside the worker.

The initial mint + first fetch happen **inside the first `on_mount` worker call**,
not before entering the event loop. A failed seed (graph `/me` 401, AADSTS65002/53003)
lands as `state.status` + empty list — the audience switcher (`a`) stays reachable.

**stderr redirect** — owned by `run()`, not the screen:

```python
old = sys.stderr
sys.stderr = state.stderr_buf  # io.StringIO
try:
    GraphScreen(config, ...).run()
finally:
    sys.stderr = old
```

In the Textual rebuild: this can be simplified because Textual captures stderr
internally, but preserve the `state.stderr_buf` for the `D` overlay (store stderr
captures there via a logging handler or explicit writes from `_ensure_token`).

Non-`OwaError` exceptions inside the worker are caught, written to `state.stderr_buf`,
and surfaced as `state.status = f'internal error: {exc!r}'` — the app stays alive.
`KeyboardInterrupt`/`SystemExit` propagate normally.

---

## Seed path resolution (`_seed_path`)

Priority:
1. `start_path` argument (caller override) — applied before `_seed_path` is called
2. `settings.default_path` if `audience == settings.default_audience`
3. First entry in `owa_graph/data/audience_seeds.json` for the audience
4. Empty string (bare API base)

---

## Parity checklist

Total: 72 discrete behaviors mapped from the curses source.

### Auth / token cache (6)
- [x] Cache hit does not trigger a re-mint (no AAD round-trip)
- [x] Cache miss mints via `get_token_for_config` (not `setup_auth`)
- [x] Per-audience keying — cached `graph` token does not satisfy `azure` request
- [x] `expires_at=None` + `expires_in=None` → uses `_DEFAULT_TTL`, never raises `TypeError`
- [x] Expiry (`exp_epoch < now + _EXP_SKEW`) forces re-mint
- [x] Failure → returns `None` + sets `state.status` + evicts cache (so `r` retries)

### Audience model (6)
- [x] All 17 audiences present in `AUDIENCE_API_BASE` (key-set parity with owa-piggy 0.16.2)
- [x] Tier A (5): `graph`, `outlook`, `outlook365`, `azure`, `powerbi`
- [x] Tier B (4): `flow`, `manage`, `substrate`, `devops`
- [x] Tier C (5): `teams`, `ic3`, `csa`, `presence`, `uis`
- [x] Tier D (3): `keyvault`, `storage`, `sql`
- [x] Tier-D footer note appended in `render_detail` for `keyvault`, `storage`, `sql`

### Graceful degradation (4)
- [x] AADSTS65002 error → `state.status` set, `state.items = []`, loop alive (never exit)
- [x] AADSTS53003 error → same
- [x] Seed fetch failure → status + empty list, `a` switcher reachable
- [x] Any bare `Exception` in worker → caught, written to `stderr_buf`, surfaces as status

### Pagination — 3 continuation shapes (9)
- [x] OData shape: `payload['@odata.nextLink']` for graph/outlook/outlook365/powerbi/flow/manage/substrate
- [x] ARM shape: `payload['nextLink']` (bare) for azure/keyvault/storage/sql
- [x] DevOps shape: `x-ms-continuationtoken` response header, re-appended as `?continuationToken=`
- [x] DevOps header lookup is case-insensitive (`X-MS-ContinuationToken` matches)
- [x] `_fetch_page` always reads both `body` and `headers` from `FetchResult`
- [x] `api_mod.paginate` is never used (wrong shape + eager)
- [x] `n` extends `state.items` (removes trailing `dim` sentinel first), updates `next_link`
- [x] `n` with `state.next_link = None` → `state.status = 'no next page'`, no-op
- [x] OData `@odata.nextLink` is in the deny list for drill targets (it's a cursor, not a nav link)

### Classification (6)
- [x] Dict with `value: list` → `'collection'`
- [x] Dict without `value: list` → `'object'`
- [x] Bare JSON list → `'collection'` (wrapped as `{'value': payload}`)
- [x] Bare scalar (string, int, etc.) → `'scalar'`
- [x] Non-JSON bytes → `'opaque'` (only reachable via `raw=True` + `json.loads` ourselves)
- [x] Empty body → `('object', {})`

### Row building (8)
- [x] `opaque` → single non-drillable sentinel
- [x] `scalar` → single non-drillable row with `_preview`
- [x] Empty collection → `Row('(no items)', None, False)`
- [x] Collection capped at `MAX_ROWS=500`; `dim` sentinel with count appended when truncated
- [x] Object capped at `MAX_KEYS=100`; `dim` sentinel appended when truncated
- [x] Link-field deny list filters `@odata.context` etc.
- [x] Navigation-link fields (`*@odata.navigationLink`, `*@odata.associationLink`, `nextLink`) drillable when same-host or relative; cross-host → detail only
- [x] `dim=True` rows get leading 2-space indent in `render_row`

### Path navigation (3)
- [x] Absolute URL target → navigate verbatim
- [x] Absolute path target (`/subscriptions/…`) → **replace** `current_path` (not append)
- [x] Relative segment → append to `current_path`

### Breadcrumb history (5)
- [x] `on_drill` pushes 7-tuple: `(audience, path, query, selected, top, rows, next_link)`
- [x] `on_back` restores all seven without a network call (`dirty` stays `False`)
- [x] `on_back` returns `False` when history empty (no crash, no-op)
- [x] `r` (refresh) clears `next_link`, resets `selected`/`top`, sets `dirty=True`; does not touch history
- [x] Non-drillable item → `on_drill` is a no-op (no history push)

### `render_detail` gating (5)
- [x] `graph` + `collection`/`object` → `format_pretty` called
- [x] `azure` + `collection`/`object` → `format_pretty` NOT called (plain `json.dumps`)
- [x] `devops` + `collection`/`object` → `format_pretty` NOT called
- [x] `opaque` → hex dump with byte count header; `format_pretty` never called
- [x] `scalar` → `str(payload)` only

### Action keys — all 8 (8)
- [x] **`o`** — graph audience → Graph Explorer URL; other audiences → status + no-op (never `webbrowser.open` a raw API URL)
- [x] **`o`** — uses `silence_os_fds()` around `webbrowser.open` (guards inherited fd 2)
- [x] **`y`** — `capture_output=True` always (guards xclip/xsel diagnostics off fd 2)
- [x] **`y`** — fallback when no clipboard tool found: `state.status = f'url: {url}'`
- [x] **`c`** — `include_token=False` (emits `$OWA_TOKEN` placeholder); curl text in `stderr_buf`
- [x] **`a`** — commits new audience even on failed subsequent fetch (so `r` retries)
- [x] **`m`** — deduplicates by `(audience, path)`; persists only `(audience, path, label)` (never bodies)
- [x] **`D`** — toggles overlay; shows last 400 chars of `stderr_buf` in status; scrollable overlay

### Settings (5)
- [x] All 7 fields cycle (`reading_pane`, `split_ratio`, `pretty_json`, `scope_warnings`, `default_audience`, `default_path`, `bookmarks`)
- [x] `split_ratio` coerced to `int` on load
- [x] `from_config` → `to_config_dict` round-trip preserves all values
- [x] Settings changes affecting layout trigger re-layout immediately (via Textual reactives)
- [x] Bookmarks: JSON-encoded list; only `(audience, path, label)` persisted; parse/dump via `parse_bookmarks`/`dump_bookmarks`

### `on_search` / `/` jump (3)
- [x] Blank query → no-op (path unchanged, `dirty` unchanged)
- [x] Non-blank → sets `state.path` (stripped), clears `query`/`next_link`, sets `dirty=True`
- [x] `on_search` does NOT pre-emptively clear `state.items` — if fetch fails, prior items remain (graceful degrade)

### `run()` lifecycle (4)
- [x] Deliberately omits `access_token`/`api_base` (graph re-mints per audience)
- [x] Initial mint + first fetch happen inside first worker call (after event loop enters)
- [x] `stderr` redirect owned by `run()` (try/finally); `state.stderr_buf` receives in-loop stderr
- [x] Refuses under `--agent` / non-interactive (via `tty.is_interactive()`)

### CLI (4)
- [x] `--audience` validated against `AUDIENCE_API_BASE` → `UsageError` on unknown
- [x] `--path` forwarded to `run(start_path=...)`
- [x] `--pretty`/`--ndjson`/`--raw` rejected (TUI is not an output-mode command)
- [x] `owa-graph --agent tui` refused (interactive guard)

### Terminal / UX (6)
- [x] Resize (`SIGWINCH`) handled without crash (Textual handles natively)
- [x] `state.title` = `f'{audience}:{path or "/"}'` (updated on every fetch)
- [x] Header shows `f'{audience} · {profile} · {tenant}'` (profile fixed for session)
- [x] `empty_text = '(no items — press r to retry, a to switch audience)'`
- [x] `FOOTER` constant wired to spec
- [x] `HELP_LINES` constant wired to spec with grouped sections

---

## Pilot test cases (`src/owa_tui/graph/test_graph_screen.py` + `test_graph_fetch.py`)

All tests use `textual.testing.Pilot`; `async def` throughout.

### `TestTokenCache` (mirrors `test_tui_auth.py`)

**TP1** `test_cache_hit_no_remint` — prime `state.token_cache['graph']` with a valid
`TokenInfo`; monkeypatch `get_token_for_config` to raise `AssertionError`; call
`_ensure_token('graph', state)` → returns the cached `TokenInfo`, no mint called.

**TP2** `test_miss_mints_and_populates` — empty cache; monkeypatch `get_token_for_config`
to return a broker with a JWT carrying `scp='User.Read Mail.Read'`; call
`_ensure_token('graph', state)` → `info.scopes == frozenset({'User.Read', 'Mail.Read'})`,
`state.api_base == 'https://graph.microsoft.com/v1.0'`, cache populated.

**TP3** `test_failure_returns_none_evicts` — monkeypatch to raise `AuthExpiredError`;
prime a stale cache entry; call `_ensure_token` → returns `None`, cache evicted,
`'AADSTS700084'` in `state.status`.

**TP4** `test_per_audience_keying` — cache `graph` token; `_ensure_token('azure', state)`
→ mints `azure`, `state.api_base == 'https://management.azure.com'`.

**TP5** `test_expiry_forces_remint` — `exp_epoch = int(time.time()) - 10`; call
`_ensure_token` → fresh mint.

**TP6** `test_expires_at_none_ttl_fallback` — broker returns `expires_at=None`,
`expires_in=None`; call `_ensure_token` → `info.exp_epoch` is a concrete int near
`now + _DEFAULT_TTL`, no `TypeError`.

### `TestFetchItems` (mirrors `test_tui_loop.py:TestFetchItems`)

**TP7** `test_fetch_happy_path` — monkeypatch `_ensure_token` to return good
`TokenInfo`; monkeypatch `_fetch_page` to return `('collection', collection_payload, None)`;
call `fetch_items(state)` → `len(state.items) == 2`, `state.status == ''`.

**TP8** `test_fetch_token_failure_leaves_items_empty` — monkeypatch `_ensure_token` to set
`state.status = 'AADSTS700084...'` and return `None`; call `fetch_items(state)` →
`state.items == []`, `'AADSTS700084'` in `state.status`.

**TP9** `test_fetch_never_raises` — monkeypatch `_fetch_page` to raise `RuntimeError('boom')`;
call `fetch_items(state)` → no exception, `'boom'` in `state.status`.

**TP10** `test_fetch_http_failure_kind` — monkeypatch `_fetch_page` to return
`('auth', 'token expired', None)` → `state.items == []`, `'token expired'` in `state.status`.

**TP11** `test_fetch_sets_response_and_kind` — success path; assert `state.response is payload`
and `state.kind == 'collection'`.

### `TestDrillBack` (mirrors `test_tui_loop.py:TestDrillBack`)

**TP12** `test_drill_pushes_7tuple_history` — call `on_drill(state, drillable_item)`;
`len(state.history) == 1`; `state.history[0][1] == 'me'` (path), `state.dirty is True`.

**TP13** `test_drill_updates_path_via_next_path` — `state.path = 'users'`; drill into
a GUID-id item → `state.path == 'users/<guid>'`.

**TP14** `test_drill_non_drillable_noop` — `Row('(no items)', None, False)` → no history push.

**TP15** `test_back_restores_without_network` — prime `state.history` with a 7-tuple;
monkeypatch `_fetch_page`/`_ensure_token` to record if called; call `on_back(state)` →
`state.path == 'users'`, `state.items is prior_items`, no network call.

**TP16** `test_back_empty_history_returns_false` — `on_back(state)` with empty history
→ returns `False`.

**TP17** `test_back_does_not_set_dirty` — `state.dirty = False` before `on_back`;
assert `state.dirty is False` after.

### `TestRenderDetail`

**TP18** `test_graph_collection_uses_format_pretty` — spy on `_format_pretty`;
`state.audience = 'graph'`, `state.kind = 'collection'` → spy called.

**TP19** `test_arm_collection_no_format_pretty` — `state.audience = 'azure'`,
`state.kind = 'collection'` → spy NOT called.

**TP20** `test_devops_collection_no_format_pretty` — same for `devops`.

**TP21** `test_opaque_hex_dump` — `state.kind = 'opaque'`, raw bytes body → lines
contain `'bytes'` or `'binary'`.

**TP22** `test_scalar_str` — `state.kind = 'scalar'`, payload `42` → `'42'` in lines.

**TP23** `test_tier_d_footer` — `state.audience = 'keyvault'` → `'Tier D'` in last lines.

**TP24** `test_none_item_returns_empty` — `render_detail(None, 80, state=state) == []`.

### `TestNavigation` (mirrors `test_tui_nav.py`)

**TP25** `test_classify_collection` — dict with `value: list` → `('collection', ...)`.

**TP26** `test_classify_opaque` — non-JSON bytes → `('opaque', bytes)`.

**TP27** `test_classify_scalar` — bare string → `('scalar', 'OK')`.

**TP28** `test_build_rows_collection_labels` — two items → labels match `displayName`.

**TP29** `test_build_rows_empty_collection` → `[Row('(no items)', None, False)]`.

**TP30** `test_build_rows_caps_with_sentinel` — `MAX_ROWS + 5` items → `MAX_ROWS + 1`
rows (sentinel row `dim=True`).

**TP31** `test_next_path_absolute_url` — `https://…` target → returned verbatim.

**TP32** `test_next_path_arm_replace` — `/subscriptions/abc` → replaces `current_path`.

**TP33** `test_next_path_relative_append` — `'messages'` → `'me/messages'`.

**TP34** `test_odata_continuation` — payload with `@odata.nextLink` → cursor is the value.

**TP35** `test_arm_continuation` — payload with bare `nextLink` → cursor is the value.

**TP36** `test_devops_continuation_case_insensitive` — response headers with
`X-MS-ContinuationToken` → cursor includes `?continuationToken=<value>`.

### `TestActions`

**TP37** `test_yank_capture_output` — monkeypatch `subprocess.run`; call
`_action_yank_url(state)`; assert `kwargs['capture_output'] is True`.

**TP38** `test_yank_fallback_no_clipboard` — all clipboard tools raise `FileNotFoundError`;
`state.status.startswith('url:')`.

**TP39** `test_open_browser_non_graph_noop` — `state.audience = 'azure'`;
`_action_open_browser(state)` → `'no browser target'` in `state.status`.

**TP40** `test_open_browser_graph_silences_fds` — monkeypatch `silence_os_fds` +
`webbrowser.open`; call `_action_open_browser(state)` → `'graph-explorer'` in opened URL.

**TP41** `test_open_browser_no_browser_available` — `webbrowser.open` returns `False` →
`state.status == 'no browser available'`.

**TP42** `test_render_curl_sets_status_and_buffer` — call `_action_render_curl(state)`;
`state.status` non-empty; `'curl:'` in `state.stderr_buf.getvalue()`.

**TP43** `test_bookmark_adds_and_dedupes` — call `_action_bookmark` twice with same
`(audience, path)` → only one entry in parsed bookmarks.

**TP44** `test_audience_switch_commits_even_on_failure` — `_action_audience_switch(state)`;
record `new_audience`; monkeypatch `_ensure_token` to fail; call `fetch_items` →
`state.audience == new_audience`, `state.items == []`.

**TP45** `test_debug_overlay_shows_buf` — write to `state.stderr_buf`; call
`_action_debug_overlay` → content appears in `state.status`.

**TP46** `test_debug_overlay_toggles` — call twice; overlay `'debug'` then `None`.

**TP47** `test_next_page_extends_items` — set `state.next_link`; monkeypatch
`_fetch_page` to return a new page → `len(state.items)` grows.

**TP48** `test_next_page_noop_when_no_link` — `state.next_link = None` →
`'no next page'` in `state.status`.

### `TestLoopIntegration` (Pilot — drives `App._on_mount` worker)

**TP49** `test_first_worker_mints_and_fetches(pilot)` — monkeypatch token + fetch;
`async with GraphScreen(...).run_test() as pilot: await pilot.pause()`; assert
`len(state.items) == 2`.

**TP50** `test_seed_failure_does_not_exit(pilot)` — monkeypatch token to fail;
run to first idle; assert `app.is_running`, `state.items == []`,
`'auth' in state.status or 'AADSTS' in state.status`.

**TP51** `test_drill_pushes_history_via_pilot(pilot)` — items loaded; send `Enter`;
assert `len(state.history) == 1`.

**TP52** `test_back_restores_without_refetch(pilot)` — prime history; count
`fetch_items` calls; send `h`; assert count did not increment.

**TP53** `test_audience_switch_committed_on_failure(pilot)` — `a` key → new audience
committed even when subsequent fetch fails.

**TP54** `test_debug_overlay_opened_by_D(pilot)` — send `D`; assert overlay visible.

**TP55** `test_quit_terminates_app(pilot)` — send `q`; assert `not app.is_running`.

**TP56** `test_resize_does_not_crash(pilot)` — send `SIGWINCH` equivalent (Textual
`Size` message); assert `app.is_running`.

---

## Files owned by this plan

```
src/owa_tui/graph/__init__.py        (empty package marker)
src/owa_tui/graph/screen.py          (GraphState, render_row, render_detail,
                                      fetch_items, on_drill, on_back, on_search,
                                      on_refresh, actions, build_spec, run)
src/owa_tui/graph/auth.py            (TokenInfo, _ensure_token, _apply_token,
                                      _exp_epoch_from_broker, constants)
src/owa_tui/graph/settings.py        (Settings dataclass, from_config, to_config_dict)
src/owa_tui/graph/fetch.py           (fetch_items async wrapper)
src/owa_tui/graph/menu.py            (GraphMenu)
src/owa_tui/graph/graph.tcss         (Textual CSS)
src/tests/graph/test_graph_screen.py (Pilot tests TP49–TP56)
src/tests/graph/test_graph_fetch.py  (TP7–TP16)
src/tests/graph/test_graph_auth.py   (TP1–TP6)
src/tests/graph/test_graph_nav.py    (TP25–TP36)
src/tests/graph/test_graph_actions.py (TP37–TP48, TP17–TP24)
```

Do NOT edit `owa-tools` at any point.
Do NOT write compatibility shims.
Do NOT import from `owa_graph.tui` (the curses module being deleted).

---

## Final gating check

Before marking this plan complete:

- [ ] All 56 Pilot test cases pass (`pytest src/tests/graph/`)
- [ ] 90% coverage gate still green (run `pytest --cov` before declaring a new widget done)
- [ ] `render_detail` — all 5 branch paths covered (opaque/scalar/graph-collection/non-graph-collection/tier-d)
- [ ] `_ensure_token` — cache-hit / miss / failure / expires_at=None all covered
- [ ] Audience set: `set(AUDIENCE_API_BASE.keys())` == frozen 17-name set (TP coverage)
- [ ] All 8 action keys `o/y/c/a/m/D/n/e` have at least one Pilot test
- [ ] `format_pretty` strictly gated to `audience == 'graph'` (TP19, TP20 guard it)
- [ ] `next_path` 3-shape coverage (absolute URL / absolute path replace / relative append)
- [ ] DevOps header lookup case-insensitive confirmed by TP36
- [ ] `run()` refuses non-interactive (mirrors cal/mail CLI guard)
- [ ] `silence_os_fds()` used in `o` action (TP40 asserts it)
- [ ] `capture_output=True` in `y` action (TP37 asserts it)
- [ ] Breadcrumb `on_back` never triggers network (TP52 asserts count)

Total parity items: 72 discrete behaviors mapped from `owa_graph/tui.py`, `tui_nav.py`,
`tui_settings.py`, `tui_menu.py`, and the curses-explorer spec.
