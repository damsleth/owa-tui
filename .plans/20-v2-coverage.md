# owa-tui v2 coverage — Textual TUI adapters for the remaining eight tools

_Created 2026-06-18. Prerequisite: a v1 owa-tui release must exist on PyPI before
any v2 card ships (the `owa-tools>=1.0.0` constraint keeps the import boundary clean)._

> **Reality check (added 76c2675):** v1 shipped **cal/mail/graph only** — `owa-people` was
> *not* built, so despite the line further down it is **not** v1 scope. Decide: add owa-people as
> a ninth v2 card (a simple `OwaListScreen`) or do it as a v1.x follow-up.
>
> **base/ vs widgets/:** v1 already has a shared kit at `src/owa_tui/widgets/` (`list_browser`,
> `detail_pane`, `settings_overlay`, `menu_state`, `status_bar`). "Step 0 `owa_tui.base`" below
> should *build Screen-level scaffolds on top of those widgets*, not reinvent them — e.g.
> `OwaListScreen` composes `ListBrowser` + `DetailPane` + `SettingsOverlay`.
>
> **Testing standard:** there are no `pytest-textual-snapshot` tests (the dep is declared but
> unused). The real standard, set by v1, is **Pilot tests** (`src/tests/<tool>/`, monkeypatch
> fetch) **plus tui-test e2e** (`e2e/`, fixture-mode). Every v2 card must ship: (1) Pilot tests,
> (2) `e2e/fixtures/<tool>*.json` wired through `OWA_TUI_FIXTURES`, and (3) tui-test specs covering
> its user actions — same pattern as `e2e/actions.test.ts`. Coverage gate is **85%** (`pyproject.toml`),
> not 80%. Heads-up: the fixture seam currently keys on `cal`/`mail`/`mail_body`/`graph/*` — each new
> tool needs its own `fixtures.load("<tool>")` call added at its fetch entrypoint.

## Context & scope

owa-tools' original `tui_kit/` plan was curses-based and tied to `owa_core`.
owa-tui exists precisely to avoid polluting owa-tools with a UI dependency.
This plan covers **Textual** TUIs for the eight tools not yet in owa-tui v1:

| Tool        | Canonical view / interaction                                    | Status  |
|-------------|------------------------------------------------------------------|---------|
| owa-todo    | TodoScreen(OwaListScreen): task list + detail, "/" search, complete-toggle | ✅ shipped (T1) |
| owa-drive   | DriveScreen(OwaTreeScreen): OneDrive folder nav (drill/up), file detail (read-only) | ✅ shipped (T2) |
| owa-planner | PlannerScreen(OwaListScreen): my-tasks list + detail, "/" search (read-only) | ✅ shipped (T5) |
| owa-sched   | SchedScreen(OwaGridScreen): free/busy grid (attendees × slots), read-only | ✅ shipped (T4) |
| owa-ado     | AdoScreen(OwaListScreen): my work-items list + detail, "/" search (read-only) | ✅ shipped (T6) |
| owa-teams   | Chats list → scrollable message thread (read-only v1)            | planned |
| owa-sites   | SitesScreen(OwaTreeScreen): SharePoint lists -> items, detail, "/" search (read-only) | ✅ shipped (T3) |
| owa-doctor  | DoctorScreen(OwaGridScreen): profiles × audiences health grid (local probes) | ✅ shipped (T8) |

**owa-vids** remains deferred (URL-based, no natural list view).
**owa-cal**, **owa-mail**, **owa-graph** are v1 scope (shipped). **owa-people** was planned as
v1 but never built — see the Reality-check note above; treat it as a v2 card or a v1.x follow-up.

## Architecture — owa-tui Textual base pattern

Each tool adapter lives entirely in `owa-tui`, never in `owa-tools`. The import
boundary: `owa_tui` imports `owa_<tool>.api` / `owa_<tool>.<data_module>` only
(the stable library surface listed in `AGENTS.md`).

### Shared `owa_tui.base` widgets (Step 0 for v2)

