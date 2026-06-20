# Changelog

## Unreleased

### Fixed
- Packaging: wheel/sdist now include all `owa_tui` subpackages (`screens`,
  `screens.base`, `people`, …) via automatic discovery. Previously
  `packages = ["owa_tui"]` shipped only the top-level package, so an installed
  `owa-tui --help` crashed with `ModuleNotFoundError: No module named
  'owa_tui.screens'`.
