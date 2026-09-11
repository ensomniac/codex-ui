# Command guide

## Safety and visibility

Every command that reads or controls visible UI shows an indicator on the
target display before it touches the UI:

- Blue: observing.
- Red: controlling.
- Amber: paused because physical user input was detected.
- Green: completed successfully.

The indicator owns a non-interactive outline around the target. Input commands
fail before acting if the indicator cannot be created. The overlay is excluded
from saved screenshots, and macOS removes it automatically if the command
crashes.

Synthesized input is tagged. If physical input is detected during a sequence,
the tool pauses until the user has been quiet for three seconds, then resumes.
The pointer returns to the exact position recorded before every controlling
command, including when the command fails.

## Quick start

```sh
codex-ui doctor
codex-ui displays
codex-ui windows --app 'Google Chrome' --title 'codex-ui Playground'
codex-ui capture --chrome-url 'codex-ui/examples/playground.html' --label before
codex-ui inspect --chrome-url 'codex-ui/examples/playground.html' --search Market --all
codex-ui press --chrome-url 'codex-ui/examples/playground.html' \
  --role button --name 'Activate demo' --capture-after
codex-ui chrome-console --chrome-url 'codex-ui/examples/playground.html' --level error
codex-ui chrome-dom --chrome-url 'codex-ui/examples/playground.html' \
  --selector '#playground' --depth 2
codex-ui window-set --chrome-url 'codex-ui/examples/playground.html' \
  --preset right-half --display 3 --margin 12
```

Target selectors fail closed when ambiguous. Narrow the application/title/URL,
or explicitly pass the 1-based `--occurrence`.

## Targeting and coordinates

Most commands accept one of:

- `--window-id ID`
- `--app SUBSTRING --title SUBSTRING`
- `--chrome-url LITERAL_SUBSTRING`
- `--frontmost`

Chrome URL targeting searches active tabs first for speed, then background
tabs. Control commands activate the exact matching tab before acting. URL
matching supports `file://` without special handling.

Coordinate commands support global screen points, window-relative points,
normalized window coordinates, or pixels from a saved screenshot:

```sh
codex-ui click --app Safari --title Preview --window-point 120 80
codex-ui click --frontmost --normalized 0.5 0.5
codex-ui click --capture $HOME/screenshots/screen_example.jpg --pixel 800 600
```

Every screenshot has a neighboring `.json` sidecar with its global point
rectangle, pixel dimensions, Retina scale, target, and timestamp. That makes a
pixel selected from an inspected image deterministic on any display layout.

## Moving and resizing windows

`window-set` changes position, size, exact bounds, or applies a common display
layout through macOS Accessibility:

```sh
codex-ui window-set --app Safari --title Preview --position -2800 80
codex-ui window-set --frontmost --size 1400 1000
codex-ui window-set --chrome-url 'project/index.html' --bounds 3100 80 1800 1400
codex-ui window-set --app Terminal --preset left-half --display 2 --margin 12
```

Positions and bounds use global macOS points, including negative coordinates.
Presets include maximize, halves, quarters, and center. Without `--display`, a
preset uses the display containing most of the current window.

The command reads back and reports the actual final bounds. It rolls back when
an application constrains the requested geometry unless `--allow-constrained`
is explicit. It also rejects geometry outside the active displays unless
`--allow-partial` is explicit, and even then keeps at least 64 by 64 points
visible. The status indicator follows the window to its new bounds.

## Semantic and OCR actions

`press` uses macOS Accessibility and fails if the element name/role is missing
or ambiguous. `click-text` tries Accessibility first and uses Tesseract OCR only
when no semantic control matches. Chrome page controls use a single click at
the exact Accessibility frame because Chrome can acknowledge `AXPress` without
dispatching the page handler. Native controls continue to use AXPress.

## Chrome DOM and console inspection

Chrome inspection uses the target tab's own DevTools surface, so it supports
the running Chrome profile and `file://` pages without enabling **Allow
JavaScript from Apple Events** or relaunching Chrome with a debugging port.
DevTools is opened only when needed and the previous open/closed state and
selected panel are restored afterward. Pass `--keep-open` to leave it visible.

Read visible console rows, optionally filtering by level or text:

```sh
codex-ui chrome-console --chrome-url 'project/index.html' --level error
codex-ui chrome-console --chrome-url 'project/index.html' --search 'failed' --limit 50
```

Console output comes from the rows exposed by DevTools Accessibility and
therefore respects the current DevTools filters. Results include the detected
level, message, and source location when Chrome exposes it.

Query the live DOM as bounded structured JSON:

```sh
codex-ui chrome-dom --chrome-url 'project/index.html' \
  --selector '.card.selected' --depth 2 --node-limit 100 --include-html
```

Each node includes its CSS path, attributes, text, viewport rectangle,
visibility, selected computed styles, children, and optional bounded
`outer_html`. Use `--pierce-shadow` when open shadow roots matter.

For a narrowly scoped diagnostic not covered by `chrome-dom`, evaluate a
JavaScript expression and receive a JSON-safe result:

```sh
codex-ui chrome-eval --chrome-url 'project/index.html' \
  '({title: document.title, ready: document.readyState})'
```

Keep evaluation expressions read-only unless page mutation is explicitly part
of the authorized task. The temporary DevTools transfer preserves the complete
macOS clipboard contents.

## JSON sequences

Use `run` to keep several actions inside one indicator and collision-monitoring
session:

```json
{
  "schema_version": 1,
  "target": {
    "chrome_url": "codex-ui/examples/playground.html"
  },
  "actions": [
    {
      "type": "press",
      "role": "button",
      "name": "Activate demo"
    },
    {
      "type": "wait",
      "seconds": 0.25
    },
    {
      "type": "capture",
      "label": "market-selected"
    }
  ]
}
```

Pass the object through `--plan` or save it and use `--plan-file`. Supported
action types are `press`, `click_text`, `click`, `move`, `drag`, `scroll`,
`type`, `key`, `window_set`, `wait`, and `capture`. A `window_set` action accepts
the CLI-equivalent `position`, `size`, `bounds`, `preset`, `display`, `margin`,
`allow_partial`, and `allow_constrained` fields.

All commands emit versioned JSON on stdout and return nonzero on failure. Set
`CODEX_UI_DEBUG=1` only when a traceback is needed.
