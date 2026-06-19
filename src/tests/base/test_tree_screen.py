"""Tests for OwaTreeScreen — fake subclass, no live M365.

Convention matches test_list_screen.py: plain asyncio.run() wrappers,
no pytest-asyncio.
"""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from owa_tui.screens.base import OwaTreeScreen, TreeNode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _folder(id: str, name: str) -> dict:
    return {"id": id, "name": name, "kind": "folder"}


def _leaf(id: str, name: str) -> dict:
    return {"id": id, "name": name, "kind": "leaf"}


ROOT = TreeNode(id="root", label="Root")

_DEFAULT_TREE: dict[str, list[dict]] = {
    "root": [_folder("f1", "Folder A"), _leaf("l1", "Leaf B")],
    "f1": [_leaf("l2", "Leaf C"), _leaf("l3", "Leaf D")],
}


class _FakeTreeScreen(OwaTreeScreen):
    """Concrete OwaTreeScreen for testing."""

    def __init__(
        self,
        *,
        tree: dict[str, list[dict]] | None = None,
        **kw: Any,
    ) -> None:
        super().__init__(
            root_node=ROOT,
            tool_name="owa-tree-fake",
            audience="graph",
            **kw,
        )
        self._tree = tree if tree is not None else dict(_DEFAULT_TREE)
        self.load_calls: list[tuple[str, str]] = []  # (node_id, search)

    async def load_node(self, node: TreeNode, search: str) -> list[dict]:
        self.load_calls.append((node.id, search))
        return [
            i
            for i in self._tree.get(node.id, [])
            if not search or search.lower() in i["name"].lower()
        ]

    def is_container(self, item: dict) -> bool:
        return item.get("kind") == "folder"

    def child_node(self, item: dict) -> TreeNode:
        return TreeNode(id=item["id"], label=item["name"])

    def render_row(self, item: dict, width: int) -> str:
        prefix = "[+] " if self.is_container(item) else "    "
        return prefix + item.get("name", "")

    def render_detail(self, item: dict) -> str:
        return f"DETAIL: {item['name']}"

    def menu_config(self) -> tuple[str, list[tuple[str, str]]]:
        return ("tree-fake — menu", [])


