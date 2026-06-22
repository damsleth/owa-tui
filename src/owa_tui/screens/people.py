"""PeopleScreen — Textual screen for owa-people (Microsoft 365 contacts TUI).

Architecture
------------
PeopleScreen(Screen)
  ├── Header
  ├── Horizontal / Vertical  (depends on settings.detail_pane)
  │   ├── PeopleList(ListView)   — left/top pane
  │   └── DetailPane(ScrollableContainer) — right/bottom (hidden when 'off')
  └── StatusBar

Detail-pane modes
-----------------
right  — Horizontal split: list left (split_ratio %), pane right
bottom — Vertical split: list top (split_ratio %), pane bottom
off    — list fills screen; Enter/l pushes full-screen DetailScreen

All blocking owa-tools I/O runs in @work(thread=True) workers — the
Textual event loop is never stalled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from owa_tui.people.settings import (
    DEFAULTS as SETTINGS_DEFAULTS,
)
from owa_tui.people.settings import (
    PeopleSettings,
    cycle,
    from_config,
    to_config_dict,
)
from owa_tui.widgets.settings_overlay import SettingsOverlay
from owa_tui.widgets.status_bar import StatusBar

API_BASE = "https://graph.microsoft.com/v1.0"

# ---------------------------------------------------------------------------
# Pure-Python helpers
# ---------------------------------------------------------------------------


def _list_row(person: dict, width: int = 80) -> str:
    """Format a single person entry for display in the list."""
    name = person.get("displayName") or "(no name)"
    email = person.get("email") or ""
    title = person.get("jobTitle") or ""
    dept = person.get("department") or ""

    # Build right side: title / dept info
    right_parts = [p for p in (title, dept) if p]
    right = "  ".join(right_parts)

    # Truncate to fit
    max_left = max(20, width // 2 - 2)
    max_right = max(10, width - max_left - 4)

    left = f"{name}"
    if email:
        left = f"{name} <{email}>"

    if len(left) > max_left:
        left = left[: max_left - 1] + "…"
    if right and len(right) > max_right:
        right = right[: max_right - 1] + "…"

    if right:
        gap = width - len(left) - len(right) - 2
        gap = max(1, gap)
        return f"{left}{' ' * gap}{right}"
    return left


def _render_person_detail(person: dict) -> str:
    """Render a person dict as a plain-text detail view."""
    lines: list[str] = []
    name = person.get("displayName") or "(no name)"
    lines.append(f"Name:     {name}")

    email = person.get("email") or ""
    if email:
        lines.append(f"Email:    {email}")

    title = person.get("jobTitle") or ""
    if title:
        lines.append(f"Title:    {title}")

    dept = person.get("department") or ""
    if dept:
        lines.append(f"Dept:     {dept}")

    company = person.get("companyName") or ""
    if company:
        lines.append(f"Company:  {company}")

    office = person.get("officeLocation") or ""
    if office:
        lines.append(f"Office:   {office}")

    mobile = person.get("mobilePhone") or ""
    if mobile:
        lines.append(f"Mobile:   {mobile}")

    biz_phones = person.get("businessPhones") or []
    if biz_phones:
        lines.append(f"Phone:    {', '.join(biz_phones)}")

    source = person.get("source") or ""
    if source:
        lines.append(f"Source:   {source}")

    return "\n".join(lines)


def _sort_people(people: list[dict], sort_by: str) -> list[dict]:
    """Sort a list of person dicts by the given key."""
    if sort_by == "name_desc":
        return sorted(people, key=lambda p: (p.get("displayName") or "").casefold(), reverse=True)
    elif sort_by == "email_asc":
        return sorted(people, key=lambda p: (p.get("email") or "").casefold())
    else:  # name_asc (default)
        return sorted(people, key=lambda p: (p.get("displayName") or "").casefold())


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


class DetailPane(ScrollableContainer):
    """Scrollable detail pane for a single person."""

    DEFAULT_CSS = """
    DetailPane {
        overflow-y: scroll;
        padding: 0 1;
        border-left: solid $border;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="detail-content")

    def show_person(self, person: dict) -> None:
        content = _render_person_detail(person)
        self.query_one("#detail-content", Static).update(content)

    def clear(self) -> None:
        self.query_one("#detail-content", Static).update("")


