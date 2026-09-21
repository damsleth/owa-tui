# TODO
- [ ] mail tui: date_format=custom has no UI entry path and never calls validate_custom_format — either wire it (prompt + validate, status 'invalid strftime format: …') or drop 'custom' from the cycle
- [ ] mail tui (low): search modal only takes KQL; since/until are plumbed to build_list_query but unreachable from the UI
