"""teams.py — TeamsScreen + TeamsThreadScreen: Microsoft Teams chats TUI.

Two-screen card:
  1. TeamsScreen(OwaListScreen)  — chats list (reuses the proven list base)
  2. TeamsThreadScreen(OwaThreadScreen) — scrollable message thread for a chat

Navigation: selecting a chat in TeamsScreen pushes TeamsThreadScreen with that
chat's id and display name pre-bound.  h / Escape / left pops back to the list.

Auth: Graph API, audience='graph'.  Token minted per-call via
owa_tui.adapter.access_token_for (same pattern as cal/mail/people).
"""

from __future__ import annotations

from typing import Any

from owa_tui.screens.base import OwaListScreen
from owa_tui.screens.base.thread import OwaThreadScreen

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# ---------------------------------------------------------------------------
# Module-level pure helpers
# ---------------------------------------------------------------------------


def _chat_display_name(chat: dict) -> str:
    """Return a human-readable name for a chat dict."""
    topic = chat.get("topic") or ""
    if topic:
        return topic
    members = chat.get("_memberNames") or []
    if members:
        return ", ".join(members[:3]) + (" …" if len(members) > 3 else "")
    return chat.get("id", "(unknown)")[:40]


def _row_text(chat: dict, width: int = 80) -> str:
    """Format a chat for the list row."""
    name = _chat_display_name(chat)
    chat_type = chat.get("chatType") or "chat"
    type_tag = {"oneOnOne": "1:1", "group": "grp", "meeting": "mtg"}.get(chat_type, "?")
    right = f"[{type_tag}]"
    max_name = max(10, width - len(right) - 3)
    if len(name) > max_name:
        name = name[: max_name - 1] + "…"
    gap = max(1, width - len(name) - len(right))
    return f"{name}{' ' * gap}{right}"


def _detail_text(chat: dict) -> str:
    """Render full chat detail for the split pane."""
    lines: list[str] = []
    name = _chat_display_name(chat)
    lines.append(f"[bold]{name}[/bold]")
    lines.append("")

    for key, label in [
        ("chatType", "Type"),
        ("createdDateTime", "Created"),
        ("lastUpdatedDateTime", "Last updated"),
        ("webUrl", "Web URL"),
    ]:
        val = chat.get(key)
        if val:
            lines.append(f"[dim]{label}:[/dim]  {val}")

    members = chat.get("_memberNames") or []
    if members:
        lines.append(f"[dim]Members:[/dim]  {', '.join(members)}")

    return "\n".join(lines)


def _render_message_block(msg: dict) -> str:
    """Render one Teams chat message as a Rich-markup block."""
    from_info = (msg.get("from") or {}).get("user") or {}
    sender = from_info.get("displayName") or from_info.get("id") or "?"
    ts = (msg.get("createdDateTime") or "")[:16].replace("T", " ")
    body_obj = msg.get("body") or {}
    content_type = body_obj.get("contentType") or "text"
    content = body_obj.get("content") or ""

    # Strip HTML for HTML-type messages (very light)
    if content_type == "html":
        import re  # noqa: PLC0415

        content = re.sub(r"<[^>]+>", "", content).strip()

    deleted = msg.get("deletedDateTime")
    if deleted:
        content = "[dim](deleted)[/dim]"

    return f"[bold cyan]{sender}[/bold cyan]  [dim]{ts}[/dim]\n{content}\n[dim]{'─' * 40}[/dim]"


# ---------------------------------------------------------------------------
# TeamsThreadScreen — OwaThreadScreen concrete implementation
# ---------------------------------------------------------------------------


