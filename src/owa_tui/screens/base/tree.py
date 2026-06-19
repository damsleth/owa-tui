"""tree.py — OwaTreeScreen: hierarchical drill-down on top of OwaListScreen.

Adds a node stack to OwaListScreen so tools can present folder-trees
(e.g. drive folders, planner plans/buckets) with the same list/detail/
search/menu/nav UX.

Subclass ``OwaTreeScreen`` and implement the three abstract hooks::

    async def load_node(self, node: TreeNode, search: str) -> list[dict]:
        ...

    def is_container(self, item: dict) -> bool:
        ...

    def child_node(self, item: dict) -> TreeNode:
        ...

Plus the OwaListScreen hooks: ``render_row``, ``render_detail``,
``menu_config``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from owa_tui.screens.base.screen import OwaListScreen

# ---------------------------------------------------------------------------
# TreeNode data class
# ---------------------------------------------------------------------------


@dataclass
class TreeNode:
    """A node in the tree hierarchy.

    Parameters
    ----------
    id:
        Opaque identifier passed to ``load_node`` so the tool can fetch
        children (e.g. a folder id, a drive id, a plan id).
    label:
        Human-readable label shown in the breadcrumb title.
    meta:
        Arbitrary tool-specific payload; not interpreted by OwaTreeScreen.
    """

    id: str
    label: str
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# OwaTreeScreen
# ---------------------------------------------------------------------------


class OwaTreeScreen(OwaListScreen):
    """OwaListScreen extended with hierarchical drill-down.

    Parameters
    ----------
    root_node:
        The root ``TreeNode``.  Its ``load_node`` call populates the first
        list view.
    **kw:
        All other keyword arguments are forwarded to ``OwaListScreen``.
    """

    def __init__(self, *, root_node: TreeNode, **kw: Any) -> None:
        super().__init__(**kw)
        self._node_stack: list[TreeNode] = [root_node]

    # ------------------------------------------------------------------
    # Abstract hooks — tools MUST override all three
    # ------------------------------------------------------------------

    async def load_node(self, node: TreeNode, search: str) -> list[dict]:
        """Return children of *node* filtered by *search*.  Required."""
        raise NotImplementedError

    def is_container(self, item: dict) -> bool:
        """Return True if *item* is a folder (drill-in), False if a leaf."""
        raise NotImplementedError

    def child_node(self, item: dict) -> TreeNode:
        """Convert a container *item* into the ``TreeNode`` to push."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # OwaListScreen overrides
    # ------------------------------------------------------------------

    async def fetch_items(self, search: str) -> list[dict]:
        """Delegate to ``load_node`` for the current top-of-stack node."""
        node = self._node_stack[-1]
        return await self.load_node(node, search)

    def on_item_activated(self, item: dict) -> None:
        """Drill into a container or show detail for a leaf."""
        if self.is_container(item):
            node = self.child_node(item)
            self._node_stack.append(node)
            self._update_title()
            self._load_items(search="")   # reset search on drill
        else:
            self._show_detail(item)

    def action_close_detail(self) -> None:
        """Tree-aware back/up.

        * If a detail pane is open  → close it (restore list mode).
        * Elif stack depth > 1      → pop node and reload the parent.
        * Else                      → no-op (at root, no detail open).
        """
        if self._mode == "detail":
            # Close detail pane — inline the base logic so we do NOT also pop.
            if self._detail_pane_mode != "off":
                lw = self._list_widget()
                if lw is not None:
                    lw.focus()
                self._mode = "list"
        elif len(self._node_stack) > 1:
            self._node_stack.pop()
            self._update_title()
            self._load_items(search="")   # reload parent, reset search
        # else: at root with no detail open — no-op

    def _apply_items(self, items: list[dict], search: str) -> None:
        """Call the base then refresh the breadcrumb title."""
        super()._apply_items(items, search)  # type: ignore[misc]
        self._update_title()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_title(self) -> None:
        """Write the breadcrumb path into ``self.title``."""
        parts = [n.label for n in self._node_stack]
        self.title = " > ".join(parts) if parts else self._screen_title
