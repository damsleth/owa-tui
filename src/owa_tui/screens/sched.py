"""sched.py — SchedScreen: free/busy scheduling grid via Microsoft Graph.

First production consumer of OwaGridScreen — shows a time-slot × attendee
matrix with colour-coded availability pulled from Graph's getSchedule endpoint.

Grid shape
----------
  columns = time slots across the window (60-min slots, next workday)
  rows    = one row per attendee (scheduleId)
  cells   = decoded availabilityView digit → status string

Cell styles
-----------
  free             → green
  tentative        → yellow
  busy             → red
  oof              → dark_orange
  workingElsewhere → cyan
  error            → dim red
  unknown          → dim

Fixture seam
------------
Set ``OWA_TUI_FIXTURES=<dir>`` and place ``sched.json`` (the raw Graph
``{"value": [...]}`` response) in that directory.  ``fetch_grid`` returns from
the fixture before making any API call.

Live path
---------
Posts to ``me/calendar/getSchedule`` on Graph (audience="graph") using the
``owa_sched.api.api_post`` helper and normalizes each entry with
``owa_sched.schedule.normalize_attendee``.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

from textual.binding import Binding

from owa_tui.screens.base.grid import GRID_BINDINGS, GridData, OwaGridScreen

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_SLOT_MINUTES = 60
_DEFAULT_WORK_START = "08:00"
_DEFAULT_WORK_END = "17:00"
_DEFAULT_TZ = "W. Europe Standard Time"

# Attendees shown when no config is supplied (demo / fixture mode)
_DEMO_ATTENDEES = [
    "alice@contoso.com",
    "bob@contoso.com",
    "carol@contoso.com",
]

# Map Graph availabilityView digits to display strings
_DIGIT_STATUS: dict[str, str] = {
    "0": "free",
    "1": "tentative",
    "2": "busy",
    "3": "oof",
    "4": "workingElsewhere",
}

# Rich markup styles per status
_CELL_STYLE: dict[str, str] = {
    "free": "green",
    "tentative": "yellow",
    "busy": "red",
    "oof": "dark_orange",
    "workingElsewhere": "cyan",
    "error": "dim red",
    "unknown": "dim",
}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _next_workday() -> str:
    """Return the ISO date string of the next workday (Mon-Fri) from today."""
    d = date.today() + timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d += timedelta(days=1)
    return d.isoformat()


def _parse_grid(raw: dict) -> GridData:
    """Convert a raw Graph getSchedule ``{"value": [...]}`` dict to GridData.

    Uses ``availabilityView`` (one digit per slot) as the authoritative source
    for cell values — no overlap arithmetic needed.
    """
    from owa_sched.schedule import normalize_attendee  # type: ignore[import]

    entries = raw.get("value") or []
    if not entries:
        return [], []

    # All attendees share the same slot window; take column count from first.
    first_av = (entries[0].get("availabilityView") or "")
    n_slots = len(first_av)
    if n_slots == 0:
        return [], []

    # Column labels: derive from slot index given work start + slot duration.
    # We use a simple HH:MM sequence rather than calling slots_in_window so that
    # _parse_grid works without a config dict (fixture path & unit tests).
    try:
        start_h, start_m = map(int, _DEFAULT_WORK_START.split(":"))
    except ValueError:
        start_h, start_m = 8, 0

    col_labels: list[str] = []
    total_minutes = start_h * 60 + start_m
    for _ in range(n_slots):
        h, m = divmod(total_minutes, 60)
        col_labels.append(f"{h:02d}:{m:02d}")
        total_minutes += _SLOT_MINUTES

    rows: list[tuple[str, list[str]]] = []
    for entry in entries:
        attendee = normalize_attendee(entry)
        email = attendee["email"] or entry.get("scheduleId") or "?"
        if attendee.get("error"):
            # Entire row is an error
            cells: list[str] = ["error"] * n_slots
        else:
            av = attendee["availabilityView"]
            cells = []
            for i in range(n_slots):
                if i < len(av):
                    cells.append(_DIGIT_STATUS.get(av[i], "unknown"))
                else:
                    cells.append("free")
        rows.append((email, cells))

    return col_labels, rows


# ---------------------------------------------------------------------------
# SchedScreen
# ---------------------------------------------------------------------------


class SchedScreen(OwaGridScreen):
    """Free/busy scheduling grid — first consumer of OwaGridScreen.

    Parameters
    ----------
    config : dict | None
        owa-tools config dict (keyword-only — see OwaGridScreen docstring).
    attendees : list[str] | None
        Email addresses to query.  Defaults to ``_DEMO_ATTENDEES`` when
        ``None`` so the screen renders meaningfully in fixture/demo mode.
    work_start : str
        HH:MM start of the work window (default "08:00").
    work_end : str
        HH:MM end of the work window (default "17:00").
    timezone : str
        IANA / Windows timezone name for the Graph request body.
    """

    BINDINGS = GRID_BINDINGS + [  # type: ignore[assignment]
        Binding("a", "add_attendee", "Add attendee"),
    ]

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        attendees: list[str] | None = None,
        work_start: str = _DEFAULT_WORK_START,
        work_end: str = _DEFAULT_WORK_END,
        timezone: str = _DEFAULT_TZ,
        **kwargs: Any,
    ) -> None:
        cfg = config or {}
        super().__init__(
            config=cfg,
            tool_name="sched",
            audience="graph",
            title="Scheduling",
            cursor_type="cell",
            **kwargs,
        )
        self._attendees: list[str] = attendees or _DEMO_ATTENDEES
        self._work_start: str = cfg.get("default_work_start") or work_start
        self._work_end: str = cfg.get("default_work_end") or work_end
        self._timezone: str = cfg.get("default_timezone") or timezone

    # -------------------------------------------------------------------------
    # Abstract hook: fetch_grid
    # -------------------------------------------------------------------------

    async def fetch_grid(self, search: str = "") -> GridData:
        """Fetch free/busy grid from Graph getSchedule.

        Short-circuits to fixture data when ``OWA_TUI_FIXTURES`` is set and
        ``sched.json`` exists in that directory.
        """
        from owa_tui import fixtures  # noqa: PLC0415

        raw = fixtures.load(self._tool_name)
        if raw is not None:
            return _parse_grid(raw)

        # --- live path ---
        from owa_sched.api import api_post  # type: ignore[import]  # noqa: PLC0415
        from owa_sched.dates import make_local_iso  # type: ignore[import]  # noqa: PLC0415

        from owa_tui.adapter import access_token_for  # noqa: PLC0415

        token = access_token_for(
            self._config, tool_name="owa-sched", audience=self._audience
        )

        target_date = _next_workday()
        body = {
            "schedules": self._attendees,
            "startTime": {
                "dateTime": make_local_iso(target_date, self._work_start),
                "timeZone": self._timezone,
            },
            "endTime": {
                "dateTime": make_local_iso(target_date, self._work_end),
                "timeZone": self._timezone,
            },
            "availabilityViewInterval": _SLOT_MINUTES,
        }

        payload = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: api_post(
                _GRAPH_BASE,
                "me/calendar/getSchedule",
                token,
                body=body,
                debug=self._debug,
            ),
        )

        if payload is None:
            return [], []

        return _parse_grid(payload)

    # -------------------------------------------------------------------------
    # Abstract hook: cell_style
    # -------------------------------------------------------------------------

    def cell_style(self, row_label: str, col_label: str, value: str) -> str | None:
        """Return a Rich markup style string for a scheduling cell."""
        return _CELL_STYLE.get(value)

    # -------------------------------------------------------------------------
    # Optional overrides
    # -------------------------------------------------------------------------

    def menu_config(self) -> tuple[str, list[tuple[str, str]]]:
        return ("Scheduling — settings", [])

    # -------------------------------------------------------------------------
    # Add attendee (a) — prompt, append, re-fetch the grid
    # -------------------------------------------------------------------------

    def action_add_attendee(self) -> None:
        from owa_tui.screens.base.screen import _SearchModal  # noqa: PLC0415

        def _on_result(value: str | None) -> None:
            email = (value or "").strip()
            if not email:
                return
            self._attendees.append(email)
            self._status = f"added {email} — refreshing…"
            self._fetch_grid()

        self.app.push_screen(
            _SearchModal("Add attendee:", "email address…"), _on_result
        )
