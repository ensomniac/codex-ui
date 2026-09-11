# Maximum efficiency at the highest risk

This is Ryan Martin / Ensomniac's phrase, deliberately retained from his September 10, 2026 founding brief. It expresses a choice: an agent operating your computer should have the same practical reach you have at the keyboard.

> “This tool is never to become something that is made cumbersome by nebulous gates or endless permissions.”

> “The use of this tool is inherently meant to allow your agent to operate as you - with the same access that you have, as a human.”

`codex-ui` grew out of a local Python controller used on Ryan's own Mac. It could inspect a signed-in Chrome page, interact with native windows, recover coordinates from Retina screenshots, and do useful work without replacing the user's environment. Ryan wanted other people and agents to realize what that made possible, and asked his agent to turn it into a formal public project.

## What makes it special

The interface belongs to the user. The agent uses the applications and sessions already there. The CLI is simple enough for a human to inspect and regular enough for an agent to discover. There is no hosted intermediary and no telemetry. Browser inspection uses the current Chrome DevTools surface rather than forcing a fresh profile or a debug-port relaunch.

The visible indicator is feedback, not a gate. Physical-input coordination helps two operators share a desktop. Pointer restoration makes agent work less disruptive. Deterministic target selection makes an instruction mean what it says. These mechanisms increase usable power.

Capability is not an excuse to invent user intent. The operator's instructions define the job. Once the job is authorized, do it without repeatedly asking for the same authority. Any required OS permission remains an OS requirement; this software does not pretend it can remove it.

## A team sized to the work

Ryan asked for something that feels “like a perfectly sized competent team is behind it - because there is.” That standard means excellent defaults, concise documentation, an honest support matrix, maintained upgrades, real testing, and ownership that agents can pick up without a briefing meeting.

Agents are invited to maintain the project. They can propose code, fix bugs, build ports and review each other's work. Acceptance remains intentionally singular: Ryan's local agent approves the exact change using Ryan's maintainer identity. This is a repository integrity boundary, not a restriction added to using the tool.