> **Step 0 status:** ✅ **OwaListScreen shipped & proven by a real consumer (T1 owa-todo).** Lives at
> `src/owa_tui/screens/base/` (`screen.py`, `keys.py`), not `src/owa_tui/base/`.
> Import: `from owa_tui.screens.base import OwaListScreen`. It's the generic flat-list +
> detail + "/" search + Esc-menu scaffold, parameterized by `fetch_items` / `render_row` /
> `render_detail` / `menu_config` hooks, composing `SettingsOverlay` + `StatusBar`, proven
> by `src/tests/base/` (Pilot, fake fetch, ~86%) **and by `TodoScreen(OwaListScreen)`** (T1).
> The shipped cal/mail/graph/people screens were **not** refactored onto it (they work;
> migration is optional later debt). The speculative `base/auth.py` helper was removed (no
> consumer); tools mint tokens via `adapter.access_token_for` directly.
> **`OwaTreeScreen` ✅ shipped** (`src/owa_tui/screens/base/tree.py`, `OwaTreeScreen(OwaListScreen)` +
> `TreeNode`) — a list-of-children + node-stack navigator (drill into containers, `h` pops up),
> proven by `owa-drive` (T2). **Still deferred:** `OwaGridScreen` / `OwaThreadScreen` — they have
> no consumer yet; build each alongside its first real card (T2 drive / T4 sched / T7 teams),
> not speculatively. `OwaListScreen` owns its list/detail via local `_OwaList`/`_DetailPane`;
> the old unused `widgets.ListBrowser`/`DetailPane` were deleted (see plan 01 drift note) — if a
> reusable widget is wanted, build it from plan 01 §5a/§5b and wire it in then.

Extract common Textual structure into `src/owa_tui/base/`:

- **`base/list_screen.py`** — `OwaListScreen(Screen)`: a `ListView`+`DetailPane`
  split. Parameterised by async `fetch_items()`, `render_row()`, `render_detail()`,
  and an `actions` dict mapping key → coroutine. Handles loading spinner, empty
  state, error footer, and `/` search overlay (a `FilterInput` that calls `on_search`).
- **`base/tree_screen.py`** — `OwaTreeScreen(Screen)`: a `Tree`-backed navigator
  for hierarchical stores (drive, sites). Parameterised by async `load_node()` called
  on expansion; drill/back navigation maintained as a node-path stack.
- **`base/grid_screen.py`** — `OwaGridScreen(Screen)`: a `DataTable` for 2-D
  matrix views (sched free/busy grid, doctor pass/fail grid). Rows and columns
  populated by an async `fetch_grid()` callback.
- **`base/thread_screen.py`** — `OwaThreadScreen(Screen)`: a vertically scrollable
  `RichLog` or `Markdown`-rendered message list for read-only thread views (teams).
- **`base/keys.py`** — one keybinding table: `/` search, `j/k` or arrows navigation,
  `enter` drill/select, `esc`/`backspace` back, `q` quit, `r` refresh. Consistent
  across all adapters.
- **`base/auth.py`** — `get_token_async(profile, audience)`: thin async wrapper
  around `owa_core.auth.get_token_for_config`. Shows a status footer while minting.

All base widgets are tested with **Pilot** tests (monkeypatched fetch) plus the
**tui-test e2e** harness in fixture-mode; no live M365 calls. Coverage target: 85% on
`owa_tui.base`, matching the repo-wide 85% gate.

### Per-tool adapter layout

Each tool's adapter is a self-contained directory:

```
src/owa_tui/<tool>/
    __init__.py      # exports run(profile, config, **kwargs)
    app.py           # OwaApp(App) subclass, composes the base Screen(s)
    adapter.py       # fetch_items/load_node/fetch_grid callbacks; calls owa_<tool>.api
    rows.py          # render_row / render_detail helpers (pure, unit-tested)
src/tests/<tool>/
    test_rows.py     # parametrised unit tests for pure row/detail helpers
    test_app.py      # pytest-textual-snapshot snapshot tests for key screens
```

No `cli.py` lives in owa-tui — the entry point is `owa-tui <tool>` dispatched from
`src/owa_tui/__main__.py` (the `owa-tui` console script). Each adapter exposes
`run(profile, config, **kwargs)` so the dispatcher just calls `run(...)`.

## Per-tool card-sets

Each tool is an **independently shippable card-set** — it can be merged and released
as a patch/minor bump without waiting for others. The suggested order follows the
owa-tools rollout rationale: quick wins first, complex views later.

