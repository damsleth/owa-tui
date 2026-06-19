# TODO

- [ ] Add optional live-auth e2e smoke run against real Graph (deferred — flaky/CI-hostile; gate behind an env flag, separate from fixture-mode suite)
- [ ] Harden owa-tui screens/people.py Pilot coverage (currently ~64%): fetch @work worker, search-submit, detail open/close, menu actions, error/empty state — blocks 452-481/502-532/565-619/652-682
- [ ] owa_tui.screens.base.OwaListScreen: replace local _OwaList/_DetailPane with widgets.ListBrowser/widgets.DetailPane to actually build on the kit (Step 0 left them duplicated)