class PeopleList(ListView):
    """Scrollable people list widget with vim-style keybindings."""

    @dataclass
    class ItemSelected(Message):
        person: dict

    @dataclass
    class ItemActivated(Message):
        person: dict

    def __init__(self, people: list[dict], settings: PeopleSettings, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._people: list[dict] = list(people)
        self._settings = settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_people(self, people: list[dict], settings: PeopleSettings) -> None:
        self._people = list(people)
        self._settings = settings
        self._rebuild()

    def current_person(self) -> dict | None:
        idx = self.index
        if idx is None or idx >= len(self._people):
            return None
        return self._people[idx]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rebuild(self) -> None:
        self.clear()
        if not self._people:
            self.append(ListItem(Static("(no people)", id="no-people-label")))
            return
        for p in self._people:
            row_text = _list_row(p, width=self.size.width or 80)
            self.append(ListItem(Label(row_text)))

    # ------------------------------------------------------------------
    # Textual overrides
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._rebuild()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        event.stop()
        p = self.current_person()
        if p is not None:
            self.post_message(self.ItemSelected(p))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        p = self.current_person()
        if p is not None:
            self.post_message(self.ItemActivated(p))


# ---------------------------------------------------------------------------
# Search modal (mirrors mail's SearchModal exactly)
# ---------------------------------------------------------------------------


class SearchModal(ModalScreen[str | None]):
    """Simple search prompt modal."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    SearchModal {
        align: center middle;
    }
    SearchModal #search-box {
        width: 60;
        height: auto;
        border: solid $border;
        background: $surface;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Static(id="search-box"):
            yield Label("Search people:", classes="overlay-title")
            yield Input(placeholder="name or email…", id="search-input")
            yield Label("Enter to search  Esc to cancel", classes="overlay-hint")

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Full-screen detail screen (used when detail_pane == 'off')
# ---------------------------------------------------------------------------


class DetailScreen(Screen[None]):
    """Full-screen detail pushed when detail_pane is 'off'."""

    BINDINGS = [
        Binding("q", "pop_screen", "Back"),
        Binding("escape", "pop_screen", "Back"),
        Binding("h", "pop_screen", "Back"),
        Binding("left", "pop_screen", "Back"),
        Binding("j", "scroll_down_line", "Down", show=False),
        Binding("k", "scroll_up_line", "Up", show=False),
        Binding("space", "scroll_down_page", "Page Down", show=False),
        Binding("pagedown", "scroll_down_page", "Page Down", show=False),
        Binding("pageup", "scroll_up_page", "Page Up", show=False),
        Binding("g", "scroll_top", "Top", show=False),
        Binding("G", "scroll_bottom", "Bottom", show=False),
    ]

    def __init__(self, person: dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._person = person

    def compose(self) -> ComposeResult:
        yield Header()
        yield DetailPane(id="full-detail-pane")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(DetailPane).show_person(self._person)

    def action_pop_screen(self) -> None:
        self.app.pop_screen()

    def action_scroll_down_line(self) -> None:
        self.query_one(DetailPane).scroll_down(animate=False)

    def action_scroll_up_line(self) -> None:
        self.query_one(DetailPane).scroll_up(animate=False)

    def action_scroll_down_page(self) -> None:
        self.query_one(DetailPane).scroll_page_down(animate=False)

    def action_scroll_up_page(self) -> None:
        self.query_one(DetailPane).scroll_page_up(animate=False)

    def action_scroll_top(self) -> None:
        self.query_one(DetailPane).scroll_home(animate=False)

    def action_scroll_bottom(self) -> None:
        self.query_one(DetailPane).scroll_end(animate=False)


# ---------------------------------------------------------------------------
# Main screen
# ---------------------------------------------------------------------------


class PeopleScreen(Screen[None]):
    """Textual screen for owa-people: people list + detail pane."""

    TITLE = "owa-people"

    BINDINGS = [
        Binding("j", "move_down", "Down", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("up", "move_up", "Up", show=False),
        Binding("g", "go_top", "Top", show=False),
        Binding("G", "go_bottom", "Bottom", show=False),
        Binding("enter", "open_detail", "Open"),
        Binding("l", "open_detail", "Open", show=False),
        Binding("h", "close_detail", "Back", show=False),
        Binding("left", "close_detail", "Back", show=False),
        Binding("tab", "focus_pane", "Focus pane", show=False),
        Binding("r", "refresh", "Refresh"),
        Binding("/", "search", "Search"),
        Binding("escape", "open_menu", "Menu"),
        Binding("q", "quit", "Quit"),
    ]

    # Reactive state
    people: reactive[list[dict]] = reactive(list, recompose=False)
    selected: reactive[int] = reactive(0)
    search: reactive[str] = reactive("")
    settings: reactive[PeopleSettings] = reactive(lambda: PeopleSettings())
    status: reactive[str] = reactive("")
    mode: reactive[str] = reactive("list")

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        debug: bool = False,
        initial_people: list[dict] | None = None,
        initial_settings: PeopleSettings | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config: dict[str, Any] = config or {}
        self._debug = debug
        self._detail_cache: dict[str, dict] = {}
        self._api_base: str = self._config.get("api_base", API_BASE)
        self._selected_person: dict | None = None

        # Load settings from config (or use provided initial_settings for tests)
        if initial_settings is not None:
            self.settings = initial_settings
        else:
            try:
                from owa_people.config import load_config  # type: ignore[import]  # noqa: PLC0415

                self.settings = from_config(load_config())
            except Exception:
                self.settings = SETTINGS_DEFAULTS

        # Pre-load people for tests without live auth
        if initial_people is not None:
            self.people = list(initial_people)
            self._people_preloaded = True
        else:
            self._people_preloaded = False

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield self._build_layout()
        yield StatusBar(self.status, id="status-bar")
        yield Footer()

    def _build_layout(self) -> Any:
        """Build the list + pane container based on detail_pane setting."""
        pane = self.settings.detail_pane
        ratio = self.settings.split_ratio

        pl = PeopleList(
            self._sorted_people(),
            self.settings,
            id="people-list",
        )

        if pane == "right":
            return _LayoutRight(ratio, pl, DetailPane(id="detail-pane"))
        elif pane == "bottom":
            return _LayoutBottom(ratio, pl, DetailPane(id="detail-pane"))
        else:  # off
            return _LayoutOff(pl)

    # ------------------------------------------------------------------
    # Mount / lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        if not self._people_preloaded:
            self._fetch_list()

    def _sorted_people(self) -> list[dict]:
        return _sort_people(self.people, self.settings.sort_by)

    # ------------------------------------------------------------------
    # Workers (blocking I/O off event loop)
    # ------------------------------------------------------------------

    @work(thread=True)
    def _fetch_list(self, search: str = "") -> None:
        """Fetch people list from Graph API in a background thread."""
        self.app.call_from_thread(lambda: setattr(self, "status", "Loading people…"))
        try:
            from owa_people.api import api_get, build_query  # type: ignore[import]  # noqa: PLC0415
            from owa_people.people import normalize_person  # type: ignore[import]  # noqa: PLC0415

            token = self._get_token_sync()
            if not token:
                self.app.call_from_thread(lambda: setattr(self, "status", "auth failed"))
                return

            # Build endpoint
            params: dict[str, Any] = {"$top": 50}
            if search:
                params["$search"] = f'"{search}"'
            qs = build_query(params)
            endpoint = f"me/people?{qs}" if qs else "me/people"
            headers = {"ConsistencyLevel": "eventual"}

            from owa_tui import fixtures  # noqa: PLC0415

            raw = fixtures.load("people")
            if raw is None:
                raw = api_get(
                    self._api_base,
                    endpoint,
                    token,
                    extra_headers=headers,
                    debug=self._debug,
                )
            if raw is None:
                self.app.call_from_thread(
                    lambda: setattr(self, "status", "fetch failed: no data returned")
                )
                return

            items = (raw or {}).get("value") or []
            persons = [normalize_person(i, "people") for i in items]
            self.app.call_from_thread(self._apply_people, persons, search)
        except Exception as exc:
            err = str(exc)
            self.app.call_from_thread(lambda: setattr(self, "status", f"error: {err}"))

    def _get_token_sync(self) -> str:
        """Mint a fresh auth token via owa-piggy (runs in worker thread)."""
        from owa_tui.adapter import access_token_for  # noqa: PLC0415

        return access_token_for(self._config, tool_name="owa-people", audience="graph")

    def _apply_people(self, persons: list[dict], search: str) -> None:
        """Called on main thread after successful list fetch."""
        self.people = persons
        self.search = search
        self.selected = 0
        self._detail_cache = {}
        self._refresh_list()
        count = len(persons)
        self.status = f"{count} person{'s' if count != 1 else ''}"

    @work(thread=True)
    def _fetch_detail(self, person_id: str) -> None:
        """Lazy-fetch a person's full profile in a background thread."""
        if person_id in self._detail_cache:
            self.app.call_from_thread(self._show_cached_detail, person_id)
            return
        try:
            from owa_people.api import api_get  # type: ignore[import]  # noqa: PLC0415
            from owa_people.people import normalize_person  # type: ignore[import]  # noqa: PLC0415

            token = self._get_token_sync()
            if not token:
                self.app.call_from_thread(self._on_detail_failed)
                return

            path = f"users/{person_id}"
            from owa_tui import fixtures  # noqa: PLC0415

            raw = fixtures.load("people_detail")
            if raw is None:
                raw = api_get(self._api_base, path, token, debug=self._debug)
            if raw is None:
                self.app.call_from_thread(self._on_detail_failed)
                return

            full_person = normalize_person(raw, "directory")
            self._detail_cache[person_id] = full_person
            self.app.call_from_thread(self._show_cached_detail, person_id)
        except Exception as exc:
            err = str(exc)
            self.app.call_from_thread(
                lambda: setattr(self, "status", f"failed to load person: {err}")
            )
            self.app.call_from_thread(lambda: setattr(self, "mode", "list"))

    def _show_cached_detail(self, person_id: str) -> None:
        """Display cached detail in detail pane or push DetailScreen."""
        full = self._detail_cache.get(person_id)
        if full is None:
            self._on_detail_failed()
            return

        if self.settings.detail_pane == "off":
            self.app.push_screen(DetailScreen(full))
        else:
            try:
                pane = self.query_one("#detail-pane", DetailPane)
                pane.show_person(full)
                self.mode = "detail"
            except Exception:
                self.app.push_screen(DetailScreen(full))

    def _on_detail_failed(self) -> None:
        self.status = "failed to load person"
        self.mode = "list"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_move_down(self) -> None:
        pl = self._people_list()
        if pl is not None:
            pl.action_cursor_down()

    def action_move_up(self) -> None:
        pl = self._people_list()
        if pl is not None:
            pl.action_cursor_up()

    def action_go_top(self) -> None:
        pl = self._people_list()
        if pl is not None:
            pl.index = 0
            self.selected = 0

    def action_go_bottom(self) -> None:
        pl = self._people_list()
        sorted_people = self._sorted_people()
        if pl is not None and sorted_people:
            last = len(sorted_people) - 1
            pl.index = last
            self.selected = last

    def action_open_detail(self) -> None:
        person = self._current_person()
        if person is None:
            return
        person_id = person.get("id") or ""
        if not person_id:
            return
        if person_id in self._detail_cache:
            self._show_cached_detail(person_id)
        else:
            self._fetch_detail(person_id)

    def action_close_detail(self) -> None:
        if self.settings.detail_pane == "off":
            pass  # nothing to close from list view
        else:
            try:
                pl = self._people_list()
                if pl:
                    pl.focus()
            except Exception:
                pass
            self.mode = "list"

    def action_focus_pane(self) -> None:
        if self.settings.detail_pane == "off":
            return
        try:
            pane = self.query_one("#detail-pane", DetailPane)
            if self.focused == pane:
                pl = self._people_list()
                if pl:
                    pl.focus()
            else:
                pane.focus()
        except Exception:
            pass

    def action_refresh(self) -> None:
        self._fetch_list(search=self.search)

    def action_search(self) -> None:
        def _on_search_result(query: str | None) -> None:
            if not query:
                return
            self._fetch_list(search=query)

        self.app.push_screen(SearchModal(), _on_search_result)

    def action_open_menu(self) -> None:
        settings_fields = [
            ("detail_pane", "Detail pane"),
            ("split_ratio", "Split ratio"),
            ("sort_by", "Sort by"),
            ("_reset", "Reset to defaults"),
        ]
        overlay = SettingsOverlay(
            title_lines=["owa-people — settings"],
            top_items=[
                ("Resume", "resume"),
                ("Settings", "settings"),
                ("Help", "help"),
                ("Quit", "quit"),
            ],
            settings_fields=settings_fields,
            settings=self.settings,
            cycle_fn=cycle,
            on_change=self._on_setting_changed,
        )
        self.app.push_screen(overlay, self._handle_overlay)

    def _on_setting_changed(self, _field: str, new_settings: PeopleSettings) -> None:
        """Live callback from the overlay each time a field is cycled."""
        self._apply_settings(new_settings)

    def _handle_overlay(self, result: str) -> None:
        if result == "resume" or result is None:
            return
        if result == "quit":
            self.app.exit()
            return
        if result == "help":
            self.status = "j/k move  g/G top/bottom  Enter open  / search  r refresh"
            return
        if result == "reset":
            self._apply_settings(SETTINGS_DEFAULTS)

    def _apply_settings(self, new_settings: PeopleSettings) -> None:
        self.settings = new_settings
        self._persist_settings(new_settings)
        self._refresh_list()

    def _persist_settings(self, settings: PeopleSettings) -> None:
        try:
            from owa_people.config import (  # type: ignore[import]  # noqa: PLC0415
                load_config,
                save_config,
            )

            config = load_config()
            config.update(to_config_dict(settings))
            save_config(config)
        except Exception:
            pass

    def action_quit(self) -> None:
        self.app.pop_screen()

    # ------------------------------------------------------------------
    # PeopleList event handlers
    # ------------------------------------------------------------------

    def on_people_list_item_selected(self, event: PeopleList.ItemSelected) -> None:
        self._selected_person = event.person
        sorted_people = self._sorted_people()
        if event.person in sorted_people:
            self.selected = sorted_people.index(event.person)
        else:
            self.selected = 0

        # Auto-populate detail pane on selection change (when pane visible)
        if self.settings.detail_pane != "off":
            person_id = event.person.get("id") or ""
            if person_id and person_id in self._detail_cache:
                self._show_cached_detail(person_id)

    def on_people_list_item_activated(self, event: PeopleList.ItemActivated) -> None:
        self._selected_person = event.person
        person_id = event.person.get("id") or ""
        if not person_id:
            return
        if person_id in self._detail_cache:
            self._show_cached_detail(person_id)
        else:
            self._fetch_detail(person_id)

    # ------------------------------------------------------------------
    # Reactives
    # ------------------------------------------------------------------

    def watch_selected(self, value: int) -> None:
        pl = self._people_list()
        if pl is not None and pl.index != value:
            pl.index = value

    def watch_status(self, value: str) -> None:
        try:
            self.query_one("#status-bar", StatusBar).update(value)
        except Exception:
            pass

    def watch_settings(self, value: PeopleSettings) -> None:
        self._refresh_list()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _people_list(self) -> PeopleList | None:
        try:
            return self.query_one("#people-list", PeopleList)
        except Exception:
            return None

    def _current_person(self) -> dict | None:
        pl = self._people_list()
        if pl is not None:
            return pl.current_person()
        return self._selected_person

    def _refresh_list(self) -> None:
        """Rebuild the people list from current people + settings."""
        pl = self._people_list()
        if pl is None:
            return
        sorted_people = self._sorted_people()
        pl.update_people(sorted_people, self.settings)


# ---------------------------------------------------------------------------
# Layout helpers (inner container widgets)
# ---------------------------------------------------------------------------


class _LayoutRight(Horizontal):
    """Horizontal layout: PeopleList left, DetailPane right."""

    def __init__(self, ratio: int, people_list: PeopleList, detail: DetailPane) -> None:
        super().__init__(id="people-layout")
        self._ratio = ratio
        self._people_list = people_list
        self._detail = detail

    def compose(self) -> ComposeResult:
        self._people_list.styles.width = f"{self._ratio}%"
        self._detail.styles.width = f"{100 - self._ratio}%"
        yield self._people_list
        yield self._detail


class _LayoutBottom(Vertical):
    """Vertical layout: PeopleList top, DetailPane bottom."""

    def __init__(self, ratio: int, people_list: PeopleList, detail: DetailPane) -> None:
        super().__init__(id="people-layout")
        self._ratio = ratio
        self._people_list = people_list
        self._detail = detail

    def compose(self) -> ComposeResult:
        self._people_list.styles.height = f"{self._ratio}%"
        self._detail.styles.height = f"{100 - self._ratio}%"
        yield self._people_list
        yield self._detail


class _LayoutOff(Horizontal):
    """Single-pane layout: only the PeopleList (no DetailPane)."""

    def __init__(self, people_list: PeopleList) -> None:
        super().__init__(id="people-layout")
        self._people_list = people_list

    def compose(self) -> ComposeResult:
        yield self._people_list