---

### Card-set T1 — owa-todo

> ✅ **Shipped.** `src/owa_tui/screens/todo.py` = `TodoScreen(OwaListScreen)` — the base's first
> real consumer. Tasks via `owa_todo.api` + `normalize_tasks` (outlook REST base), `/` search,
> complete-toggle (no-op in fixture mode), `OWA_TUI_FIXTURES` seam. Tests: `src/tests/todo/`
> (Pilot, todo.py ~97%) + `e2e/todo.test.ts` (7/7). The two-pane "lists sidebar" + create-task
> from the original spec are deferred (read + toggle is the v1 CRUD scope).

**Canonical view:** Two-pane `OwaListScreen` variant: left pane lists task-lists,
right pane lists tasks for the selected list.

**Textual widgets:**
- `ListView` (left) — one item per task-list, highlighted on select.
- `ListView` (right) — one item per task, checkbox emoji prefix for done/not-done.
- `Input` overlay triggered by `n` — new task title; `enter` commits via
  `owa_todo.api.create_task(list_id, title)`.
- `DetailPane` (`Static` / `Markdown`) — task detail (due, body, tags) on `enter`.

**owa-tools imports:** `owa_todo.api.get_lists`, `owa_todo.api.get_tasks`,
`owa_todo.api.toggle_done`, `owa_todo.api.create_task`.

**Keybindings:** `space` toggle done, `n` new task, `d` delete (confirm prompt),
`/` filter tasks in right pane, `r` refresh, `q` quit.

**CRUD scope (v1):** read lists + tasks; toggle done; create task. Edit/delete task
deferred (confirm dialog required — carry as a TODO comment).

**Tests:**
- `test_rows.py`: `render_task_row(task)` with done/undone/overdue states.
- `test_app.py`: snapshot — initial two-pane layout; snapshot — task toggled done.
- Coverage target: rows.py 100%, adapter.py 80% (mock `owa_todo.api`).

**Pilot test cases:**
1. Launch with no tasks → empty-state message visible in right pane.
2. Select a list → tasks populate right pane.
3. Press `space` on a task → checkbox flips; API mock called with correct list_id + task_id.
4. Press `n`, type title, `enter` → task appears at bottom of list; API mock called.
5. Press `/`, type partial title → list filters; clear filter restores full list.

---

### Card-set T2 — owa-drive

> ✅ **Shipped.** `src/owa_tui/screens/drive.py` = `DriveScreen(OwaTreeScreen)` — first consumer of
> the new tree base. Lists OneDrive children via `owa_drive.paths.children_endpoint` + `normalize_item`
> (Graph base), drills into folders / `h` pops up, file detail, `/` search, path-keyed `OWA_TUI_FIXTURES`
> seam (`drive` root + `drive_<slug>` per folder, fallback to root). **Read-only** (download/upload/delete
> deferred). Tests: `src/tests/drive/` (Pilot, drive.py 99%) + `src/tests/base/test_tree_screen.py`
> (tree.py 96%) + `e2e/drive.test.ts` (6/6, drill+up verified).

**Canonical view:** `OwaTreeScreen` file navigator.

**Textual widgets:**
- `Tree` — root node "OneDrive", child nodes lazy-loaded via `load_node(item_id)`.
  Folders expand in-place; files are leaf nodes with size/modified in the label.
- `Label` footer — current path breadcrumb.
- `Static` detail sidebar (right, optional) — file metadata on `enter` for a file node.

**owa-tools imports:** `owa_drive.api.list_root`, `owa_drive.api.list_children`,
`owa_drive.api.get_item`, `owa_drive.api.get_download_url`.

**Keybindings:** `enter` expand/collapse folder or open-in-browser for file,
`d` download (writes to `~/Downloads/<name>` via `httpx` or `urllib`),
`backspace` collapse/back, `/` search (calls `owa_drive.api.search`), `r` refresh
current node, `q` quit.

**CRUD scope (v1):** navigate + open/download. Upload/delete deferred.

**Tests:**
- `test_rows.py`: `render_drive_node(item)` for folder vs. file, size formatting.
- `test_app.py`: snapshot — root tree with two folders; snapshot — folder expanded.
- Coverage target: rows.py 100%, adapter.py 80%.

