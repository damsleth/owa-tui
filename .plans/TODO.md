# TODO
- [ ] mail tui: date_format=custom has no UI entry path and never calls validate_custom_format — either wire it (prompt + validate, status 'invalid strftime format: …') or drop 'custom' from the cycle
- [ ] mail tui (low): search modal only takes KQL; since/until are plumbed to build_list_query but unreachable from the UI
- [ ] when reading an email (either using enter or l to navigate into the email), the reading pane should be active, indicated by highlighting the reading pane, and scrolling up and down with j/k should affect the reading pane, not the mail list pane
- [ ] scheduling only returns 403
- [ ] people: people details should show in a right pane by default, similar to email
- [ ] investigate causes of 429 when using the owa-tui. happens in many tools, including people, very quickly
- [ ] show errors/warnings/messages at the top instead of the bottom, e.g. overlaying the top profile + email row
- [ ] implement automated TUI design testing
