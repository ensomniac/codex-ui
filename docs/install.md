# Install, upgrade, remove

The first public release is distributed through GitHub Releases. **There is no claim that this package is published on PyPI or the npm registry.** URLs below resolve to released artifacts; `main` is not an upgrade channel. The Python distribution is `ensomniac-codex-ui`, the npm bridge has the same name, and every route exposes `codex-ui`.

## Recommended: standalone installer

```sh
curl -fsSL https://raw.githubusercontent.com/ensomniac/codex-ui/main/install.sh | sh
```

This installs uv if absent, supplies Python 3.12, resolves the latest stable GitHub release and verifies its SHA-256 hash through uv. It installs in an isolated tool environment. Inspect or download the script first if you prefer. It does not install the maintainer watcher.

PowerShell supports the portable lifecycle on Windows; native Windows desktop control is planned:

```powershell
irm https://raw.githubusercontent.com/ensomniac/codex-ui/main/install.ps1 | iex
```

## Package managers

Use the current version's wheel URL from [Releases](https://github.com/ensomniac/codex-ui/releases/latest). These are working 2.0.1 examples:

```sh
# uv
uv tool install 'https://github.com/ensomniac/codex-ui/releases/download/v2.0.1/ensomniac_codex_ui-2.0.1-py3-none-any.whl'

# pipx
pipx install 'https://github.com/ensomniac/codex-ui/releases/download/v2.0.1/ensomniac_codex_ui-2.0.1-py3-none-any.whl'

# pip, in an environment you own
python3 -m venv ~/.local/share/codex-ui/venv
~/.local/share/codex-ui/venv/bin/python -m pip install 'https://github.com/ensomniac/codex-ui/releases/download/v2.0.1/ensomniac_codex_ui-2.0.1-py3-none-any.whl'
~/.local/share/codex-ui/venv/bin/codex-ui doctor

# Homebrew: this repository is also its own tap
brew tap ensomniac/codex-ui https://github.com/ensomniac/codex-ui
brew install ensomniac/codex-ui/codex-ui
```

JavaScript managers use a small bridge that prepares an isolated Python environment on first execution. **Install uv or Python 3.11+ first.** No npm postinstall script runs. The released npm archive includes the matching wheel. The bridge works with node 18+ and caches its runtime under `~/.local/share/codex-ui/npm-runtime`; override with `CODEX_UI_NODE_RUNTIME`.

```sh
npm install -g 'https://github.com/ensomniac/codex-ui/releases/download/v2.0.1/ensomniac-codex-ui-2.0.1.tgz'
pnpm add -g 'https://github.com/ensomniac/codex-ui/releases/download/v2.0.1/ensomniac-codex-ui-2.0.1.tgz'
yarn global add 'https://github.com/ensomniac/codex-ui/releases/download/v2.0.1/ensomniac-codex-ui-2.0.1.tgz'
bun add -g 'https://github.com/ensomniac/codex-ui/releases/download/v2.0.1/ensomniac-codex-ui-2.0.1.tgz'
npx --yes --package='https://github.com/ensomniac/codex-ui/releases/download/v2.0.1/ensomniac-codex-ui-2.0.1.tgz' codex-ui --version
```

`yarn global` applies to Yarn Classic; modern Yarn uses `yarn dlx --package <tarball-url> codex-ui --version`. npm/pnpm/Bun also require their usual global-bin directory on PATH. None of these commands publishes anything to a registry.

## Upgrades are part of the product

```sh
codex-ui upgrade --check
codex-ui upgrade
codex-ui skill install
```

The universal upgrade command resolves the latest stable release, verifies the wheel's GitHub SHA-256 digest and updates the environment that owns the runtime. It uses `uv tool install --force` or `pipx install --force` for pinned-wheel tool installs, pip/uv in a regular venv, or `brew update` and `brew upgrade` for Homebrew. On Windows, it updates packages in place so the running Python interpreter is retained. It never needs a desktop backend to update the package. Windows 2.0.0 users should rerun the installer once to receive the 2.0.1 updater fix.

For the JS bridge, this upgrades its cached Python runtime. To upgrade the bridge itself, repeat your package manager's install command using the new release's `.tgz` URL. Direct-URL requirements are pinned: a generic `npm update`, `pipx upgrade` or `uv tool upgrade` may keep the old URL. Use the universal command or a new release URL, not an expectation that a pinned URL changes.

For Homebrew, the formula's release URL and checksum must advance with every release. `brew upgrade ensomniac/codex-ui/codex-ui` is the native path. `codex-ui upgrade` invokes it for you.

## Skills

```sh
codex-ui skill install                  # ~/.codex/skills/control-local-ui
codex-ui skill install --agent claude   # ~/.claude/skills/control-local-ui
codex-ui skill install --agent generic  # ~/.agents/skills/control-local-ui
codex-ui skill install --path /your/skills/control-local-ui
```

The wheel contains the skill matching its release. Existing differing content is saved as `SKILL.md.previous` before replacement. A manual alternative is to copy `skills/control-local-ui` from the release source. Agents supporting the open SKILL.md format can consume it directly. [Codex skills documentation](https://learn.chatgpt.com/docs/build-skills) describes host-specific discovery.

## First desktop use

Run `codex-ui doctor`. macOS can require Accessibility and Screen Recording for the terminal or agent application launching the command, and Automation for Chrome/System Events. Grant the actual host requested by macOS once. `doctor` reports Accessibility and capture availability; Chrome Automation is exercised when Chrome is used. Tesseract is optional: `brew install tesseract` adds OCR fallback. Native semantic actions work without it.

If a new Python runtime changes OS permission attribution, rerun `doctor` and grant the reported host as needed. Permissions cannot be silently transplanted between identities by this package.

## Uninstall or recover

| Installation | Remove |
| --- | --- |
| uv | `uv tool uninstall ensomniac-codex-ui` |
| pipx | `pipx uninstall ensomniac-codex-ui` |
| pip/venv | Remove that dedicated venv, or run its `python -m pip uninstall ensomniac-codex-ui`. |
| Homebrew | `brew uninstall ensomniac/codex-ui/codex-ui` |
| npm / pnpm / Yarn Classic / Bun | Use that manager's global remove command for `ensomniac-codex-ui`. |

The JS runtime cache, screenshots, installed skill, and coordination state are user data and are not deleted implicitly. Remove only the corresponding directories you intend to discard. A previous release can be installed explicitly from its release wheel or npm archive. For uv/pipx use `install --force` with that previous URL. Restore a Homebrew version from a reviewed previous formula revision. Inspect `codex-ui --version` and `doctor` afterward.

See the upstream [uv tool documentation](https://docs.astral.sh/uv/concepts/tools/), [npm URL installation documentation](https://docs.npmjs.com/cli/install/) and [Homebrew formula guidance](https://docs.brew.sh/Language-Specific-Formulae) for manager behavior.
