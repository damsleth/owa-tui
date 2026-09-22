"""doctor.py — DoctorScreen: auth-health grid via owa-doctor local probes.

Second production consumer of OwaGridScreen — shows a profiles × audiences
matrix where each cell reflects the token health for that (profile, audience)
pair as reported by the local owa-piggy auth broker.

Grid shape
----------
  rows    = profiles (aliases) from owa_core.auth.get_profiles()
  columns = registered tools (SCREEN_REGISTRY order); each maps to the
            owa-piggy audience its screen mints via _TOOL_AUDIENCE
  cells   = classify_finding() result: "ok" | "warn" | "fail", or
            "disabled" for a profile owa-piggy reports as not registered

Cell styles
-----------
  ok       → green
  warn     → yellow
  fail     → bold red
  disabled → dim

Fixture seam
------------
Set ``OWA_TUI_FIXTURES=<dir>`` and place ``doctor.json`` (a JSON list of
findings dicts) in that directory.  ``fetch_grid`` returns from the fixture
before making any probe call.  The REAL ``classify_finding`` is still applied
to fixture data so the classify logic is exercised.

Live path
---------
Calls ``owa_core.auth.get_profiles()`` to enumerate profiles (keeping the
``registered`` flag so disabled profiles are shown as such, not probed), then
``probe_profile_token(alias, audience)`` ONCE per distinct (alias, audience)
pair and fans the classified result out to every tool column sharing that
audience.  All probes run in the executor thread (they are blocking
subprocess/socket calls) so the event loop is never blocked.
"""

from __future__ import annotations

import asyncio
from typing import Any

from owa_tui.screens.base.grid import GridData, OwaGridScreen

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Tool key (SCREEN_REGISTRY) -> owa-piggy audience the screen mints tokens for.
# Mirrors the ``audience=`` each screen passes to access_token_for; keep in sync.
_TOOL_AUDIENCE: dict[str, str] = {
    "cal": "outlook",
    "mail": "outlook",
    "people": "graph",
    "todo": "outlook",
    "planner": "graph",
    "ado": "devops",
    "drive": "graph",
    "sites": "graph",
    "sched": "graph",
    "teams": "graph",
    "graph": "graph",
}

# Rich markup styles for probe result cells.
_RESULT_STYLE: dict[str, str] = {
    "ok": "green",
    "warn": "yellow",
    "fail": "bold red",
    "disabled": "dim",
}

# Cell value / finding error for a profile owa-piggy reports as not registered.
_DISABLED = "disabled"
_DISABLED_ERROR = "profile not registered in owa-piggy"


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _classify(finding: dict) -> str:
    """classify_finding, with a "disabled" short-circuit for unregistered profiles."""
    from owa_doctor.probe import classify_finding  # noqa: PLC0415

    if finding.get(_DISABLED):
        return _DISABLED
    return classify_finding(finding)


def _parse_grid(
    findings: list[dict],
    columns: list[tuple[str, str]] | None = None,
) -> GridData:
    """Pivot a flat list of probe findings into a profiles x columns GridData.

    Parameters
    ----------
    findings:
        List of finding dicts as returned by ``probe_profile_token`` (or loaded
        from ``doctor.json``).  Expected keys: ``alias``, ``audience``,
        ``token_ok``, ``minutes_remaining``.
    columns:
        Optional ``[(label, audience), ...]``.  When given, one column per
        entry (tools sharing an audience share the finding).  When omitted,
        columns are the distinct audiences in insertion order (fixture mode).

    Returns
    -------
    (column_labels, [(row_label, [cell_text, ...]), ...])

    The REAL ``classify_finding`` is applied to each finding so the classify
    logic is exercised even in fixture mode.
    """
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
        lookup[key] = _classify(f)

    if columns is None:
        columns = [(aud, aud) for aud in audiences]

    rows: list[tuple[str, list[str]]] = []
    for alias in profiles:
        cells = [lookup.get((alias, aud), "fail") for _label, aud in columns]
        rows.append((alias, cells))

    return [label for label, _aud in columns], rows


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
        # (alias, audience) -> finding dict, for cell_detail. Filled by fetch_grid.
        self._findings: dict[tuple[str, str], dict] = {}
        # column label (tool) -> audience, so cell_detail can find the finding.
        self._col_audience: dict[str, str] = {}

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
            self._index_findings(raw)
            return _parse_grid(raw)

        # --- live path: one token probe per (profile, audience) via owa-piggy ---
        from owa_core.auth import get_profiles  # noqa: PLC0415
        from owa_doctor.probe import probe_profile_token  # noqa: PLC0415

        from owa_tui.screens import registered_tools  # noqa: PLC0415

        columns = [(k, _TOOL_AUDIENCE[k]) for k, _ in registered_tools() if k in _TOOL_AUDIENCE]
        audiences = list(dict.fromkeys(aud for _k, aud in columns))
        self._col_audience = dict(columns)

        def _run_probes() -> list[dict]:
            results: list[dict] = []
            for profile in get_profiles(tool_name="owa-doctor"):
                for audience in audiences:
                    if profile.registered:
                        results.append(probe_profile_token(profile.alias, audience=audience))
                    else:
                        results.append({
                            "alias": profile.alias,
                            "audience": audience,
                            "token_ok": False,
                            _DISABLED: True,
                            "error": _DISABLED_ERROR,
                        })
            return results

        findings = await asyncio.get_event_loop().run_in_executor(None, _run_probes)

        if not findings:
            return [], []

        self._index_findings(findings)
        return _parse_grid(findings, columns)

    def _index_findings(self, findings: list[dict]) -> None:
        """Build the (alias, audience) -> finding lookup for cell_detail."""
        self._findings = {
            (f.get("alias", "?"), f.get("audience", "?")): f for f in findings
        }

    # -------------------------------------------------------------------------
    # Abstract hook: cell_style
    # -------------------------------------------------------------------------

    def cell_style(self, row_label: str, col_label: str, value: str) -> str | None:
        """Return a Rich markup style string for a health-check cell."""
        return _RESULT_STYLE.get(value)

    def cell_detail(self, row_label: str, col_label: str, value: str) -> str:
        """Append the probe error / token lifetime to the base cell detail."""
        base = super().cell_detail(row_label, col_label, value)
        f = self._findings.get((row_label, self._col_audience.get(col_label, col_label)))
        if not f:
            return base
        err = f.get("error")
        if err:
            return f"{base} — {err}"
        mins = f.get("minutes_remaining")
        if mins is not None:
            return f"{base} — {mins} min left"
        return base

    # -------------------------------------------------------------------------
    # Optional overrides
    # -------------------------------------------------------------------------

    def menu_config(self) -> tuple[str, list[tuple[str, str]]]:
        return ("Diagnostics — settings", [])
