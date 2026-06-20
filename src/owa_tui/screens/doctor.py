"""doctor.py — DoctorScreen: auth-health grid via owa-doctor local probes.

Second production consumer of OwaGridScreen — shows a profiles × audiences
matrix where each cell reflects the token health for that (profile, audience)
pair as reported by the local owa-piggy auth broker.

Grid shape
----------
  rows    = profiles (aliases) returned by list_piggy_profiles()
  columns = fixed audience set: graph, mail, cal  (or wider if configured)
  cells   = classify_finding() result: "ok" | "warn" | "fail"

Cell styles
-----------
  ok   → green
  warn → yellow
  fail → bold red

Fixture seam
------------
Set ``OWA_TUI_FIXTURES=<dir>`` and place ``doctor.json`` (a JSON list of
findings dicts) in that directory.  ``fetch_grid`` returns from the fixture
before making any probe call.  The REAL ``classify_finding`` is still applied
to fixture data so the classify logic is exercised.

Live path
---------
Calls ``owa_doctor.probe.list_piggy_profiles()`` to enumerate profiles, then
``probe_profile_token(alias, audience)`` for each (alias, audience) pair and
``classify_finding(finding)`` to bucket the result.  All probes run in the
executor thread (they are blocking subprocess/socket calls) so the event loop
is never blocked.
"""

from __future__ import annotations

import asyncio
from typing import Any

from owa_tui.screens.base.grid import GridData, OwaGridScreen

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Audiences checked by default — matches the columns visible in fixture data.
_DEFAULT_AUDIENCES: list[str] = ["graph", "mail", "cal"]

# Rich markup styles for probe result cells.
_RESULT_STYLE: dict[str, str] = {
    "ok": "green",
    "warn": "yellow",
    "fail": "bold red",
}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _parse_grid(findings: list[dict]) -> GridData:
    """Pivot a flat list of probe findings into a profiles x audiences GridData.

    Parameters
    ----------
    findings:
        List of finding dicts as returned by ``probe_profile_token`` (or loaded
        from ``doctor.json``).  Expected keys: ``alias``, ``audience``,
        ``token_ok``, ``minutes_remaining``.

    Returns
    -------
    (column_labels, [(row_label, [cell_text, ...]), ...])

    The REAL ``classify_finding`` is applied to each finding so the classify
    logic is exercised even in fixture mode.
    """
    from owa_doctor.probe import classify_finding  # noqa: PLC0415

    if not findings:
        return [], []

    # Preserve insertion order for both dimensions so the grid matches the
    # order findings appear in the fixture / probe results.
    audiences: list[str] = []
    seen_aud: set[str] = set()
    profiles: list[str] = []
    seen_pro: set[str] = set()
    for f in findings:
        aud = f.get("audience", "?")
        alias = f.get("alias", "?")
        if aud not in seen_aud:
            audiences.append(aud)
            seen_aud.add(aud)
        if alias not in seen_pro:
            profiles.append(alias)
            seen_pro.add(alias)

    # Build lookup: (alias, audience) -> classified cell text
    lookup: dict[tuple[str, str], str] = {}
    for f in findings:
        key = (f.get("alias", "?"), f.get("audience", "?"))
        lookup[key] = classify_finding(f)

    rows: list[tuple[str, list[str]]] = []
    for alias in profiles:
        cells = [lookup.get((alias, aud), "fail") for aud in audiences]
        rows.append((alias, cells))

    return audiences, rows


# ---------------------------------------------------------------------------
# DoctorScreen
# ---------------------------------------------------------------------------


class DoctorScreen(OwaGridScreen):
    """Auth-health diagnostics grid — second consumer of OwaGridScreen.

    Parameters
    ----------
    config : dict | None
        owa-tools config dict (passed positionally by OwaTuiApp.push_tool).
    debug : bool
        Enable verbose probe logging.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        debug: bool = False,
        **kw: Any,
    ) -> None:
        cfg = config or {}
        super().__init__(
            config=cfg,
            tool_name="doctor",
            audience="",           # no token needed — local probes only
            title="Diagnostics",
            cursor_type="cell",
            debug=debug,
            **kw,
        )

    # -------------------------------------------------------------------------
    # Abstract hook: fetch_grid
    # -------------------------------------------------------------------------

    async def fetch_grid(self, search: str = "") -> GridData:
        """Fetch the profiles x audiences health grid.

        Short-circuits to fixture data when ``OWA_TUI_FIXTURES`` is set and
        ``doctor.json`` exists in that directory.  The REAL ``classify_finding``
        is still applied so the classify logic is exercised on fixture data.
        """
        from owa_tui import fixtures  # noqa: PLC0415

        raw = fixtures.load(self._tool_name)
        if raw is not None:
            # raw is a list of findings from doctor.json
            return _parse_grid(raw)

        # --- live path: local probes via owa-piggy, no network/token ---
        from owa_doctor.probe import (  # noqa: PLC0415
            list_piggy_profiles,
            probe_profile_token,
        )

        def _run_probes() -> list[dict]:
            aliases, _default = list_piggy_profiles()
            results: list[dict] = []
            for alias in aliases:
                for audience in _DEFAULT_AUDIENCES:
                    finding = probe_profile_token(alias, audience=audience)
                    results.append(finding)
            return results

        findings = await asyncio.get_event_loop().run_in_executor(None, _run_probes)

        if not findings:
            return [], []

        return _parse_grid(findings)

    # -------------------------------------------------------------------------
    # Abstract hook: cell_style
    # -------------------------------------------------------------------------

    def cell_style(self, row_label: str, col_label: str, value: str) -> str | None:
        """Return a Rich markup style string for a health-check cell."""
        return _RESULT_STYLE.get(value)

    # -------------------------------------------------------------------------
    # Optional overrides
    # -------------------------------------------------------------------------

    def menu_config(self) -> tuple[str, list[tuple[str, str]]]:
        return ("Diagnostics — settings", [])
