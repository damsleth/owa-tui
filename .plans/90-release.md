# owa-tui release process

_Mirrors the owa-tools release flow (see `owa-tools/RELEASING.md`) with owa-tui-
specific adjustments. Read this alongside `RELEASING.md` and `AGENTS.md`._

## Key difference from owa-tools

owa-tui ships as a **separate PyPI distribution** (`owa-tui`) that carries a
runtime dependency on a published `owa-tools>=1.0.0`. Coordinate version
compatibility across both packages before tagging: the `owa-tools` version
referenced in `pyproject.toml` must already be live on PyPI.

## Tag format

`vX.Y.Z` — same semver convention as owa-tools.

## Pre-release checklist

1. Confirm the `owa-tools>=X.Y.Z` lower bound in `pyproject.toml` is satisfied
   by the currently published `owa-tools` on PyPI:
   ```bash
   pip index versions owa-tools
   ```
2. Run all gates locally:
   ```bash
   .venv/bin/ruff check .
   .venv/bin/python -m compileall -q src
   .venv/bin/python -m pytest -q --cov --cov-fail-under=85
   ```
   All three must be green. The coverage gate is 85% (lower than owa-tools' 90%
   because the Textual `compose()`/`on_mount()` layer is exercised by Pilot + e2e
   tests rather than line-counted).
3. `uv build` and verify the wheel:
   ```bash
   python3 -m venv /tmp/owa-tui-verify
   /tmp/owa-tui-verify/bin/pip install dist/owa_tui-X.Y.Z-*.whl
   /tmp/owa-tui-verify/bin/owa-tui --help
   ```
4. Changelog updated for the new version.
5. End-to-end suite green (black-box, drives the real binary in a pty via fixture-mode):
   ```bash
   npx tui-test            # runs e2e/*.test.ts; no live auth needed (OWA_TUI_FIXTURES)
   ```
   All specs must pass. (There are no `pytest-textual-snapshot` tests — the dep is declared
   but unused; Pilot tests in step 2 plus this e2e suite are the UI gate.)

## Cutting a release

```bash
git checkout main
git pull --ff-only

# Bump version in pyproject.toml, src/owa_tui/__init__.py, and CHANGELOG.md.
$EDITOR pyproject.toml src/owa_tui/__init__.py CHANGELOG.md
git commit -am "release: vX.Y.Z"
git push

# Annotated tag with release notes.
git tag -a vX.Y.Z -m "vX.Y.Z - <headline>

- bullet: ...
"
git push origin vX.Y.Z

# Build, verify, publish to PyPI.
rm -rf dist build
uv build
.venv/bin/python -m pytest -q --cov --cov-fail-under=85
set -a && . ./.env && set +a && uv publish dist/owa_tui-X.Y.Z*
```

The tag push triggers `.github/workflows/release.yml`, which re-runs gates,
rebuilds artifacts, and posts the GitHub Release with wheel + sdist attached.
PyPI uploads happen **locally** with `uv publish` reading `UV_PUBLISH_TOKEN`
from `./.env` (gitignored — never commit it).

## GitHub Actions release workflow

The workflow mirrors owa-tools' `release.yml` with these adaptations:

- **`gates` job**: lint (`ruff check .`), compile (`python -m compileall -q src`),
  unit/Pilot tests with 85% coverage gate (`pytest -q --cov --cov-fail-under=85`),
  plus the tui-test e2e suite (`npx tui-test`, needs Node + `npm ci` in the job).
  Matrix: Python 3.10, 3.11, 3.12 on ubuntu-latest.
- **`build` job**: `uv build` → upload wheel + sdist as `dist` artifact.
- **`binaries` job**: see PyInstaller section below — **conditional on the known
  issue being resolved**. Targets: `ubuntu-latest` (linux-x86_64),
  `macos-14` (macos-arm64). macOS Intel (macos-13) dropped — same rationale as
  owa-tools (deprecated GitHub runners).
- **`github-release` job**: downloads `dist` + `binary-*` artifacts, creates the
  GitHub Release with `softprops/action-gh-release@v2`.

## PyPI publish

```bash
# Verify upload succeeded (index lags by minutes):
pip download --no-deps --dest /tmp/owa-tui-verify owa-tui==X.Y.Z
ls /tmp/owa-tui-verify
```

If `uv publish` reports "File already exists" on a retry but
`pypi.org/pypi/owa-tui/X.Y.Z/json` returns 200, the upload succeeded.

## Homebrew formula

- Add an `owa-tui` formula to the same Homebrew tap that carries `owa-tools`.
- The formula installs the `owa-tui` console script (single binary entry point).
- A draft formula skeleton lives at `src/packaging/homebrew/owa-tui.rb` (to be
  created at first release). Update `url`, `sha256`, and `version` to match the
  published sdist on PyPI. `owa-tools` must be listed as a dependency or both
  formulas must be installed; confirm the tap's dependency strategy before the
  first Homebrew release.
