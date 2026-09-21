# TODO
- [ ] cal tui: j/k (and u/d) scroll the detail pane when it has focus, mirroring mail (CalDetailPane has no BINDINGS)
- [ ] cal tui: reading_pane / split_ratio settings apply live like mail does (_make_layout only runs in compose)
- [ ] owa-tui main(): refuse to start when stdout is not a tty (exit 2 usage error) instead of letting Textual misrender
- [ ] mail tui: date_format=custom has no UI entry path and never calls validate_custom_format — either wire it (prompt + validate, status 'invalid strftime format: …') or drop 'custom' from the cycle
- [ ] mail tui (low): search modal only takes KQL; since/until are plumbed to build_list_query but unreachable from the UI
