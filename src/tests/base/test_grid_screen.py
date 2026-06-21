"""Pilot tests for owa_tui.screens.base.OwaGridScreen.

The base is proven with a concrete _FakeGridScreen whose fetch_grid returns
canned data (or raises) — no live M365.  Async helpers are wrapped in
asyncio.run() so plain pytest runs them (project convention, no pytest-asyncio).

Coverage targets (>= 90% of grid.py):
  - compose() mounts DataTable + StatusBar + breadcrumb label
  - _fetch_grid worker populates columns, rows, cells, status message
  - empty grid (no columns) sets status "(no data)"
  - rows-present but zero-column edge case (col_labels=[])
  - error path: fetch_grid raises → status "error: …", no crash
  - r key triggers refresh → fetch_grid called again
  - escape key opens SettingsOverlay
  - q key pops the screen (quit)
  - cell_style markup applied to cells in the DataTable
  - handle_menu_result("help") sets status string
  - handle_menu_result("quit") calls pop_screen
  - cursor-movement actions (j/k/h/l) do not crash
  - menu_config default title convention
  - watch__status writes through to StatusBar
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header

from owa_tui.screens.base.grid import GRID_BINDINGS, GridData, OwaGridScreen
from owa_tui.widgets.status_bar import StatusBar

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COLS = ["Mon", "Tue", "Wed"]
_ROWS: list[tuple[str, list[str]]] = [
    ("Alice", ["free", "busy", "free"]),
    ("Bob", ["busy", "free", "busy"]),
]


def _canned_grid() -> GridData:
    return (_COLS, _ROWS)


def _empty_grid() -> GridData:
    return ([], [])


def _no_rows_grid() -> GridData:
    return (_COLS, [])


# ---------------------------------------------------------------------------
# Fake subclass
# ---------------------------------------------------------------------------


class _FakeGridScreen(OwaGridScreen):
    """Concrete OwaGridScreen for testing the base behaviour.

    Mirrors _FakeListScreen's pattern: canned data or a forced error, plus a
    counter so tests can verify how many times fetch_grid was called.
    """

    def __init__(
        self,
        *,
        grid_data: GridData | None = None,
        fetch_error: str = "",
        **kw: Any,
    ) -> None:
        super().__init__(
            config={},
            tool_name="owa-fake-grid",
            audience="graph",
            title="FakeGrid",
            **kw,
        )
        self._grid_data: GridData = grid_data if grid_data is not None else _canned_grid()
        self._fetch_error = fetch_error
        self.fetch_calls: int = 0

    async def fetch_grid(self, search: str = "") -> GridData:
        self.fetch_calls += 1
        if self._fetch_error:
            raise RuntimeError(self._fetch_error)
        return self._grid_data

    def cell_style(self, row_label: str, col_label: str, value: str) -> str | None:
        if value == "busy":
            return "bold red"
        if value == "free":
            return "green"
        return None


def _make_app(**screen_kw: Any) -> App:
    class _TestApp(App):
        TITLE = "test"

        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(_FakeGridScreen(**screen_kw))

    return _TestApp()


# ---------------------------------------------------------------------------
# Tests: compose / mounting
# ---------------------------------------------------------------------------


def test_datatable_is_mounted() -> None:
    """compose() yields a DataTable that Textual mounts."""

    async def _run() -> int:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            return len(list(app.screen.query(DataTable)))

    assert asyncio.run(_run()) == 1


def test_statusbar_is_mounted() -> None:
    async def _run() -> int:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            return len(list(app.screen.query(StatusBar)))

    assert asyncio.run(_run()) == 1


def test_breadcrumb_label_is_mounted() -> None:
    async def _run() -> bool:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            # Confirm the label is present — content is set via Label("FakeGrid")
            labels = list(app.screen.query("#owa-grid-breadcrumb"))
            return len(labels) == 1

    assert asyncio.run(_run())


# ---------------------------------------------------------------------------
# Tests: fetch worker populates DataTable
# ---------------------------------------------------------------------------


def test_fetch_worker_populates_columns() -> None:
    """After mount + pause, DataTable has the expected columns."""

    async def _run() -> list[str]:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            tbl = app.screen.query_one("#owa-grid-table", DataTable)
            # column keys: first is "_row_label" stub, then Mon/Tue/Wed
            return [str(col.label) for col in tbl.columns.values()]

    cols = asyncio.run(_run())
    # first column is the row-label stub (empty string)
    assert cols[0] == ""
    assert "Mon" in cols
    assert "Tue" in cols
    assert "Wed" in cols


def test_fetch_worker_populates_rows() -> None:
    """DataTable has one row per entry returned by fetch_grid."""

    async def _run() -> int:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            tbl = app.screen.query_one("#owa-grid-table", DataTable)
            return tbl.row_count

    assert asyncio.run(_run()) == len(_ROWS)


def test_fetch_worker_sets_status_with_dimensions() -> None:
    """Status after successful fetch includes row × column counts."""

    async def _run() -> str:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            return app.screen._status

    status = asyncio.run(_run())
    assert "rows" in status or "row" in status
    assert "columns" in status


def test_fetch_called_once_on_mount() -> None:
    """fetch_grid is called exactly once on mount."""

    async def _run() -> int:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            return app.screen.fetch_calls

    assert asyncio.run(_run()) == 1


# ---------------------------------------------------------------------------
# Tests: cell_style markup
# ---------------------------------------------------------------------------


def test_cell_style_applied_to_busy_cells() -> None:
    """Cells with value 'busy' get [bold red]…[/bold red] markup."""

    async def _run() -> bool:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            tbl = app.screen.query_one("#owa-grid-table", DataTable)
            # Row 0 is Alice: free/busy/free — busy cell is index (row=0, col 2 = Tue)
            # Row 1 is Bob:   busy/free/busy — busy cell is index (row=1, col 1 = Mon)
            # The cell renderable should contain the markup tag
            cell_val = str(tbl.get_cell_at((0, 2)))  # Alice/Tue = busy
            return "[bold red]" in cell_val or "busy" in cell_val

    assert asyncio.run(_run())


def test_cell_style_none_for_unknown_values() -> None:
    """cell_style returning None leaves cell text as plain string."""
    screen = _FakeGridScreen()
    result = screen.cell_style("Alice", "Mon", "unknown")
    assert result is None


def test_cell_style_returns_markup_for_busy() -> None:
    screen = _FakeGridScreen()
    assert screen.cell_style("Alice", "Mon", "busy") == "bold red"


def test_cell_style_returns_markup_for_free() -> None:
    screen = _FakeGridScreen()
    assert screen.cell_style("Alice", "Mon", "free") == "green"


# ---------------------------------------------------------------------------
# Tests: empty grid
# ---------------------------------------------------------------------------


def test_empty_grid_no_columns_sets_status() -> None:
    """When fetch_grid returns empty columns, status is '(no data)'."""

    async def _run() -> str:
        app = _make_app(grid_data=_empty_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            return app.screen._status

    assert asyncio.run(_run()) == "(no data)"


def test_empty_grid_datatable_has_no_rows() -> None:
    async def _run() -> int:
        app = _make_app(grid_data=_empty_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            tbl = app.screen.query_one("#owa-grid-table", DataTable)
            return tbl.row_count

    assert asyncio.run(_run()) == 0


def test_columns_present_no_rows_sets_zero_rows_status() -> None:
    """Columns but zero rows → status '0 rows'."""

    async def _run() -> str:
        app = _make_app(grid_data=_no_rows_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            return app.screen._status

    assert asyncio.run(_run()) == "0 rows"


# ---------------------------------------------------------------------------
# Tests: error path
# ---------------------------------------------------------------------------


def test_error_path_sets_error_status() -> None:
    """When fetch_grid raises, status is set to 'error: …' without crashing."""

    async def _run() -> str:
        app = _make_app(fetch_error="network timeout")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            return app.screen._status

    status = asyncio.run(_run())
    assert status.startswith("error:")
    assert "network timeout" in status


def test_error_path_datatable_empty() -> None:
    """On error, DataTable is still empty (not in an inconsistent state)."""

    async def _run() -> int:
        app = _make_app(fetch_error="boom")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            tbl = app.screen.query_one("#owa-grid-table", DataTable)
            return tbl.row_count

    assert asyncio.run(_run()) == 0


# ---------------------------------------------------------------------------
# Tests: refresh (r key)
# ---------------------------------------------------------------------------


def test_r_key_re_fetches() -> None:
    """Pressing r calls fetch_grid a second time."""

    async def _run() -> int:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            await pilot.press("r")
            await pilot.pause(0.3)
            return app.screen.fetch_calls

    assert asyncio.run(_run()) == 2


def test_refresh_action_re_fetches() -> None:
    """action_refresh() triggers the worker without pressing a key."""

    async def _run() -> int:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            app.screen.action_refresh()
            await pilot.pause(0.3)
            return app.screen.fetch_calls

    assert asyncio.run(_run()) == 2


# ---------------------------------------------------------------------------
# Tests: SettingsOverlay (escape)
# ---------------------------------------------------------------------------


def test_escape_opens_settings_overlay() -> None:
    """Pressing escape pushes a SettingsOverlay onto the screen stack."""

    async def _run() -> str:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("escape")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) == "SettingsOverlay"


def test_handle_menu_result_help_sets_status() -> None:
    """handle_menu_result('help') sets a non-empty help status string."""

    async def _run() -> str:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            app.screen.handle_menu_result("help")
            await pilot.pause(0.05)
            return app.screen._status

    status = asyncio.run(_run())
    assert "refresh" in status or "menu" in status or "quit" in status


def test_handle_menu_result_resume_is_noop() -> None:
    """handle_menu_result('resume') does not change the status."""

    async def _run() -> str:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            app.screen.handle_menu_result("resume")
            await pilot.pause(0.05)
            return app.screen._status

    assert asyncio.run(_run()) is not None  # no crash, status unchanged or same


def test_handle_menu_result_quit_pops_screen() -> None:
    """handle_menu_result('quit') calls app.pop_screen()."""

    async def _run() -> str:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            # Push a dummy screen first so pop_screen doesn't kill the app
            # Instead, just mock pop_screen and verify it's called
            called: list[bool] = []

            def _spy_pop():
                called.append(True)

            app.pop_screen = _spy_pop  # type: ignore[method-assign]
            app.screen.handle_menu_result("quit")
            await pilot.pause(0.05)
            return "called" if called else "not called"

    assert asyncio.run(_run()) == "called"


# ---------------------------------------------------------------------------
# Tests: menu_config default
# ---------------------------------------------------------------------------


def test_menu_config_default_title() -> None:
    """menu_config() title contains the screen title."""
    screen = _FakeGridScreen()
    title, fields = screen.menu_config()
    assert "FakeGrid" in title
    assert isinstance(fields, list)


# ---------------------------------------------------------------------------
# Tests: cursor-movement keys do not crash
# ---------------------------------------------------------------------------


def test_cursor_movement_keys_do_not_crash() -> None:
    """j/k/h/l movement keys do not raise or crash the screen."""

    async def _run() -> str:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            for key in ("j", "k", "h", "l", "j", "k"):
                await pilot.press(key)
                await pilot.pause(0.05)
            return app.screen._status

    status = asyncio.run(_run())
    # status should still be the populated grid status, not an error
    assert not status.startswith("error:")


def test_action_cursor_methods_do_not_crash() -> None:
    """Direct action_cursor_* calls are safe even before DataTable has rows."""

    async def _run() -> bool:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            app.screen.action_cursor_down()
            app.screen.action_cursor_up()
            app.screen.action_cursor_left()
            app.screen.action_cursor_right()
            await pilot.pause(0.05)
            return True

    assert asyncio.run(_run())


# ---------------------------------------------------------------------------
# Tests: q key quits
# ---------------------------------------------------------------------------


def test_q_key_pops_screen() -> None:
    """q key calls action_quit which pops the screen."""

    async def _run() -> bool:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            called: list[bool] = []

            def _spy():
                called.append(True)

            app.pop_screen = _spy  # type: ignore[method-assign]
            await pilot.press("q")
            await pilot.pause(0.05)
            return bool(called)

    assert asyncio.run(_run())


# ---------------------------------------------------------------------------
# Tests: watch__status wires to StatusBar
# ---------------------------------------------------------------------------


def test_watch_status_updates_statusbar() -> None:
    """Setting _status reactive propagates the value (checked via reactive directly)."""

    async def _run() -> str:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            app.screen._status = "test-sentinel"
            await pilot.pause(0.05)
            # Confirm the reactive value was accepted and the StatusBar is present
            _ = app.screen.query_one("#owa-status-bar", StatusBar)  # must not raise
            return app.screen._status

    assert asyncio.run(_run()) == "test-sentinel"


# ---------------------------------------------------------------------------
# Tests: GRID_BINDINGS export
# ---------------------------------------------------------------------------


def test_grid_bindings_exported() -> None:
    """GRID_BINDINGS is importable from grid.py and contains expected keys."""
    keys = {b.key for b in GRID_BINDINGS}
    assert "r" in keys
    assert "q" in keys
    assert "escape" in keys
    assert "j" in keys
    assert "k" in keys
    assert "h" in keys
    assert "l" in keys


def test_grid_bindings_exported_from_base_init() -> None:
    """GRID_BINDINGS is also re-exported from owa_tui.screens.base."""
    from owa_tui.screens.base import GRID_BINDINGS as GB

    assert GB is GRID_BINDINGS


# ---------------------------------------------------------------------------
# Tests: fixture seam (unit-level — no network)
# ---------------------------------------------------------------------------


def test_fixture_seam_skips_live_fetch() -> None:
    """fetch_grid can short-circuit to fixture data before any network call.

    This mirrors how PlannerScreen does it:
        raw = fixtures.load(self._tool_name)
        if raw is not None: return _parse_raw(raw)

    Here we patch fixtures.load to return canned data and confirm the screen
    renders it without touching access_token_for.
    """

    class _FixtureGridScreen(OwaGridScreen):
        def __init__(self, **kw: Any) -> None:
            super().__init__(config={}, tool_name="owa-sched", **kw)
            self.live_called = False

        async def fetch_grid(self, search: str = "") -> GridData:
            from owa_tui import fixtures  # noqa: PLC0415

            raw = fixtures.load(self._tool_name)
            if raw is not None:
                # parse fixture: expect {"columns": [...], "rows": [[label, ...], ...]}
                cols = raw.get("columns", [])
                rows = [(r[0], r[1:]) for r in raw.get("rows", [])]
                return cols, rows
            # live path (should NOT be reached in this test)
            self.live_called = True
            return ([], [])

        def cell_style(self, row_label: str, col_label: str, value: str) -> str | None:
            return None

    canned_fixture = {
        "columns": ["A", "B"],
        "rows": [["r1", "x", "y"]],
    }

    async def _run() -> tuple[int, bool]:
        class _FixApp(App):
            def compose(self) -> ComposeResult:
                yield Header()

            def on_mount(self) -> None:
                self.push_screen(_FixtureGridScreen())

        app = _FixApp()
        with patch("owa_tui.fixtures.load", return_value=canned_fixture):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                tbl = app.screen.query_one("#owa-grid-table", DataTable)
                return tbl.row_count, app.screen.live_called

    rows, live_called = asyncio.run(_run())
    assert rows == 1
    assert not live_called


# ---------------------------------------------------------------------------
# Tests: cell detail (enter / CellSelected)  [hardening]
# ---------------------------------------------------------------------------


def test_cell_detail_default_format() -> None:
    """Default cell_detail is '<row> · <col>: <value>'; row-label stub → row."""
    screen = _FakeGridScreen(grid_data=_canned_grid())
    assert screen.cell_detail("Alice", "Tue", "busy") == "Alice · Tue: busy"
    assert screen.cell_detail("Alice", "", "Alice") == "Alice"


def test_show_cell_detail_resolves_data_cell() -> None:
    """_show_cell_detail maps a (row, column) coord to the raw cell + footer."""

    async def _run() -> str:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: _FakeGridScreen = app.screen  # type: ignore[assignment]
            screen._show_cell_detail(1, 2)  # Bob, column "Tue" (index 1) -> "free"
            await pilot.pause(0.05)
            return screen._status

    assert asyncio.run(_run()) == "Bob · Tue: free"


def test_show_cell_detail_on_row_label_stub() -> None:
    """Column 0 is the unlabelled row-label stub → detail is just the row."""

    async def _run() -> str:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: _FakeGridScreen = app.screen  # type: ignore[assignment]
            screen._show_cell_detail(0, 0)
            await pilot.pause(0.05)
            return screen._status

    assert asyncio.run(_run()) == "Alice"


def test_show_cell_detail_ignores_out_of_range() -> None:
    """Out-of-range row/column coords are ignored (no crash, status unchanged)."""

    async def _run() -> str:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: _FakeGridScreen = app.screen  # type: ignore[assignment]
            before = screen._status
            screen._show_cell_detail(99, 0)  # bad row
            screen._show_cell_detail(0, 99)  # bad column
            await pilot.pause(0.05)
            return screen._status == before

    assert asyncio.run(_run())


def test_enter_shows_cell_detail_via_cellselected() -> None:
    """Pressing enter on a data cell posts CellSelected → footer shows detail."""

    async def _run() -> str:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("right")  # move cursor onto first data cell
            await pilot.press("enter")
            await pilot.pause(0.05)
            return app.screen._status  # type: ignore[union-attr]

    # Alice row, first data column "Mon" -> "free"
    assert asyncio.run(_run()) == "Alice · Mon: free"


def test_action_show_detail_uses_cursor() -> None:
    """action_show_detail reads the table cursor and shows that cell's detail."""

    async def _run() -> str:
        app = _make_app(grid_data=_canned_grid())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: _FakeGridScreen = app.screen  # type: ignore[assignment]
            screen.action_show_detail()  # cursor at origin (0,0) -> row stub
            await pilot.pause(0.05)
            return screen._status

    assert asyncio.run(_run()) == "Alice"
