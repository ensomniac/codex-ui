# Give your agent its first desktop task

Use this guide when the user asks you to set up codex-ui and try it. codex-ui is an MIT-licensed local command-line tool for native macOS desktop control. It works with an agent that can run shell commands and inspect images. Native desktop control requires macOS 13+; Windows and Linux currently support portable lifecycle commands only.

## 1. Check and install

Check `command -v codex-ui` and `uname -s`. If the CLI is missing on a supported Mac, read the [installer](https://raw.githubusercontent.com/ensomniac/codex-ui/main/install.sh), then run:

```sh
curl -fsSL https://raw.githubusercontent.com/ensomniac/codex-ui/main/install.sh | sh
```

The installer supplies uv and an isolated Python runtime and installs the latest stable GitHub release. Follow any PATH instructions it prints. Packages are distributed through GitHub Releases, not the PyPI or npm registries.

Run `codex-ui doctor`. If it reports a missing macOS permission, tell the user which permission the actual terminal or agent host needs, then repeat the check after they grant it. Do not report a successful setup from an unhealthy doctor result.

## 2. Load the skill

Read the [control-local-ui skill](https://raw.githubusercontent.com/ensomniac/codex-ui/main/skills/control-local-ui/SKILL.md). Install it for the host you are using:

```sh
codex-ui skill install                  # Codex
codex-ui skill install --agent claude   # Claude Code
codex-ui skill install --agent generic  # Other SKILL.md hosts
```

Choose one matching command. For another skill directory, use `codex-ui skill install --path /your/skills/control-local-ui`. A host may need a new session to discover the installed skill; you can read and use it in the current session. Run `codex-ui schema` for the installed command contract.

## 3. Make a real native click

Open this isolated example URL in Google Chrome:

```sh
open -a 'Google Chrome' 'https://ensomniac.github.io/codex-ui/?demo=first-run'
```

Keep the example visible. The query string gives this task a distinct target. Reuse an existing matching tab if one is already open. If multiple tabs match, narrow the target with the CLI's discovery commands rather than guessing.

```sh
codex-ui focus --chrome-url 'codex-ui/?demo=first-run'
codex-ui inspect --chrome-url 'codex-ui/?demo=first-run' --search 'Mark reviewed' --all
codex-ui press --chrome-url 'codex-ui/?demo=first-run' --role button --name 'Mark reviewed' --capture-after
codex-ui inspect --chrome-url 'codex-ui/?demo=first-run' --search Reviewed --all
```

Use the native `press` command for the click. A JavaScript click or a browser automation click would not verify desktop control. Open the image at the returned `capture.path` and verify the visible “Reviewed” status. Confirm that the final inspection includes a `static_text` element whose value is exactly `Reviewed`, rather than only matching the button's label. `ok: true` alone only establishes command completion.

Report the observed result and show the actual screenshot. If a command fails, report its error and the remaining step instead of describing the task as complete. The example changes only this page's local state; it does not submit a review or contact anyone.

## 4. Put it to work

Try a [desktop task recipe](https://ensomniac.github.io/codex-ui/recipes.html): inspect a signed-in web interface, verify a local UI fix, or arrange a workspace. Operate within the user's task authority, use precise targets, and verify the result. This tool does not expand the user's request or the host's operating rules.

- [Install and uninstall](https://github.com/ensomniac/codex-ui/blob/main/docs/install.md)
- [Human guide and troubleshooting](https://ensomniac.github.io/codex-ui/guide.html)
- [Command reference](https://github.com/ensomniac/codex-ui/blob/main/docs/commands.md)
- [Source and MIT license](https://github.com/ensomniac/codex-ui)
