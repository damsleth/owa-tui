# Releasing

Semver. Tags drive releases. `owa-tui` ships as a standalone distribution
separate from `owa-tools`, via **GitHub Releases only** — it is not on PyPI
(deferred, not planned).

## Tag format

- `vX.Y.Z`

## Pre-release checklist

1. Confirm the `owa-tools` version constraint in `pyproject.toml` is satisfied
   by the current published `owa-tools` on PyPI.
2. Run the gates locally:
   ```bash
   ruff check .
   python -m compileall -q src
   pytest -q --cov --cov-fail-under=85
   npx tui-test
   ```
3. `uv build` and verify the wheel installs cleanly:
   ```bash
   python3 -m venv /tmp/owa-tui-verify
   /tmp/owa-tui-verify/bin/pip install dist/owa_tui-X.Y.Z-*.whl
   /tmp/owa-tui-verify/bin/owa-tui --help
   ```
4. Changelog updated for the new version.

## Release workflow

The GitHub Actions workflow at `.github/workflows/release.yml` re-runs the
gates (lint, compile, coverage, e2e) on Python 3.10–3.12, rebuilds the
artifacts in CI, and creates the GitHub Release at the tag with the wheel and
sdist attached. Nothing is uploaded to PyPI.

### Cutting a release

```bash
git checkout main
git pull --ff-only

# Bump version in pyproject.toml + src/owa_tui/__init__.py and add a changelog entry.
$EDITOR pyproject.toml src/owa_tui/__init__.py CHANGELOG.md
git commit -am "release: vX.Y.Z"
git push

# Annotated tag with release notes in the message.
git tag -a vX.Y.Z -m "vX.Y.Z - <headline>

- bullet: ...
"
git push origin vX.Y.Z
```

## Backout / rollback

If a release introduces a regression:

1. Revert the offending PR on `main`.
2. Bump the patch version, update the changelog, tag `vX.Y.(Z+1)`, push.
3. Mark the bad GitHub Release as a pre-release or delete its assets; never
   delete the tag.
4. Document the regression and the fix version in the changelog.

Never force-push tags. A bad release is fixed by publishing a higher version.

## Deferred work

- **Snapshot tests:** `pytest-textual-snapshot` fixtures for key screens.
- **Generated shell completions:** once the CLI surface stabilises.
- **PyInstaller binaries / PyPI publish:** deferred, not planned.

Done: live integration smoke tests now exist, opt-in against real M365 — unit
token smoke (`OWA_TUI_LIVE_TESTS=1`) and full-render e2e (`OWA_TUI_LIVE_E2E=1`,
`e2e/live.test.ts`).
