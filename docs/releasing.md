# Releases

Only the trusted maintainer operates releases. Do not publish from an unreviewed branch.

1. Update `src/codex_ui/_version.py` and `CHANGELOG.md`. Run `uv run python scripts/prepare.py` to sync npm metadata, public install URLs and the bundled skill.
2. Run the documented checks, inspect the playground for native behavior changes, build the wheel and source distribution, then run `npm pack --pack-destination dist`.
3. Generate the Homebrew formula with `uv run python scripts/build_formula.py`. It pins the released wheel and every universal2 PyObjC wheel with SHA-256 and installs dependencies offline. Commit the formula alongside the release change.
4. Merge through the trusted review process. After CI passes on main, run `gh workflow run release.yml -f version=X.Y.Z`. The workflow verifies the version on main and its successful CI check before creating the tag/release. GitHub credentials stay in the maintainer context.
5. Verify the published wheel/source/npm assets, digests, formula URL and documentation site. Test a fresh install and upgrade on supported platforms, then run `codex-ui --version`, `doctor`, and an inspected desktop command. CI tests alone do not prove macOS permissions work.

`upgrade` uses the latest non-prerelease GitHub release and validates artifact origin/digest. Keep every previous release available so explicit recovery remains possible. Do not delete/reuse release tags, move release assets between versions, or silently change a published wheel. Correct a release with a new patch version.

The release workflow publishes GitHub artifacts today. PyPI/npm registry trusted publishing can be added after the maintainer connects those identities. Keep docs explicit about which channels are actually live.

Release notes start with `docs/release-intro.md`, then include only the matching version's `CHANGELOG.md` section and a link to full history. Preview them with `uv run python scripts/release_notes.py`; a missing, empty, or duplicate version section fails before publication. Review the platform statement and install instructions when cutting a release. Editing existing release prose must not replace its tag or package assets.

The **Released install and upgrade** workflow runs after publication on Apple Silicon, Intel, Windows and Linux. It downloads and verifies the current and actual previous stable wheels, installs each in separate temporary uv tool directories, and runs the previous release's real `upgrade` command. It checks the final version, capabilities and no-update result. A separate pre-publication candidate check uses an explicitly synthetic version to exercise the candidate updater against the current public release. These are different checks; the synthetic fixture does not establish an N−1 → N upgrade.

`npm run test:site` checks the home page and guide at four widths, plus real demo state, clipboard paths, keyboard tabs, no-JavaScript access, reduced motion, local links and automated accessibility rules. Use `node scripts/capture_site.cjs` for local review captures and inspect them. Native Chrome interaction remains a separate acceptance check.
