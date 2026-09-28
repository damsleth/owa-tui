"""Multi-profile fan-out (owa-tui -A): eligibility, the token override, and merged screens."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import owa_tui
from owa_tui import adapter

FIXTURES = Path(__file__).resolve().parents[3] / "e2e" / "fixtures"
ALL = {"owa_piggy_profiles": ["all"]}


@pytest.fixture
def fixture_mode(monkeypatch):
    monkeypatch.setenv("OWA_TUI_FIXTURES", str(FIXTURES))


def _row(alias, *, registered=True, has_config=True, services=(), type="m365"):
    return SimpleNamespace(
        alias=alias, registered=registered, has_config=has_config, services=services, type=type
    )


def test_eligible_profiles_mirrors_owa_tools_rule(monkeypatch) -> None:
    import owa_core.auth

    rows = [
        _row("nc", services=("owa", "ado")),
        _row("une", services=("owa",)),
        _row("off", registered=False, services=("owa",)),
        _row("bare", has_config=False, services=("owa",)),
        _row("old"),  # older broker: no services, type m365
        _row("g", services=("google",), type="google"),
    ]
    monkeypatch.setattr(owa_core.auth, "get_profiles", lambda **k: rows)
    assert adapter.eligible_profiles(ALL) == ["nc", "une", "old"]
    assert adapter.eligible_profiles(ALL, "ado") == ["nc"]
    # explicit names are kept (and ordered/deduped) even if not eligible
    assert adapter.eligible_profiles({"owa_piggy_profiles": ["une", "all", "g"]}) == [
        "une", "nc", "old", "g",
    ]
    assert adapter.eligible_profiles({}) == []


def test_eligible_profiles_reads_profiles_fixture(fixture_mode) -> None:
    assert adapter.eligible_profiles(ALL) == ["work", "side"]
    assert adapter.eligible_profiles(ALL, "ado") == ["work"]


def test_profile_config_pins_one_profile_and_leaves_merged_mode() -> None:
    cfg = {"owa_piggy_profiles": ["all"], "x": 1}
    assert adapter.profile_config(cfg, {"_profile": "une"}) == {"x": 1, "owa_piggy_profile": "une"}
    assert adapter.profile_config(cfg, "nc")["owa_piggy_profile"] == "nc"
    assert adapter.profile_config(cfg, {"id": "no-profile"}) is cfg
    assert adapter.profile_config(cfg, None) is cfg


def test_fan_out_mints_per_profile_tags_rows_and_never_leaks(monkeypatch) -> None:
    """The override reaches get_token_for_config per profile and is reset afterwards,
    so a pooled worker thread's next fetch isn't minted for the last profile."""
    import owa_core.auth

    def get_token_for_config(config, *, tool_name, audience):
        return f"tok-{config.get('owa_piggy_profile')}"

    monkeypatch.setattr(
        adapter, "eligible_profiles", lambda config, service="owa": ["une", "nc", "bad"]
    )
    with patch.object(
        owa_core.auth, "get_token_for_config", autospec=True, side_effect=get_token_for_config
    ) as mint:

        def fetch():
            tok = adapter.access_token_for({}, tool_name="t", audience="graph")
            if tok == "tok-bad":
                raise RuntimeError("401")
            return [{"tok": tok}]

        rows, errors = adapter.fan_out(ALL, fetch)
        after = adapter.access_token_for({}, tool_name="t", audience="graph")

    assert rows == [{"tok": "tok-une", "_profile": "une"}, {"tok": "tok-nc", "_profile": "nc"}]
    assert errors == ["bad: 401"]
    assert [c.args[0].get("owa_piggy_profile") for c in mint.call_args_list] == [
        "une", "nc", "bad", None,
    ]
    assert after == "tok-None"


def test_fan_out_override_reaches_asyncio_run_and_to_thread(monkeypatch) -> None:
    import owa_core.auth

    monkeypatch.setattr(adapter, "eligible_profiles", lambda config, service="owa": ["a", "b"])
    monkeypatch.setattr(
        owa_core.auth,
        "get_token_for_config",
        lambda config, **k: config.get("owa_piggy_profile"),
    )

    async def fetch_items():
        tok = await asyncio.to_thread(adapter.access_token_for, {}, tool_name="t", audience="g")
        return [{"tok": tok}]

    rows, _ = adapter.fan_out(ALL, lambda: asyncio.run(fetch_items()))
    assert [r["tok"] for r in rows] == ["a", "b"]


@pytest.mark.parametrize(
    "argv, expected",
    [
        ([], None),
        (["--profile", "une"], {"owa_piggy_profile": "une"}),
        (["--profile", "une", "--profile", "nc"], {"owa_piggy_profiles": ["une", "nc"]}),
        (["-A"], {"owa_piggy_profiles": ["all"]}),
        (["--all-profiles", "--profile", "une"], {"owa_piggy_profiles": ["all", "une"]}),
        (["--profile", "all"], {"owa_piggy_profiles": ["all"]}),
    ],
)
def test_cli_profile_flags(argv, expected) -> None:
    args = owa_tui.build_parser().parse_args(argv)
    assert owa_tui._profile_config(args.profile or [], args.all_profiles) == expected


def test_list_screen_merges_profiles_with_a_profile_column(fixture_mode) -> None:
    from owa_tui.screens.todo import TodoScreen

    async def run():
        app = owa_tui.OwaTuiApp(config=dict(ALL))
        async with app.run_test(size=(120, 30)) as pilot:
            app.push_screen(TodoScreen(app._config))
            await pilot.pause(0.5)
            sc = app.screen
            texts = [str(lbl.content) for lbl in sc.query("ListItem Label")]
            return [i["_profile"] for i in sc._items], texts[0]

    profiles, row0 = asyncio.run(run())
    n = len(profiles) // 2
    assert profiles == ["work"] * n + ["side"] * n and n > 0
    assert row0.startswith("[dim]work[/dim] ")


def test_cal_merges_profiles_by_start_and_responds_as_the_event_profile(monkeypatch) -> None:
    from textual.app import App

    import owa_tui.screens.cal.fetch as fetch_mod
    from owa_tui.screens.cal import CalScreen

    monkeypatch.setattr(adapter, "eligible_profiles", lambda config, service="owa": ["une", "nc"])
    per_profile = {
        "une": [{"Id": "u1", "Subject": "U late", "Start": {"DateTime": "2026-09-28T15:00:00"},
                 "End": {"DateTime": "2026-09-28T16:00:00"}}],
        "nc": [{"Id": "n1", "Subject": "N early", "Start": {"DateTime": "2026-09-28T09:00:00"},
                "End": {"DateTime": "2026-09-28T10:00:00"}}],
    }

    minted: list[str | None] = []

    def _token() -> str:
        minted.append(adapter._PROFILE.get())
        return "tok"

    async def _fake(fn, *a, **k):  # patches asyncio.to_thread for the whole test
        module = getattr(fn, "__module__", "")
        if module == "owa_tui.screens.cal.fetch":  # the Graph events call
            return {"value": per_profile[adapter._PROFILE.get()]}
        if module == "owa_tui.screens.cal.screen" and fn.__name__ == "_call":
            return {"ok": True}  # the respond POST
        return fn(*a, **k)  # _token, eligible_profiles

    monkeypatch.setattr(fetch_mod.asyncio, "to_thread", _fake)

    class _App(App[None]):
        def on_mount(self) -> None:
            s = CalScreen(config=dict(ALL), api_base="https://fake.api")
            s._token = _token  # type: ignore[method-assign]
            s._persist_settings = lambda: None  # type: ignore[method-assign]
            self.push_screen(s)

    async def run():
        app = _App()
        async with app.run_test(size=(120, 30)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            sc = app.screen
            order = [(e["_profile"], e["subject"]) for e in sc._events]
            minted.clear()
            await pilot.press("y", "a")  # respond to the first (nc) event
            await app.workers.wait_for_complete()
            return order, minted[0]

    order, respond_profile = asyncio.run(run())  # the respond POST also goes through _fake
    assert order == [("nc", "N early"), ("une", "U late")]
    assert respond_profile == "nc"


def test_switch_profile_leaves_merged_mode(fixture_mode) -> None:
    async def run():
        app = owa_tui.OwaTuiApp(config=dict(ALL), tool="todo")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.switch_profile("side")
            await pilot.pause()
            return app._config

    assert asyncio.run(run()) == {"owa_piggy_profile": "side"}


def test_people_merges_profiles_and_looks_up_detail_in_the_rows_tenant(fixture_mode) -> None:
    from owa_tui.screens.people import PeopleScreen

    minted: list[str | None] = []

    async def run():
        app = owa_tui.OwaTuiApp(config=dict(ALL))
        async with app.run_test(size=(120, 30)) as pilot:
            sc = PeopleScreen(app._config)
            real = sc._get_token_sync
            sc._get_token_sync = lambda: minted.append(adapter._PROFILE.get()) or real()  # type: ignore[method-assign]
            app.push_screen(sc)
            await pilot.pause(0.5)
            tags = [p["_profile"] for p in sc.people]
            row0 = str(sc.query("ListItem Label").first().content)
            last = sc.people[-1]
            minted.clear()
            sc._fetch_detail(last["id"], last["_profile"])
            await app.workers.wait_for_complete()
            return tags, row0, minted

    tags, row0, detail_minted = asyncio.run(run())
    half = len(tags) // 2
    assert tags == ["work"] * half + ["side"] * half and half > 0
    assert row0.startswith("[dim]work[/dim] ")
    assert detail_minted == ["side"]
