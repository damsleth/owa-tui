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

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Static

from owa_tui.screens.base.keys import LIST_BINDINGS
from owa_tui.screens.base.screen import OwaListScreen, _DetailPane, _OwaList

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
# Miller-column layout (parent | current | detail)
# ---------------------------------------------------------------------------


class _ParentPane(Static):
    DEFAULT_CSS = """
    _ParentPane {
        padding: 0 1;
        border-right: solid $border;
    }
    """


class _LayoutColumns(Horizontal):
    """Three fixed panes.

    ponytail: lf shows N ancestor columns; one parent column is the ceiling
    here — the node stack has the data if anyone ever wants more.
    """

    def __init__(self, parent: _ParentPane, list_widget: _OwaList, detail: _DetailPane) -> None:
        super().__init__(id="owa-list-layout")
        self._pw = parent
        self._lw = list_widget
        self._dw = detail

    def compose(self) -> ComposeResult:
        yield self._pw
        yield self._lw
        yield self._dw


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

    ``COLUMN_VIEW`` (class attribute) selects the initial layout when
    ``detail_pane_mode == "right"``: lf-style columns (parent folder | current
    folder | detail) when True, the plain list + detail split when False.
    ``c`` toggles at runtime.
    """

    COLUMN_VIEW = False
    BINDINGS = LIST_BINDINGS + [  # type: ignore[assignment]
        Binding("c", "toggle_columns", "Columns", show=False),
    ]

    def __init__(self, *, root_node: TreeNode, **kw: Any) -> None:
        super().__init__(**kw)
        self._node_stack: list[TreeNode] = [root_node]
        # Parallel to _node_stack[1:]: (parent listing, item drilled into).
        self._items_stack: list[tuple[list[dict], dict]] = []
        self._column_view = self.COLUMN_VIEW

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
            self._items_stack.append((list(self._items), item))
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
            if self._items_stack:
                self._items_stack.pop()
            self._update_title()
            self._load_items(search="")   # reload parent, reset search
        # else: at root with no detail open — no-op

    def _apply_items(self, items: list[dict], search: str) -> None:
        """Call the base then refresh the breadcrumb title."""
        super()._apply_items(items, search)  # type: ignore[misc]
        self._update_title()
        self._refresh_parent_pane()

    def _build_layout(self) -> Any:
        if self._detail_pane_mode != "right":
            return super()._build_layout()
        list_widget = _OwaList(
            self.sort_items(self._items),
            self.render_row,
            empty_label=self._empty_label,
            id="owa-item-list",
        )
        return _LayoutColumns(
            _ParentPane("", id="owa-parent-pane", markup=False),
            list_widget,
            _DetailPane(id="owa-detail-pane"),
        )

    def on_mount(self) -> None:
        super().on_mount()
        self._apply_column_layout()

    def action_toggle_columns(self) -> None:
        self._column_view = not self._column_view
        self._apply_column_layout()
        self._refresh_parent_pane()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_title(self) -> None:
        """Write the breadcrumb path into ``self.title``."""
        parts = [n.label for n in self._node_stack]
        self.title = " > ".join(parts) if parts else self._screen_title

    def _parent_pane(self) -> _ParentPane | None:
        try:
            return self.query_one("#owa-parent-pane", _ParentPane)
        except Exception:
            return None

    def _apply_column_layout(self) -> None:
        """Show/hide the parent column and set the three pane widths."""
        pane, lw, dw = self._parent_pane(), self._list_widget(), self._detail_pane()
        if pane is None or lw is None or dw is None:
            return
        pane.display = self._column_view
        if self._column_view:
            pane.styles.width, lw.styles.width, dw.styles.width = "20%", "45%", "35%"
        else:
            lw.styles.width = f"{self._split_ratio}%"
            dw.styles.width = f"{100 - self._split_ratio}%"

    def _refresh_parent_pane(self) -> None:
        """Render the parent listing with the current folder marked."""
        pane = self._parent_pane()
        if pane is None or not self._column_view:
            return
        if not self._items_stack:
            pane.update("")
            return
        parent_items, active = self._items_stack[-1]
        width = max(10, (pane.size.width or 24) - 6)
        pane.update(
            "\n".join(
                ("> " if item is active else "  ") + self.render_row(item, width)
                for item in parent_items
            )
        )