**Pilot test cases:**
1. Launch → root "OneDrive" node visible; expand → children load asynchronously.
2. Navigate into a nested folder; breadcrumb updates.
3. Press `enter` on a file → browser opens (mock `webbrowser.open`).
4. Press `/`, type filename → search results replace tree view; `esc` restores tree.
5. Press `r` on a folder → node reloads without collapsing siblings.

---

### Card-set T3 — owa-sites

> ✅ **Shipped.** `src/owa_tui/screens/sites.py` = `SitesScreen(OwaTreeScreen)` — second tree consumer.
> Two-level nav: site **lists** at root (`lists_endpoint` + `normalize_lists`) → drill a list to its
> **items** (`list_items_endpoint` + `normalize_items`) via SharePoint REST `paginate_sp` (Graph
> `/sites` 403s; SP token minted through `owa_sites.auth.setup_auth`), `h` pops up, item detail, `/`
> search, path-keyed `OWA_TUI_FIXTURES` seam. **Read-only.** Tests: `src/tests/sites/` (Pilot + unit,
> sites.py 96%, incl. mocked live lists→items) + `e2e/sites.test.ts` (6/6, drill+up verified). **Live
> SharePoint path mocked-tested, not e2e-verifiable without a real site** (like ado).

**Canonical view:** `OwaTreeScreen` three-level browser: sites → lists+libraries → items/docs.

**Textual widgets:**
- `Tree` — level 0: site nodes; level 1: list/library nodes (with a `[hidden]` dimmed
  label for hidden lists); level 2: item/doc leaf nodes.
