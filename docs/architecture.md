# Architecture

```text
human / agent / script
         │  arguments or JSON plan
         ▼
parser → CLI → versioned JSON envelope
         ├── schema / capabilities / skill / upgrade  [portable]
         └── registry → native backend
                        └── macOS engine
                            ├── Quartz: displays, windows, pixels, input
                            ├── Accessibility: controls, focus, window geometry
                            ├── Cocoa: indicator, clipboard, image encoding
                            └── Chrome JXA + DevTools: discovery, DOM, console
```

The CLI is the compatibility boundary. It keeps `ok`, `command`, `version`, `schema_version`, and `duration_ms` on stdout. Failures add an `error` object and return nonzero. Help/version use conventional text. Diagnostics from installers go to stderr. `doctor` is a real readiness check, not an unconditional success result.

`models.py` holds portable screen and target values. Native modules load lazily, so installing the package, asking for help, generating a command schema and upgrading do not require macOS frameworks. `registry.py` reports which backend actually exists.

The first public release preserves the working macOS orchestration and its regression suite. It extracts data contracts, parser, browser scripts, configuration and lifecycle without rewriting thousands of lines of working native behavior. Future additions should form cohesive modules behind the backend boundary; broad mechanical refactoring is not a release prerequisite.

## Desktop invariants

Coordinates are global desktop points unless explicitly marked as screenshot pixels. Sidecars contain the point rectangle and scale. Displays may have negative positions and different pixel densities. Never assume the primary display is the only one.

Target selectors are literal and ambiguity is an error. Chrome selection prefers active tabs, then searches background tabs. Activation verifies the selected tab. The native indicator appears before UI work; control sessions coordinate with physical input and restore the pointer, including failure paths.

Chrome DOM inspection temporarily uses DevTools. It preserves clipboard data and normally restores the panel layout. Visible console results respect DevTools filters and depend on Accessibility/OCR exposure. Absence of readable rows is not proof that the page has no errors.

## Storage and network

Screenshots default to `~/screenshots`; override with `CODEX_UI_SCREENSHOTS`. Runtime coordination defaults to `~/.cache/codex-ui/state.json`; override its directory with `CODEX_UI_STATE_DIR`. `CODEX_UI_DEBUG=1` includes tracebacks. Desktop operations have no telemetry or background network service. `upgrade` explicitly contacts GitHub and the selected package installer. The optional maintainer watcher contacts GitHub on a schedule; normal users do not install it.

## Release contract

`_version.py` is the Python source of truth. `scripts/prepare.py` synchronizes the bundled skill and npm version. CI checks for drift. GitHub Releases carry the wheel, source distribution, npm bridge and SHA-256 checksums. Upgrades resolve the latest stable release, verify the wheel digest, then use the installing environment's manager. No runtime code is pulled from a development branch.
