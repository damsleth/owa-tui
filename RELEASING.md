# Releasing

Semver. Tags drive releases. `owa-tui` ships as a standalone distribution
separate from `owa-tools`: on PyPI (uploaded locally with `uv publish`), as a
GitHub Release, and as the `damsleth/tap/owa-tui` Homebrew formula.

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
sdist attached. It does **not** touch PyPI: the upload happens locally with
`uv publish`, which reads `UV_PUBLISH_TOKEN` from the environment (source a
gitignored `.env`; never commit or print it).

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

# Build and publish to PyPI.
rm -rf dist build
uv build
set -a && . ../.env && set +a && uv publish dist/owa_tui-X.Y.Z*
```

PyPI's JSON index (`/pypi/owa-tui/json`) lags by minutes after upload. If
`uv publish` reports "File already exists" on a retry but
`pypi.org/pypi/owa-tui/X.Y.Z/json` returns 200, the upload succeeded.

### Homebrew

`damsleth/homebrew-tap` `Formula/owa-tui.rb` installs from the GitHub tag
tarball. After the tag is pushed, set `url` to the new tag and `sha256` to
`curl -sL <url> | shasum -a 256`. owa-tui imports owa-tools in-process, so
owa-tools is vendored as a `resource` in the same virtualenv (not a
`depends_on` formula, whose separate venv owa-tui could not import from);
bump that resource to the current owa-tools tag too. Run `brew audit --strict`,
`brew install --build-from-source` and `brew test`, then commit the tap as
`owa-tui X.Y.Z` and push.

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
- **PyInstaller binaries:** deferred, not planned.

Done: live integration smoke tests now exist, opt-in against real M365 — unit
token smoke (`OWA_TUI_LIVE_TESTS=1`) and full-render e2e (`OWA_TUI_LIVE_E2E=1`,
`e2e/live.test.ts`).
