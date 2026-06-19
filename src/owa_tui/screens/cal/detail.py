"""DetailPane for cal screen — renders event detail with rich formatting."""

from __future__ import annotations

import textwrap
from typing import Any

from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.widgets import Static

# ---------------------------------------------------------------------------
# Response label mapping (ported verbatim from owa_cal.tui)
# ---------------------------------------------------------------------------

_RESPONSE_LABEL: dict[str, str] = {
    "accepted": "accepted",
    "declined": "declined",
    "tentativelyaccepted": "tentative",
    "tentative": "tentative",
    "notresponded": "no reply",
    "none": "no reply",
    "organizer": "organizer",
}

_MAX_ATTENDEES = 12


def _response_label(resp: str) -> str:
    """Normalise a raw Graph response string to a display label."""
    return _RESPONSE_LABEL.get(resp.lower(), resp.lower())


def _attendee_line(att: Any, width: int) -> str:
    """Format a single attendee (dict or bare string) as a display line."""
    if isinstance(att, dict):
        name: str = att.get("name") or att.get("address") or ""
        resp = _response_label(att.get("response") or att.get("status") or "none")
        att_type: str = att.get("type") or ""
        opt = " (optional)" if att_type.lower() in ("optional", "optional attendee") else ""
        return f"  {name} — {resp}{opt}"
    return f"  {att}"


def render_detail(event: dict[str, Any], width: int, *, detail: str = "full") -> list[str]:
    """Render an event as a list of display strings.

    Ported verbatim from ``owa_cal.tui.render_detail``.

    Parameters
    ----------
    event:
        Normalised event dict (output of ``normalize_events_detail``).
    width:
        Terminal column width used for wrapping and underline.
    detail:
        ``'full'`` shows all fields; ``'basic'`` omits attendees, organizer,
        body, and own response.
    """
    if width < 1:
        width = 1

    lines: list[str] = []

    subject: str = event.get("subject") or ""
    start: str = event.get("start") or ""
    end: str = event.get("end") or ""
    location: str = event.get("location") or ""
    show_as: str = event.get("showAs") or ""
    categories: list = event.get("categories") or []
    is_all_day: bool = bool(event.get("isAllDay"))
    organizer: str = event.get("organizer") or ""
    attendees: list = event.get("attendees") or []
    body: str = event.get("body") or event.get("bodyPreview") or ""
    response: str = event.get("response") or event.get("responseStatus") or ""
    is_organizer: bool = bool(event.get("isOrganizer"))

    # Subject + underline
    lines.append(subject)
    underline_len = min(len(subject), width)
    lines.append("─" * underline_len)

    # When
    if is_all_day:
        when_date = start[:10] if start else ""
        lines.append(f"When:      all-day  {when_date}")
    else:
        s_time = start[11:16] if len(start) >= 16 else start
        e_time = end[11:16] if len(end) >= 16 else end
        lines.append(f"When:      {s_time} – {e_time}")

    # Location
    if location:
        lines.append(f"Location:  {location}")

    # Status (showAs)
    if show_as:
        lines.append(f"Status:    {show_as}")

    # Category
    if categories:
        lines.append(f"Category:  {', '.join(str(c) for c in categories)}")

    if detail == "full":
        # Response / organizer flag
        if is_organizer:
            lines.append("Response:  organizer")
        elif response:
            lines.append(f"Response:  {_response_label(response)}")

        # Organizer
        if organizer:
            lines.append(f"Organizer: {organizer}")

        # Attendees
        if attendees:
            lines.append("")
            lines.append(f"Attendees ({len(attendees)}):")
            shown = attendees[:_MAX_ATTENDEES]
            overflow = len(attendees) - len(shown)
            for att in shown:
                lines.append(_attendee_line(att, width))
            if overflow > 0:
                lines.append(f"  … +{overflow} more")

        # Body / note
        if body:
            lines.append("")
            lines.append("Note:")
            wrap_width = max(1, width - 2)
            for raw_line in body.splitlines():
                if raw_line.strip() == "":
                    lines.append("")
                else:
                    wrapped = textwrap.wrap(raw_line, wrap_width) or [""]
                    lines.extend(wrapped)

    return lines


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------


class CalDetailPane(ScrollableContainer):
    """Scrollable event detail pane for the cal screen.

    Content is refreshed via :meth:`update_event`.
    """

    DEFAULT_CSS = """
    CalDetailPane {
        overflow-y: scroll;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="cal-detail-content")

    def update_event(self, event: dict[str, Any] | None, detail_level: str = "full") -> None:
        """Re-render the pane for *event* at *detail_level*."""
        if event is None:
            self.query_one("#cal-detail-content", Static).update("")
            return
        width = self.size.width or 60
        lines = render_detail(event, width, detail=detail_level)
        self.query_one("#cal-detail-content", Static).update("\n".join(lines))

    def clear(self) -> None:
        self.query_one("#cal-detail-content", Static).update("")