class TeamsThreadScreen(OwaThreadScreen):
    """Message thread for a single Teams chat.

    Push this from TeamsScreen.on_item_activated with the chat dict — it
    binds chat_id and chat_name at construction time and fetches messages
    on mount.

    Parameters
    ----------
    config : dict
        owa-tools config (positional, see OwaThreadScreen).
    chat_id : str
        The Graph chat id (e.g. "19:...@thread.v2").
    chat_name : str
        Display name shown in the breadcrumb label.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        chat_id: str,
        chat_name: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            config,
            tool_name="owa-teams",
            audience="graph",
            title=chat_name or "Teams thread",
            breadcrumb=chat_name or chat_id,
            **kwargs,
        )
        self._chat_id = chat_id
        self._chat_name = chat_name

    async def fetch_messages(self) -> list[dict]:
        """Fetch messages for this chat from the Graph API.

        Short-circuits to the fixture layer when ``OWA_TUI_FIXTURES`` is set.
        Fixture resolution order (first hit wins):

        1. ``teams_<slug>.json``    where slug = re.sub(r"[^a-zA-Z0-9]+", "_", chat_id).strip("_")
        2. ``teams_messages.json``  generic fallback for any chat
        3. Live Graph call          when no fixture files are present
        """
        import re  # noqa: PLC0415

        from owa_tui import fixtures  # noqa: PLC0415

        # --- Fixture seam (e2e / offline mode) ---
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", self._chat_id).strip("_")
        raw = fixtures.load(f"teams_{slug}")
        if raw is None:
            raw = fixtures.load("teams_messages")

        # --- Live Graph fetch ---
        if raw is None:
            from owa_tui.adapter import access_token_for  # noqa: PLC0415

            token = access_token_for(
                self._config, tool_name=self._tool_name, audience=self._audience
            )
            import httpx  # noqa: PLC0415

            headers = {"Authorization": f"Bearer {token}"}
            url: str | None = f"{GRAPH_BASE}/me/chats/{self._chat_id}/messages"
            pages: list[dict] = []
            async with httpx.AsyncClient(timeout=20) as client:
                while url:
                    resp = client.get(url, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    pages.extend(data.get("value", []))
                    url = data.get("@odata.nextLink")
            raw = {"value": pages}

        messages: list[dict] = list(raw.get("value") or [])
        # Reverse so oldest-first (Graph returns newest-first by default).
        return list(reversed(messages))

    def render_message(self, msg: dict) -> str:
        return _render_message_block(msg)


# ---------------------------------------------------------------------------
# TeamsScreen — OwaListScreen for the chats list
# ---------------------------------------------------------------------------


class TeamsScreen(OwaListScreen):
    """Microsoft Teams chats list.

    Selecting a chat pushes TeamsThreadScreen for that chat's messages.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        tool_name: str = "owa-teams",
        audience: str = "graph",
        title: str = "Teams",
        **kwargs: Any,
    ) -> None:
        # config is keyword-only in OwaListScreen; pass it explicitly
        super().__init__(
            config=config,
            tool_name=tool_name,
            audience=audience,
            title=title,
            detail_pane_mode="right",
            split_ratio=45,
            search_prompt="Filter chats:",
            search_placeholder="chat name or topic…",
            empty_label="(no chats)",
            **kwargs,
        )

    # -------------------------------------------------------------------------
    # Abstract hook: fetch_items
    # -------------------------------------------------------------------------

    async def fetch_items(self, search: str = "") -> list[dict]:
        """Fetch Teams chats from the Graph API, optionally filtered by *search*.

        Short-circuits to the fixture layer when ``OWA_TUI_FIXTURES`` is set.
        Fixture file: ``teams.json`` — raw Graph ``/me/chats?$expand=members``
        payload (``{"value": [...chats...]}``) with ``_memberNames`` pre-populated
        or derivable from ``members``.
        """
        from owa_tui import fixtures  # noqa: PLC0415

        # --- Fixture seam (e2e / offline mode) ---
        raw = fixtures.load("teams")

        # --- Live Graph fetch ---
        if raw is None:
            from owa_tui.adapter import access_token_for  # noqa: PLC0415

            token = access_token_for(
                self._config, tool_name=self._tool_name, audience=self._audience
            )
            import httpx  # noqa: PLC0415

            headers = {"Authorization": f"Bearer {token}"}
            url: str | None = f"{GRAPH_BASE}/me/chats?$expand=members&$top=50"
            pages: list[dict] = []
            async with httpx.AsyncClient(timeout=20) as client:
                while url:
                    resp = client.get(url, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    pages.extend(data.get("value", []))
                    url = data.get("@odata.nextLink")
            raw = {"value": pages}

        chats: list[dict] = list(raw.get("value") or [])

        # Annotate member names for display helpers (idempotent if already set).
        for chat in chats:
            if "_memberNames" not in chat:
                members = chat.get("members") or []
                chat["_memberNames"] = [
                    (m.get("displayName") or m.get("userId") or "?") for m in members
                ]

        if search:
            sl = search.lower()
            chats = [c for c in chats if sl in _chat_display_name(c).lower()]

        return chats

    # -------------------------------------------------------------------------
    # Abstract hook: render_row
    # -------------------------------------------------------------------------

    def render_row(self, item: dict, width: int) -> str:
        return _row_text(item, width)

    # -------------------------------------------------------------------------
    # Abstract hook: render_detail
    # -------------------------------------------------------------------------

    def render_detail(self, item: dict) -> str:
        return _detail_text(item)

    # -------------------------------------------------------------------------
    # Optional hook: open_browser_for — chats carry a webUrl
    # -------------------------------------------------------------------------

    def open_browser_for(self, item: dict) -> str | None:
        return item.get("webUrl") or None

    # -------------------------------------------------------------------------
    # Abstract hook: menu_config
    # -------------------------------------------------------------------------

    def menu_config(self) -> tuple[str, list[tuple[str, str]]]:
        return ("Teams — settings", [])

    # -------------------------------------------------------------------------
    # Optional hook: on_item_activated — push the thread screen
    # -------------------------------------------------------------------------

    def on_item_activated(self, chat: dict) -> None:
        """Open the selected chat's message thread."""
        chat_id = chat.get("id", "")
        chat_name = _chat_display_name(chat)
        thread = TeamsThreadScreen(
            self._config,
            chat_id=chat_id,
            chat_name=chat_name,
        )
        self.app.push_screen(thread)

    # -------------------------------------------------------------------------
    # Optional hook: sort_items
    # -------------------------------------------------------------------------

    def sort_items(self, chats: list[dict]) -> list[dict]:
        """Sort chats newest-first by lastUpdatedDateTime."""
        return sorted(
            chats,
            key=lambda c: c.get("lastUpdatedDateTime") or "",
            reverse=True,
        )

    def help_text(self) -> str:
        return "j/k move  Enter open thread  / filter  r refresh  q quit"
