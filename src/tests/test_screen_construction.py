"""Regression guard: every registered tool screen must accept config POSITIONALLY.

OwaTuiApp.push_tool does `cls(self._config, debug=self._debug)` — config is
passed positionally. Pilot tests construct screens with explicit kwargs, so a
keyword-only `config` slips past them and only blows up in the real binary
(it bit owa-drive and owa-sched). This constructs each registered screen the
way push_tool does, with no running app.
"""

from __future__ import annotations

import owa_tui  # noqa: F401  (ensures screens package import side-effects)
from owa_tui.screens import _bootstrap_screens, registered_tools


def test_every_screen_accepts_positional_config_and_debug() -> None:
    _bootstrap_screens()
    tools = registered_tools()
    assert tools, "expected at least one registered tool"
    for key, _label in tools:
        # Skip fakes other tests inject into the global registry (keys like
        # "_test_tool"); real tool keys never start with an underscore.
        if key.startswith("_"):
            continue
        from owa_tui.screens import get_screen_class

        cls = get_screen_class(key)
        # Exactly the call OwaTuiApp.push_tool makes.
        screen = cls({}, debug=False)
        assert screen is not None, key


def test_every_screen_keeps_the_profile_it_was_built_with() -> None:
    """Switch profile / --profile hand the alias in via config. A screen that
    drops it (sites and drive set self._config, then the base reset it to {})
    silently runs as the broker's default profile."""
    from owa_tui.screens import get_screen_class

    _bootstrap_screens()
    for key, _label in registered_tools():
        if key.startswith("_"):
            continue
        screen = get_screen_class(key)({"owa_piggy_profile": "dno"}, debug=False)
        config = getattr(screen, "_config", None)
        assert config is not None and config.get("owa_piggy_profile") == "dno", key
