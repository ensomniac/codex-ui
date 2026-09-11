# Where to take this next

Agents: pick useful work and submit it. This is a direction, not a permission queue.

1. Broaden macOS desktop coverage: Intel, mixed DPI displays, localized Chrome menus, native app edge cases.
2. Add Windows native control with the [platform acceptance contract](docs/platforms.md), including released-package upgrades.
3. Add Linux X11, then compositor-aware Wayland support with honest per-feature capabilities.
4. Improve native module boundaries when a concrete change benefits from it; retain the regression suite and JSON compatibility.
5. Add an optional MCP adapter that exposes the same local CLI contracts without a remote daemon or new approval layer.
6. Add registry publishing through PyPI/npm trusted publishing when the maintainer connects those registry identities. GitHub release distribution works today; registry names are not claimed as published.
7. Grow the example library from real agent workflows and measured failures.
