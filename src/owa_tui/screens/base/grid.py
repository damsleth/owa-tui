"""grid.py — OwaGridScreen: generic 2-D matrix base built on Textual DataTable.

Parallel to OwaListScreen (flat list + detail) but for read-only tabular data
where the natural representation is rows × columns, not a drill-down list.
Examples: free/busy schedules, test-run matrices, availability grids.

Subclass the two abstract hooks::

    async def fetch_grid(self, search: str = "") -> GridData:
        # Return (column_labels, [(row_label, [cell, ...]), ...])
        ...

    def cell_style(self, row_label: str, col_label: str, value: str) -> str | None:
        # Return a Rich markup style string ("bold green", "red", …) or None.
        ...

Everything else — worker, status reactive, SettingsOverlay, fixtures seam,
token minting seam — follows the OwaListScreen conventions exactly.

Layout
------
    ┌─────────────────────────────────────────┐
    │  Label  (breadcrumb / title)            │
    │  DataTable  (fills remaining height)    │
    │  StatusBar  (1 line, muted)             │
    └─────────────────────────────────────────┘

Bindings
--------
    j / down      cursor_down  (DataTable native + action wrapper)
    k / up        cursor_up
    h / left      cursor_left
    l / right     cursor_right
    enter         show_detail (selected cell → status footer)
    r             refresh (re-run fetch_grid)
    escape        open SettingsOverlay menu
    q             quit (pop screen)

No search, no drill-down — grids are read-only matrices; ``enter`` surfaces the
selected cell's detail in the status footer.
"""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import DataTable, Label

from owa_tui.widgets.status_bar import StatusBar

# Type alias: (column_labels, [(row_label, [cell_text, ...]), ...])
GridData = tuple[list[str], list[tuple[str, list[str]]]]

# ---------------------------------------------------------------------------
# Bindings
# ---------------------------------------------------------------------------

GRID_BINDINGS: list[Binding] = [
    # navigation — arrows are handled natively by DataTable; j/k/h/l are wired
    # to action_cursor_* wrappers so they call DataTable.action_scroll_* methods.
    Binding("j", "cursor_down", "Down", show=False),
    Binding("down", "cursor_down", "Down", show=False),
    Binding("k", "cursor_up", "Up", show=False),
    Binding("up", "cursor_up", "Up", show=False),
    Binding("h", "cursor_left", "Left", show=False),
    Binding("left", "cursor_left", "Left", show=False),
    Binding("l", "cursor_right", "Right", show=False),
    Binding("right", "cursor_right", "Right", show=False),
    # cell detail
    Binding("enter", "show_detail", "Detail"),
    # universal actions
    Binding("r", "refresh", "Refresh"),
    Binding("escape", "open_menu", "Menu"),
    Binding("q", "quit", "Quit"),
]


# ---------------------------------------------------------------------------
# OwaGridScreen
# ---------------------------------------------------------------------------