- Toggle `h` — show/hide hidden lists/libraries (mirrors `lf`'s `.` toggle).
- `Static` sidebar — selected item metadata (content type, modified, URL).

**owa-tools imports:** `owa_sites.api.list_sites`, `owa_sites.api.list_lists`,
`owa_sites.api.list_items`, `owa_sites.api.get_item`.

**Keybindings:** `h` toggle hidden, `enter` expand/drill or open-in-browser,
`backspace` back one level, `/` search (search within current level),
`d` download (doc libraries only), `r` refresh, `q` quit.

**CRUD scope (v1):** navigate + open/download. Upload/delete deferred.

**Dependency:** Build after T2 (drive); the tree navigation pattern is identical,
only the API layer changes. Re-use `OwaTreeScreen` base; adapt `load_node` for
SPO's three-tier hierarchy.

**Tests:**
- `test_rows.py`: `render_site_node`, `render_list_node` (hidden vs. visible),
  `render_item_node` (doc vs. list item).
- `test_app.py`: snapshot — top-level sites list; snapshot — hidden toggle.
- Coverage target: rows.py 100%, adapter.py 80%.

**Pilot test cases:**
1. Launch → site list visible.
2. Expand a site → lists and libraries appear; hidden ones present but dimmed.
3. Press `h` → hidden items toggle off; press `h` again → restore.
4. Drill into a document library → document leaf nodes appear.
5. Press `enter` on a document → browser open mock called with correct URL.

---

### Card-set T4 — owa-sched

> ✅ **Shipped.** `src/owa_tui/screens/sched.py` = `SchedScreen(OwaGridScreen)` — first consumer of
> the new **`OwaGridScreen`** base (`src/owa_tui/screens/base/grid.py`, a `DataTable` matrix with a
> `fetch_grid`+`cell_style` hook contract; not list+detail). Free/busy grid: attendee rows × time-slot
> columns, cells busy/free/tentative from `getSchedule` `availabilityView` (`owa_sched.api.api_post` +
> `normalize_attendee` + `slots_in_window`, Graph base), `r` refresh, Esc menu, `OWA_TUI_FIXTURES`
> seam. **Read-only.** Tests: `src/tests/sched/` + `src/tests/base/test_grid_screen.py` (Pilot + unit,
> incl. mocked live getSchedule) + `e2e/sched.test.ts`. Live getSchedule path mocked-tested, not
> e2e-verifiable without real calendars.

**Canonical view:** `OwaGridScreen` availability grid — rows = attendees, columns = time slots.

**Textual widgets:**
- `DataTable` — columns are 30-min (or configurable) slots across the requested
  day range; rows are attendee email addresses. Cells: "FREE", "BUSY", "OOF",
  "UNKNOWN" with Rich colour markup (green/red/amber/grey).
- `Input` header bar — add/remove attendees (comma-separated), date range selector.
- `Label` footer — selected cell's exact free/busy detail on cursor move.

**owa-tools imports:** `owa_sched.api.get_availability`, `owa_sched.api.parse_slots`.

**Keybindings:** `a` add attendee (input prompt), `r` refresh grid, `arrow` cursor
through cells, `enter` show full detail for selected cell, `q` quit. `/` not
applicable (no search in a matrix view — omit or no-op).

**CRUD scope (v1):** read-only availability grid.

**Tests:**
- `test_rows.py`: `render_slot_cell(slot)` for each status type; colour mapping.
- `test_app.py`: snapshot — 2-attendee × 4-slot grid; snapshot — OOF cell selected.
- Coverage target: rows.py 100%, adapter.py 80%.

**Pilot test cases:**
1. Launch with two attendees → grid populates with correct slot count.
2. Navigate cursor to a BUSY cell → footer shows meeting subject if available.
3. Press `a`, enter new attendee → row appended, grid refreshed.
4. Press `r` → grid re-fetches; loading indicator shown briefly.
5. All-FREE row → all cells green.

---

### Card-set T5 — owa-planner

> ✅ **Shipped.** `src/owa_tui/screens/planner.py` = `PlannerScreen(OwaListScreen)`. Lists
> `me/planner/tasks` via `owa_planner.api` + `normalize_tasks` (Graph base), detail pane, `/`
> search, `OWA_TUI_FIXTURES` seam. **Read-only** (v1 scope) — the plan→bucket→task drill and
> complete-toggle from the original spec are deferred. Tests: `src/tests/planner/` (Pilot,
> planner.py 100%) + `e2e/planner.test.ts` (6/6). Second `OwaListScreen` consumer after todo.

**Canonical view:** `OwaListScreen` drill: plans list → buckets+tasks (grouped), toggle complete.

**Textual widgets:**
- Level 0 (`ListView`) — plans for the signed-in user.
- Level 1 (`ListView`) — tasks grouped by bucket; group header rows (non-selectable,
  dimmed) interspersed with task rows. Checkbox prefix for completion status.
- `DetailPane` (`Static`/`Markdown`) — task detail: description, due, assignees,
  checklist items.

**owa-tools imports:** `owa_planner.api.get_plans`, `owa_planner.api.get_buckets`,
`owa_planner.api.get_tasks`, `owa_planner.api.toggle_complete`.

**Keybindings:** `enter` drill in (plan → tasks), `backspace` back to plans,
`space` toggle task complete, `/` filter tasks by title, `r` refresh, `q` quit.

**CRUD scope (v1):** read plans + tasks; toggle complete. Create/edit/delete deferred.

**Tests:**
- `test_rows.py`: `render_plan_row`, `render_task_row` (complete/incomplete/overdue),
  `render_bucket_header`.
- `test_app.py`: snapshot — plan list; snapshot — tasks grouped by bucket.
- Coverage target: rows.py 100%, adapter.py 80%.

**Pilot test cases:**
1. Launch → plans list visible; select a plan → tasks grouped by bucket.
2. Press `backspace` → return to plans list.
3. Press `space` on a task → checkbox flips; API mock called with correct task_id.
4. Press `/`, type partial task title → list filters.
5. Overdue task → due date rendered in red.

---

### Card-set T6 — owa-ado

> ✅ **Shipped.** `src/owa_tui/screens/ado.py` = `AdoScreen(OwaListScreen)`. Lists my work items
> via the ADO two-step (WIQL `POST` → batch `GET` through `ado_request`, org/project from
> `owa_ado.config`, audience `"devops"`) + `normalize_work_item`, detail pane, `/` search,
> `OWA_TUI_FIXTURES` seam (returns before any `ado_request`). **Read-only** — create/edit/
> state-change and the `v` view-switch deferred. Tests: `src/tests/ado/` (Pilot + unit, ado.py
> 100%, incl. a mocked two-step live-path test) + `e2e/ado.test.ts` (6/6). **Live ADO path is
> unit-tested with mocks but not e2e-verifiable without a real org/PAT** (by design for v1).
> Third `OwaListScreen` consumer — flat-list trio (todo/planner/ado) complete.

**Canonical view:** `OwaListScreen` work-items list (assigned-to-me by default),
drill to detail.

**Textual widgets:**
- `ListView` — one item per work item: ID, type icon, title, state, priority.
- `DetailPane` (`Markdown`) — full work item: description, acceptance criteria,
  comments, history. Rich markdown render of HTML body via `html2text` or regex strip.
- `Select` widget (header) — switch view: assigned-to-me / current sprint /
  custom WIQL query.

**owa-tools imports:** `owa_ado.api.get_work_items`, `owa_ado.api.get_work_item`,
`owa_ado.api.update_state` (optional, behind confirm).

**Keybindings:** `enter` open detail, `backspace` back to list, `v` cycle view
(assigned/sprint), `o` open in browser, `s` change state (optional, confirm prompt),
`/` search/filter list, `r` refresh, `q` quit.

**CRUD scope (v1):** read + optional state transition behind confirm. Create/edit deferred.

**Tests:**
- `test_rows.py`: `render_wi_row(wi)` — type icon mapping (Bug/Task/UserStory/Epic),
  state colour, priority indicator. `render_wi_detail(wi)`.
- `test_app.py`: snapshot — assigned-to-me list; snapshot — detail pane open.
- Coverage target: rows.py 100%, adapter.py 80%.

**Pilot test cases:**
1. Launch → assigned-to-me list (mocked); items show type icons and state.
2. Press `enter` → detail pane shows description and comments.
3. Press `v` → switch to sprint view; list repopulates.
4. Press `o` → browser mock called with correct work item URL.
5. Press `/`, type "login" → list filters to matching items.

---

### Card-set T7 — owa-teams

**Canonical view:** `OwaListScreen` (chats) + `OwaThreadScreen` (message thread).

**Textual widgets:**
- `ListView` (left/first screen) — one item per chat: display name, last message
  preview, timestamp. 1:1 chats show the other party's name; group chats show
  the group name.
- `OwaThreadScreen` (right/drill) — `RichLog` or vertical `Static` scroll; each
  message rendered as `**Sender** timestamp\n body`. Handles rich text via
  `html2text` or `Markdown`.

**owa-tools imports:** `owa_teams.api.get_chats`, `owa_teams.api.get_messages`.
(If `owa_teams` does not yet expose these, note as a prerequisite — this card is
blocked until `owa_teams.api` has `get_chats` and `get_messages`.)

**Keybindings:** `enter` open thread, `backspace` back to chats list, `r` refresh
(chats or thread), `j/k` scroll in thread, `q` quit. No send in v1.

**CRUD scope (v1):** read-only (chats list + thread). Send deferred.

**Tests:**
- `test_rows.py`: `render_chat_row(chat)`, `render_message_block(msg)` — sender
  truncation, timestamp formatting, HTML body stripping.
- `test_app.py`: snapshot — chats list; snapshot — thread with 3 messages.
- Coverage target: rows.py 100%, adapter.py 80%.

**Pilot test cases:**
1. Launch → chats list visible; 1:1 vs group chats labelled correctly.
2. Select a chat → thread screen shown with messages in chronological order.
3. Press `backspace` → return to chats list.
4. Press `r` in thread → messages re-fetched; loading indicator shown.
5. Long message body wraps correctly without overflowing the terminal width.

---

### Card-set T8 — owa-doctor

> ✅ **Shipped.** `src/owa_tui/screens/doctor.py` = `DoctorScreen(OwaGridScreen)` — second grid
> consumer. Profiles (rows, from `list_piggy_profiles`) × audiences (columns) health grid; each cell
> = `classify_finding(probe_profile_token(alias, audience))` rendered ok/warn/fail (green/yellow/red).
> **Local probes — no api_base/token/network**; probes run in an executor thread; fixture mode
> short-circuits before probing. `r` refresh, Esc menu. Tests: `src/tests/doctor/` (Pilot + unit,
> doctor.py 100%, incl. mocked live probe path) + `e2e/doctor.test.ts` (5/5). Live probe path
> mocked-tested, not e2e-verifiable in CI (needs owa-piggy + profiles).

**Canonical view:** `OwaGridScreen` live health dashboard — profiles × audiences.

**Textual widgets:**
- `DataTable` — rows = profiles (from `owa-piggy`), columns = audiences/scopes.
  Cells: `PASS` (green), `FAIL` (red), `SKIP` (grey), `...` (pending).
- `Label` footer — selected cell's error detail (HTTP status, AADSTS code) on cursor.
- `Label` header — last-refresh timestamp.

**owa-tools imports:** `owa_doctor.api.run_checks` (or equivalent; consult
`src/owa_doctor/` in owa-tools for the actual function name). The adapter calls
`run_checks` per profile × audience pair concurrently via `asyncio.gather`.

**Keybindings:** `r` re-run all checks (async, shows `...` while in-flight),
`enter` show full error detail for selected cell, `arrow` navigate cells, `q` quit.
`/` not meaningful in a fixed matrix view — omit.

**CRUD scope (v1):** read-only (health check runner). No token minting or config
changes from within the TUI.

**Tests:**
- `test_rows.py`: `render_check_cell(result)` for PASS/FAIL/SKIP/PENDING;
  `format_error_detail(err)` — AADSTS code extraction.
- `test_app.py`: snapshot — 2-profile × 3-audience grid (all PASS);
  snapshot — one FAIL cell selected, footer shows error.
- Coverage target: rows.py 100%, adapter.py 80%.

**Pilot test cases:**
1. Launch → grid shows `...` while checks run; cells populate as results arrive.
2. FAIL cell selected → footer shows HTTP status and AADSTS error code.
3. Press `r` → all cells reset to `...`, checks re-run concurrently.
4. Profile with no audiences → row present but all cells SKIP (not crash).
5. Network error on one check → that cell FAIL with "network error" detail; others unaffected.

---

## Build order & parallelisation

Recommended sequencing (each is independently mergeable after the base is stable):

```
Step 0: owa_tui.base (list_screen, tree_screen, grid_screen, thread_screen, keys, auth)
  — single agent, proof-test against existing owa-cal and owa-mail adapters
  — must be merged before any v2 card starts

Batch A (parallel — independent file trees):
  T1 owa-todo    (OwaListScreen, two-pane variant)
  T4 owa-sched   (OwaGridScreen)
  T8 owa-doctor  (OwaGridScreen, async checks)

Batch B (parallel — after A merged):
  T2 owa-drive   (OwaTreeScreen)
  T5 owa-planner (OwaListScreen, drill variant)
  T6 owa-ado     (OwaListScreen + view switch)
  T7 owa-teams   (OwaListScreen + OwaThreadScreen)

Batch C (sequential — T3 depends on T2):
  T3 owa-sites   (OwaTreeScreen, three-level hierarchy)
```

Max concurrent agents per batch: 3 (coverage gate + base widget churn).

## Coverage gate

owa-tui uses a repo-wide 85% `fail_under` (see `pyproject.toml`). Each card-set
must keep the gate green on merge. Strategy: keep all logic in `rows.py` (pure,
easily tested) and `adapter.py` (testable with mocked `owa_<tool>.api`). The
Textual `app.py` App subclass is snapshot-tested but not line-coverage-critical —
`# pragma: no cover` the `compose()` / `on_mount()` bodies that are fully exercised
by the snapshot test runner, same discipline as owa-mail.

## What this plan explicitly drops from the old curses rollout

- `tui_kit/` (curses) — entirely superseded by `owa_tui.base` (Textual).
- `cmd_tui` in owa-tools `cli.py` — no longer needed; owa-tui is a separate
  distribution with its own entry point.
- Curses `_loop`, `silence_os_fds`, `state.dirty`, `_pending_respond` sentinel —
  replaced by Textual's reactive/worker model.
- Step 0.1 (`stdscr` pass-through to action callbacks) — not applicable; Textual
  actions receive the `App` instance and can call `app.push_screen` or `app.notify`.
- `owa_core/tty.py` `is_interactive` guard — owa-tui's `__main__.py` should guard
  non-TTY invocations via `sys.stdout.isatty()` and print a clear error; no
  `--agent` flag needed (owa-tui has no `--agent` mode).
