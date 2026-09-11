# Beyond macOS

| Platform | Native desktop | Install / schema / skill / upgrade |
| --- | --- | --- |
| macOS 13+ Apple Silicon | Released; live desktop verified on the maintainer's Mac | Available |
| macOS 13+ Intel | Same native backend; CI coverage, additional desktop evidence welcome | Available |
| Windows 11 | Planned | Portable lifecycle available; no desktop claim |
| Linux X11 | Planned | Portable lifecycle available; no desktop claim |
| Linux Wayland | Planned after compositor/portal capability work | Portable lifecycle available; no desktop claim |

## Sequence

1. **Windows:** UI Automation for semantics, Win32 input/window APIs, per-monitor DPI coordinates, and Windows Graphics Capture. Implement the visible indicator and user-input coordination in a signed-in desktop session. Do not promise access to secure desktops or OS-protected surfaces. Start with `doctor`, discovery, capture, semantic press and keyboard before Chrome-specific tooling.
2. **Linux X11:** AT-SPI2 semantics, XRandR geometry, XTest input and X11 capture. Make session and display availability explicit in `doctor`. Package native dependencies reproducibly.
3. **Wayland:** probe the actual desktop's screenshot/screencast and remote-desktop portals or supported compositor protocols. Represent capabilities individually. Permission/session decisions imposed by the compositor must be explicit; the tool adds no extra ones. No universal Wayland input claim before desktop-specific verification.

These are implementation plans, not completion dates or working backends. Native framework and distribution choices should be checked against official platform documentation when implementation starts.

## Acceptance contract for every port

A port ships only when all of these are demonstrated:

- Actual native desktop discovery, screenshots with accurate sidecars, semantic controls where supported, mouse/keyboard input, and useful capability diagnostics.
- Visible activity, physical-input coordination, and pointer restoration with evidence on the target OS.
- Versioned JSON behavior compatible with existing callers; precise unsupported-feature errors.
- A clean install and an **N−1 → N released-package upgrade**, with a smoke command after the upgrade. Upgrade support is mandatory on every supported architecture and distribution channel.
- Uninstall instructions and a documented previous-version recovery path.
- Native CI plus manual or automated desktop evidence for DPI/scaling, multiple displays and application focus.

Keep common CLI/lifecycle contracts portable. Add `backends/windows` or `backends/linux` only with real implementation; avoid placeholder adapters that imply support. Windows distribution should add PowerShell and WinGet/Scoop channels with upgrades in the same change. Linux should add distro packages only when the team can maintain their upgrades; uv, pipx, pip and the JS bridge already share the portable release path.