class OwaGridScreen(Screen):
    """Generic 2-D matrix screen base built on Textual's DataTable.

    Parameters
    ----------
    config : dict | None
        Auth / tool config dict (passed to ``access_token_for``).
        POSITIONAL callers must pass as a keyword to avoid the bug that hit
        DriveScreen — always use ``config=cfg``, never a bare positional arg.
    tool_name : str
        owa-tools tool key (e.g. ``"owa-sched"``).  Also used as the fixture
        key: ``fixtures.load(tool_name)``.
    audience : str
        Token audience passed to ``access_token_for`` (e.g. ``"graph"``).
    title : str
        Screen title shown in the breadcrumb label.
    cursor_type : str
        DataTable cursor type: ``"cell"`` (default) or ``"row"``.
    debug : bool
        Enable verbose adapter logging.
    """

    BINDINGS = GRID_BINDINGS  # type: ignore[assignment]

    # Reactive status drives the StatusBar widget (mirroring OwaListScreen)
    _status: reactive[str] = reactive("")

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        tool_name: str = "owa-grid",
        audience: str = "graph",
        title: str = "",
        cursor_type: str = "cell",
        debug: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config: dict[str, Any] = config or {}
        self._tool_name = tool_name
        self._audience = audience
        self._screen_title = title or tool_name
        self._cursor_type = cursor_type
        self._debug = debug
        # Raw (unstyled) grid data kept so the cursor cell can be resolved for
        # action_show_detail. Populated by _apply_grid.
        self._col_labels: list[str] = []
        self._rows: list[tuple[str, list[str]]] = []

    # -------------------------------------------------------------------------
    # Abstract hooks — subclass MUST implement
    # -------------------------------------------------------------------------

    @abstractmethod
    async def fetch_grid(self, search: str = "") -> GridData:
        """Fetch grid data.  Runs inside a @work thread — do NOT touch UI here.

        Return
        ------
        (column_labels, rows) where rows is a list of (row_label, [cell, ...]).
        Raise on unrecoverable error; return ([], []) for empty results.

        Fixture seam
        ------------
        In your implementation, short-circuit with fixture data when present::

            from owa_tui import fixtures
            raw = fixtures.load(self._tool_name)
            if raw is not None:
                return _parse_grid(raw)          # build GridData from fixture
            # else: live fetch via access_token_for(...)
        """
        raise NotImplementedError(f"{type(self).__name__} must implement fetch_grid()")

    @abstractmethod
    def cell_style(
        self, row_label: str, col_label: str, value: str
    ) -> str | None:
        """Return a Rich markup style string for a cell, or None for plain text.

        Examples: ``"bold green"``, ``"red"``, ``"dim"``, ``None``.
        Called for every cell when the DataTable is populated, so keep it fast.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement cell_style()"
        )

    # -------------------------------------------------------------------------
    # Optional overridable hooks
    # -------------------------------------------------------------------------

    def menu_config(self) -> tuple[str, list[tuple[str, str]]]:
        """Return (overlay_title, settings_fields) for the Esc overlay.

        Override to add tool-specific settings.  Default returns an empty list
        (no Settings sub-menu, just Resume / Help / Quit).
        """
        return (f"{self._screen_title} — settings", [])

    def handle_menu_result(self, result: str) -> None:
        """Called when the SettingsOverlay is dismissed.

        ``result`` is ``"resume"``, ``"quit"``, ``"help"``, or a
        ``"cycle:<field>"`` string if settings_fields were added.
        Override to react to tool-specific results; call super() for defaults.
        """
        if result == "quit":
            self.app.pop_screen()
        elif result == "help":
            self._status = "j/k/h/l move  r refresh  Esc menu  q quit"
        # "resume" and cycle:* are silently ignored by default

    # -------------------------------------------------------------------------
    # Composition
    # -------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Label(self._screen_title, id="owa-grid-breadcrumb")
        tbl: DataTable[str] = DataTable(
            id="owa-grid-table",
            cursor_type=self._cursor_type,  # type: ignore[arg-type]
            show_cursor=True,
        )
        yield tbl
        yield StatusBar(id="owa-status-bar")

    def on_mount(self) -> None:
        self.title = self._screen_title
        self._fetch_grid()

    # -------------------------------------------------------------------------
    # Reactive watcher — status → StatusBar (same pattern as OwaListScreen)
    # -------------------------------------------------------------------------

    def watch__status(self, value: str) -> None:
        try:
            self.query_one("#owa-status-bar", StatusBar).update(value)
        except Exception:  # widget not yet mounted
            pass

    # -------------------------------------------------------------------------
    # Fetch worker — @work thread, main-thread DataTable update via call_from_thread
    # -------------------------------------------------------------------------

    @work(thread=True)
    def _fetch_grid(self, search: str = "") -> None:
        """Worker: call fetch_grid(), then populate the DataTable on the main thread.

        Mirrors OwaListScreen._load_items() exactly:
          - sets "_status" to "Loading…" before the async call
          - catches all exceptions → "error: …" status, never raises
          - posts _apply_grid to the main thread via call_from_thread
        """
        self.app.call_from_thread(
            lambda: setattr(self, "_status", "Loading…")
        )
        try:
            col_labels, rows = asyncio.run(self.fetch_grid(search))
        except Exception as exc:
            err = str(exc)
            self.app.call_from_thread(
                lambda: setattr(self, "_status", f"error: {err}")
            )
            return
        self.app.call_from_thread(self._apply_grid, col_labels, rows)

    def _apply_grid(
        self,
        col_labels: list[str],
        rows: list[tuple[str, list[str]]],
    ) -> None:
        """Main-thread: clear DataTable and repopulate with new data.

        Called exclusively from _fetch_grid via call_from_thread, so it runs
        on the Textual event loop thread and may safely touch widgets.

        Layout: the first column is always the row label ("") — unlabelled so
        it reads as a header stub — followed by one column per col_label.
        """
        # Keep raw data for action_show_detail (cursor → cell lookup).
        self._col_labels = col_labels
        self._rows = rows

        tbl = self.query_one("#owa-grid-table", DataTable)
        tbl.clear(columns=True)

        if not col_labels:
            self._status = "(no data)"
            return

        # Add row-label stub column + one column per data column
        tbl.add_column("", key="_row_label")
        for cl in col_labels:
            tbl.add_column(cl, key=cl)

        if not rows:
            self._status = "0 rows"
            return

        for row_label, cells in rows:
            styled: list[str] = []
            for cl, val in zip(col_labels, cells):
                style = self.cell_style(row_label, cl, val)
                if style:
                    styled.append(f"[{style}]{val}[/{style}]")
                else:
                    styled.append(val)
            tbl.add_row(row_label, *styled)

        n_rows = len(rows)
        n_cols = len(col_labels)
        noun = "row" if n_rows == 1 else "rows"
        self._status = f"{n_rows} {noun} × {n_cols} columns"

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_refresh(self) -> None:
        """Re-run the fetch worker (same as pressing r)."""
        self._fetch_grid()

    def action_quit(self) -> None:
        self.app.pop_screen()

    def action_open_menu(self) -> None:
        from owa_tui.widgets.settings_overlay import (  # noqa: PLC0415
            SettingsOverlay,
        )

        overlay_title, settings_fields = self.menu_config()
        overlay = SettingsOverlay(
            title_lines=[overlay_title],
            top_items=[
                ("Resume", "resume"),
                ("Settings", "settings"),
                ("Help", "help"),
                ("Quit", "quit"),
            ],
            settings_fields=settings_fields,
            settings=None,
        )
        self.app.push_screen(overlay, self.handle_menu_result)

    # Cursor-movement wrappers — delegate to DataTable's own actions so that
    # j/k/h/l behave identically to the arrow keys DataTable already handles.

    def action_cursor_down(self) -> None:
        try:
            self.query_one("#owa-grid-table", DataTable).action_scroll_down()
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        try:
            self.query_one("#owa-grid-table", DataTable).action_scroll_up()
        except Exception:
            pass

    def action_cursor_left(self) -> None:
        try:
            self.query_one("#owa-grid-table", DataTable).action_scroll_left()
        except Exception:
            pass

    def action_cursor_right(self) -> None:
        try:
            self.query_one("#owa-grid-table", DataTable).action_scroll_right()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Cell detail (enter)
    # -------------------------------------------------------------------------

    def cell_detail(self, row_label: str, col_label: str, value: str) -> str:
        """Detail string for the selected cell, shown in the status footer.

        Default is ``"<row> · <col>: <value>"`` (or just the row label when the
        cursor is on the row-label stub). Subclasses override for richer text
        (e.g. doctor appends the probe error / minutes remaining).
        """
        if not col_label:
            return row_label
        return f"{row_label} · {col_label}: {value}"

    def _show_cell_detail(self, row: int, column: int) -> None:
        """Resolve a cursor (row, column) to raw data and show its detail."""
        if not (0 <= row < len(self._rows)):
            return
        row_label, cells = self._rows[row]
        if column <= 0:  # the unlabelled row-label stub column
            self._status = self.cell_detail(row_label, "", row_label)
            return
        ci = column - 1
        if ci >= len(self._col_labels):
            return
        value = cells[ci] if ci < len(cells) else ""
        self._status = self.cell_detail(row_label, self._col_labels[ci], value)

    def action_show_detail(self) -> None:
        """Show the detail for the cell under the cursor (fallback for enter)."""
        try:
            coord = self.query_one("#owa-grid-table", DataTable).cursor_coordinate
        except Exception:
            return
        if coord is not None:
            self._show_cell_detail(coord.row, coord.column)

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """DataTable posts this on enter when cursor_type='cell'."""
        self._show_cell_detail(event.coordinate.row, event.coordinate.column)
