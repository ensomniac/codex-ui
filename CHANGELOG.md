# Changelog

## 2.1.1 — 2026-10-30

- Initialize Chrome's complete page Accessibility tree before window inspection or tab activation, so semantic controls work without another assistive client enabling them first.
- Explain missing Python inspection example arguments with usage and help, preserving valid URL fragments and JSON behavior.
- Correct the playground inspection command and document window, display, and global-region captures.
- Update the pinned GitHub Actions used by CI, releases, and trusted review.
- Recognize held fork CI runs with missing PR metadata and handle trusted verification finishing before auto-merge is enabled.

## 2.1.0 — 2026-09-10

- Introduce a quieter visual identity across the website, guide, repository and playground, with a custom window-and-pointer mark.
- Add an on-site command guide, accessible installation controls and a real browser example that reports actual page state.
- Shorten human copy while retaining the founding brief and the invitation for agents to maintain the project.
- Add browser checks for responsive layouts, accessibility, keyboard navigation, clipboard behavior, reduced motion and no-JavaScript use.
- Synchronize public installation URLs with release metadata and publish the site only when its matching packages are available.
- Test actual previous-release upgrades on Apple Silicon, Intel, Windows and Linux.
- Add bot-authored maintainer submissions that keep local signed approval and main branch protections intact.

Native desktop control remains macOS-only. The CLI and native controller behavior are unchanged.

## 2.0.1 — 2026-09-10

- Preserve the running Windows interpreter during upgrades by updating its environment in place.
- Honor an existing GH_TOKEN/GITHUB_TOKEN for authenticated release metadata requests in CI. Normal local use still requires no account.
- Add real upgrade preflight against published artifacts.

Windows users on 2.0.0 should rerun the installer once to receive this fix. macOS/Linux users can use `codex-ui upgrade`.

## 2.0.0 — 2026-09-10

First public release of Ryan / Ensomniac's desktop controller.

- Promote the local 1.2.1 script into an MIT-licensed Python package and public repository.
- Preserve macOS native control, the JSON schema and 39 original regression tests.
- Separate portable CLI, models, parser, browser payloads, platform capabilities and lifecycle.
- Add release upgrades, agent skill installation, package-manager bridges, examples and human documentation.
- Replace maintainer-specific screenshot paths with user-relative configurable storage.
- Make unhealthy `doctor` results return nonzero.
- Fix Chrome page buttons that acknowledge AXPress without firing: click the exact semantic frame once.
- Establish sole-code-owner, locally signed agent review and optional PR notifications.
- Define Windows/Linux expansion with mandatory install and upgrade parity.

The command remains `codex-ui`. Desktop behavior remains macOS-only. Python internals are not a stable API in this release.