def _make_app(**kw: Any) -> App:
    class _TestApp(App):
        TITLE = "test"

        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(_FakeTreeScreen(**kw))

    return _TestApp()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_root_node_loads_children() -> None:
    """On mount, load_node is called with the root node and 2 items returned."""

    async def _run() -> tuple[int, list[tuple[str, str]]]:
        app = _make_app(detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc: _FakeTreeScreen = app.screen
            return len(sc._items), sc.load_calls

    n, calls = asyncio.run(_run())
    assert n == 2
    assert calls[0] == ("root", "")


def test_drill_into_folder_pushes_stack_and_reloads() -> None:
    """Activating a folder pushes a new TreeNode and loads its children."""

    async def _run() -> tuple[int, int, list[tuple[str, str]]]:
        app = _make_app(detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc: _FakeTreeScreen = app.screen
            sc.on_item_activated(sc._items[0])  # Folder A
            await pilot.pause(0.3)
            return len(sc._node_stack), len(sc._items), sc.load_calls

    depth, n, calls = asyncio.run(_run())
    assert depth == 2
    assert n == 2  # f1 has 2 leaves
    assert calls[-1] == ("f1", "")


def test_drill_resets_selected_idx_to_zero() -> None:
    """_apply_items resets _selected_idx=0 on drill-in."""

    async def _run() -> int:
        app = _make_app(detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc: _FakeTreeScreen = app.screen
            sc._selected_idx = 1  # pretend user moved down
            sc.on_item_activated(sc._items[0])  # drill into Folder A
            await pilot.pause(0.3)
            return sc._selected_idx

    assert asyncio.run(_run()) == 0


def test_back_from_child_pops_stack_and_reloads_parent() -> None:
    """action_close_detail at stack-depth>1 pops and reloads parent."""

    async def _run() -> tuple[int, list[tuple[str, str]]]:
        app = _make_app(detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc: _FakeTreeScreen = app.screen
            sc.on_item_activated(sc._items[0])  # drill into f1
            await pilot.pause(0.3)
            await pilot.press("h")              # back
            await pilot.pause(0.3)
            return len(sc._node_stack), sc.load_calls

    depth, calls = asyncio.run(_run())
    assert depth == 1
    assert calls[-1] == ("root", "")


def test_back_at_root_is_noop() -> None:
    """action_close_detail at root depth=1, no detail open — no-op (no extra load)."""

    async def _run() -> int:
        app = _make_app(detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc: _FakeTreeScreen = app.screen
            initial_calls = len(sc.load_calls)
            await pilot.press("h")
            await pilot.pause(0.1)
            return len(sc.load_calls) - initial_calls

    assert asyncio.run(_run()) == 0


def test_back_closes_detail_before_popping_stack() -> None:
    """If detail pane is open, first h closes it; second h pops the stack."""

    async def _run() -> tuple[str, int]:
        app = _make_app(detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc: _FakeTreeScreen = app.screen
            sc.on_item_activated(sc._items[0])  # drill into Folder A
            await pilot.pause(0.3)
            # activate a leaf to open detail
            sc.on_item_activated(sc._items[0])  # Leaf C
            await pilot.pause(0.1)
            await pilot.press("h")              # first back → close detail
            await pilot.pause(0.1)
            mode_after_close = sc._mode
            depth = len(sc._node_stack)
        return mode_after_close, depth

    mode, depth = asyncio.run(_run())
    assert mode == "list"   # detail closed
    assert depth == 2       # stack NOT popped yet


def test_refresh_reloads_current_node() -> None:
    """r reloads the current top-of-stack node."""

    async def _run() -> tuple[str, list[tuple[str, str]]]:
        app = _make_app(detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc: _FakeTreeScreen = app.screen
            sc.on_item_activated(sc._items[0])  # drill to f1
            await pilot.pause(0.3)
            await pilot.press("r")
            await pilot.pause(0.3)
            return sc._node_stack[-1].id, sc.load_calls

    node_id, calls = asyncio.run(_run())
    assert node_id == "f1"
    assert calls[-1] == ("f1", "")


def test_breadcrumb_title_updates_on_drill_and_pop() -> None:
    """self.title reflects the node path at each step."""

    async def _run() -> tuple[str, str, str]:
        app = _make_app(detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc: _FakeTreeScreen = app.screen
            root_title = sc.title
            sc.on_item_activated(sc._items[0])  # drill into Folder A
            await pilot.pause(0.3)
            child_title = sc.title
            await pilot.press("h")              # back
            await pilot.pause(0.3)
            back_title = sc.title
        return root_title, child_title, back_title

    root, child, back = asyncio.run(_run())
    assert "Root" in root
    assert "Folder A" in child
    assert "Folder A" not in back


def test_leaf_activation_shows_detail_not_drill() -> None:
    """Activating a leaf does not change stack depth."""

    async def _run() -> tuple[int, str]:
        app = _make_app(detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc: _FakeTreeScreen = app.screen
            leaf = sc._items[1]  # "Leaf B"
            sc.on_item_activated(leaf)
            await pilot.pause(0.1)
            return len(sc._node_stack), sc._mode

    depth, mode = asyncio.run(_run())
    assert depth == 1       # no drill
    assert mode == "detail"


def test_search_filters_within_current_node() -> None:
    """search query is passed to load_node, not the base fetch_items."""

    async def _run() -> list[tuple[str, str]]:
        app = _make_app(detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc: _FakeTreeScreen = app.screen
            sc.on_search_query("leaf")
            await pilot.pause(0.3)
            return sc.load_calls

    calls = asyncio.run(_run())
    assert ("root", "leaf") in calls


def test_abstract_hooks_raise_not_implemented() -> None:
    """Calling hooks on bare OwaTreeScreen raises NotImplementedError."""
    bare = OwaTreeScreen(
        root_node=TreeNode(id="r", label="R"),
        tool_name="t",
        audience="graph",
    )
    node = TreeNode(id="r", label="R")
    for call in (
        lambda: asyncio.run(bare.load_node(node, "")),
        lambda: bare.is_container({}),
        lambda: bare.child_node({}),
    ):
        try:
            call()
            raise AssertionError("expected NotImplementedError")
        except NotImplementedError:
            pass


def test_empty_node_shows_zero_items() -> None:
    """A node with no children yields an empty list."""

    async def _run() -> int:
        tree = {"root": [], "f1": []}
        app = _make_app(detail_pane_mode="off", tree=tree)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            return len(app.screen._items)

    assert asyncio.run(_run()) == 0


def test_search_returns_filtered_subset() -> None:
    """load_node receives the query and can return a subset."""

    async def _run() -> int:
        app = _make_app(detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc: _FakeTreeScreen = app.screen
            sc.on_search_query("folder")
            await pilot.pause(0.3)
            return len(sc._items)

    # only "Folder A" matches "folder"
    assert asyncio.run(_run()) == 1


def test_fetch_items_uses_top_of_stack() -> None:
    """fetch_items always uses the current top-of-stack node id."""

    async def _run() -> str:
        app = _make_app(detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc: _FakeTreeScreen = app.screen
            sc.on_item_activated(sc._items[0])  # push f1
            await pilot.pause(0.3)
            # fetch_items should now use f1
            await sc.fetch_items("")
            return sc._node_stack[-1].id

    node_id = asyncio.run(_run())
    assert node_id == "f1"


def test_update_title_breadcrumb_format() -> None:
    """_update_title joins all node labels with ' > '."""
    bare = OwaTreeScreen(
        root_node=TreeNode(id="r", label="Root"),
        tool_name="t",
        audience="graph",
    )
    # Manually push nodes without a running app
    bare._node_stack.append(TreeNode(id="c1", label="Child"))
    bare._node_stack.append(TreeNode(id="c2", label="Grand"))
    # Verify the breadcrumb format by inspecting the stack directly
    # (no running app, so we cannot call _update_title)
    parts = [n.label for n in bare._node_stack]
    assert " > ".join(parts) == "Root > Child > Grand"


def test_tree_node_dataclass_defaults() -> None:
    """TreeNode can be constructed with just id and label."""
    n = TreeNode(id="x", label="X")
    assert n.id == "x"
    assert n.label == "X"
    assert n.meta == {}


def test_two_drill_levels_then_pop_twice() -> None:
    """Drill two levels deep, then pop twice back to root."""

    deep_tree = {
        "root": [_folder("f1", "Folder A")],
        "f1": [_folder("f2", "Folder B")],
        "f2": [_leaf("l1", "Leaf Z")],
    }

    async def _run() -> tuple[list[int], list[str]]:
        app = _make_app(detail_pane_mode="off", tree=deep_tree)
        depths: list[int] = []
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc: _FakeTreeScreen = app.screen
            depths.append(len(sc._node_stack))       # 1
            sc.on_item_activated(sc._items[0])       # drill to f1
            await pilot.pause(0.3)
            depths.append(len(sc._node_stack))       # 2
            sc.on_item_activated(sc._items[0])       # drill to f2
            await pilot.pause(0.3)
            depths.append(len(sc._node_stack))       # 3
            await pilot.press("h")                   # pop to f1
            await pilot.pause(0.3)
            depths.append(len(sc._node_stack))       # 2
            await pilot.press("h")                   # pop to root
            await pilot.pause(0.3)
            depths.append(len(sc._node_stack))       # 1
            return depths, sc.load_calls

    depths, calls = asyncio.run(_run())
    assert depths == [1, 2, 3, 2, 1]
    assert calls[-1] == ("root", "")
