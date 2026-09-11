# Release a complete product

Only the trusted maintainer operates releases. Do not publish from an unreviewed branch.

1. Update `src/codex_ui/_version.py` and `CHANGELOG.md`. Update visible pinned install examples. Run `uv run python scripts/prepare.py` to sync the npm manifest and bundled skill.
2. Run the documented checks, inspect the playground for native behavior changes, build the wheel and source distribution, then run `npm pack --pack-destination dist`.
3. Generate the Homebrew formula with `uv run python scripts/build_formula.py`. It pins the released wheel and every universal2 PyObjC wheel with SHA-256 and installs dependencies offline. Commit the formula alongside the release change.
4. Merge through the trusted review process. After CI passes on main, run `gh workflow run release.yml -f version=X.Y.Z`. The workflow verifies the version on main and its successful CI check before creating the tag/release. GitHub credentials stay in the maintainer context.
5. Verify the published wheel/source/npm assets, digests, formula URL and documentation site. Test a fresh install and upgrade on supported platforms, then run `codex-ui --version`, `doctor`, and an inspected desktop command. CI tests alone do not prove macOS permissions work.

`upgrade` uses the latest non-prerelease GitHub release and validates artifact origin/digest. Keep every previous release available so explicit recovery remains possible. Do not delete/reuse release tags, move release assets between versions, or silently change a published wheel. Correct a release with a new patch version.

The release workflow publishes GitHub artifacts today. PyPI/npm registry trusted publishing can be added after the maintainer connects those identities. Keep docs explicit about which channels are actually live.

The **Released install and upgrade** workflow runs after publication on Apple Silicon, Intel, Windows and Linux. It downloads and verifies the public wheel, installs a synthetic `0.0.0` fixture in a temporary uv tool directory, runs the real `upgrade` command against GitHub, and verifies the installed release. The synthetic fixture is explicit because the first public release has no earlier published wheel. Subsequent releases should also retain evidence for upgrades from the actual previous release.