- Verify after tap update:
  ```bash
  brew install owa-tui
  owa-tui --version
  owa-tui --help
  ```

## PyInstaller standalone binaries

### Plan

Produce a multicall standalone binary (`owa-tui`) per OS/arch that requires no
Python install, mirroring the owa-tools `packaging/owa.spec` approach.

### KNOWN ISSUE — Textual + Rich hidden-import and data-file hook risk

**This must be resolved before binary releases ship.**

Textual and Rich are not stdlib — they carry:

1. **Hidden imports:** Textual's CSS engine (`textual.css`), its built-in themes
   (`textual._xterm_theme`, `textual._ansi_theme`), Rich's markup/theme modules,
   and any Textual worker/signal internals are not traversed by PyInstaller's
   static analysis. Without explicit `--hidden-import` entries or a hook, the
   frozen binary will raise `ModuleNotFoundError` at runtime on the first widget
   render.

2. **Data files (CSS/TCSS):** Textual ships `.tcss` (Textual CSS) files and default
   theme assets inside the `textual` package directory. PyInstaller does not
   automatically bundle non-`.py` files unless a `datas` hook entry is present.
   Missing TCSS causes `FileNotFoundError` or silent style degradation at launch.

3. **Rich `_fileno` / `Console` detection:** Rich uses `os.get_terminal_size()` and
   checks `fileno()` in ways that behave differently in a frozen executable; the
   Textual `App` may misdetect terminal capabilities.

**Required work before enabling the `binaries` job:**

- Audit which Textual + Rich submodules are actually imported at runtime for each
  owa-tui adapter (use `--debug imports` with PyInstaller on a local build).
- Write a `packaging/hooks/hook-textual.py` that enumerates all hidden imports and
  adds the `datas` entries for `.tcss` and theme JSON files:
  ```python
  # packaging/hooks/hook-textual.py (skeleton)
  from PyInstaller.utils.hooks import collect_data_files, collect_submodules

  hiddenimports = collect_submodules("textual")
  datas = collect_data_files("textual")
  ```
  Do the same for `hook-rich.py` if needed.
- Run `pyinstaller --clean --noconfirm owa_tui.spec` on both linux-x86_64 and
  macos-arm64 and verify the binary launches, renders the initial screen, and
  exits cleanly (`owa-tui --help` exit 0).
- Add a CI smoke step: `./owa-tui --help` executed against the frozen binary
  artifact before the `github-release` job runs.

Until this work is complete, the `binaries` job in `release.yml` should remain
commented out or gated by a repo variable (`OWA_TUI_PYINSTALLER_READY: false`).
Ship PyPI-only releases in the interim — `pip install owa-tui` is the primary
install path and works without any of this.

## Clean install verification

Before announcing a release:

```bash
python3 -m venv /tmp/owa-tui-clean
/tmp/owa-tui-clean/bin/pip install owa-tui==X.Y.Z
/tmp/owa-tui-clean/bin/owa-tui --help
/tmp/owa-tui-clean/bin/owa-tui --version
```

Where live M365 credentials are available, run at least one authenticated adapter:
```bash
OWA_TUI_LIVE_TESTS=1 /tmp/owa-tui-clean/bin/owa-tui cal
```

Verify `owa-tools` and `owa-tui` can coexist in the same environment without
either importing the other's internal modules:
```bash
/tmp/owa-tui-clean/bin/python -c "import owa_tui; import owa_cal; print('ok')"
```

## Backout / rollback

Identical to the owa-tools policy:

1. Revert the offending PR on `main`.
2. Bump patch version, update changelog, tag `vX.Y.(Z+1)`, push tag, publish
   locally with `uv publish`.
3. Yank the affected version on PyPI via the web UI at
   `https://pypi.org/manage/project/owa-tui/release/X.Y.Z/` — yanking hides it
   from new resolves but does not delete it.
4. If the broken version is referenced by the Homebrew formula, bump the tap.
5. Document the regression and fix version in the changelog.

Never force-push tags. Never delete published versions.

## Deferred work

- **Fixtures + e2e specs for all v2 adapters:** each card-set in `20-v2-coverage.md`
  must add `e2e/fixtures/<tool>*.json` and tui-test specs before merge (same pattern as
  `e2e/actions.test.ts`); they are a release gate.
- **Generated shell completions:** once the `owa-tui <tool>` dispatch surface
  stabilises, generate completions from the subcommand registry.
- **Live integration smoke tests:** opt-in authenticated tests gated by
  `OWA_TUI_LIVE_TESTS=1`; track which adapters have coverage in `RELEASING.md`
  as they are added.
- **PyInstaller binaries:** blocked on the Textual+Rich hook issue documented
  above. Track as a milestone issue in the owa-tui repo.
