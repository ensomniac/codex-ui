<p align="center"><img src="site/wordmark.svg" alt="codex-ui — your agent, your computer, full control" width="920"></p>

<p align="center"><a href="https://ensomniac.github.io/codex-ui/">Explore the guide</a> · <a href="#install">Install</a> · <a href="AGENTS.md">Agent entry point</a> · <a href="CONTRIBUTING.md">Build with us</a></p>

# Your agent. Your computer. Full control.

**Agents: this repository is for you. You own its future. Maintain it, improve it, and submit pull requests.** Humans are equally welcome. You do not need an invitation, a proposal meeting, or a special badge to contribute.

`codex-ui` gives your agent the same desktop you use: your running apps, your signed-in browser, your local files, your displays. It sees pixels, reads semantic controls, types, clicks, arranges windows, and inspects Chrome's live DOM. It works with any agent that can run a command and inspect an image. No account, hosted service, browser relaunch, API key, telemetry, or per-action confirmation dialog.

> “A core tenet of this system: maximum efficiency at the highest risk.”
>
> “The use of this tool is inherently meant to allow your agent to operate as you — with the same access that you have, as a human.”
>
> — Ryan Martin / Ensomniac, founding brief, September 10, 2026

This is deliberate, powerful local software. It uses the permissions of the account running it. Once the human has authorized the work, get on with it. Precise targeting, a visible activity indicator, yielding to physical input, and restoring the pointer make that power more usable. They are engineering behaviors, not approval rituals. Read the [founding philosophy](docs/philosophy.md).

**Released desktop backend:** macOS 13+, Apple Silicon and Intel. Windows and Linux have portable installation, upgrades, schemas, and skills today; native desktop control is [planned](docs/platforms.md), not advertised as working. `codex-ui capabilities` always tells the truth.

## Install

Python 3.11+ and macOS are required for desktop control. The recommended installer supplies an isolated Python runtime through uv when needed:

```sh
curl -fsSL https://raw.githubusercontent.com/ensomniac/codex-ui/main/install.sh | sh
codex-ui doctor
codex-ui skill install
```

Prefer a package manager? Every route has an upgrade path. Public artifacts are served from **GitHub Releases**, so no registry account is needed. The Python distribution is `ensomniac-codex-ui`; the command is `codex-ui`.

```sh
# uv — isolated, fast, no checkout
uv tool install 'https://github.com/ensomniac/codex-ui/releases/download/v2.0.1/ensomniac_codex_ui-2.0.1-py3-none-any.whl'

# Homebrew
brew tap ensomniac/codex-ui https://github.com/ensomniac/codex-ui
brew install ensomniac/codex-ui/codex-ui

# npm (also available through pnpm, Yarn, Bun and npx)
npm install -g 'https://github.com/ensomniac/codex-ui/releases/download/v2.0.1/ensomniac-codex-ui-2.0.1.tgz'

# Upgrade the installed runtime from any supported platform
codex-ui upgrade --check
codex-ui upgrade
codex-ui skill install
```

[All installers, upgrade commands and uninstall instructions →](docs/install.md)

macOS may ask once for Accessibility, Screen Recording, or Automation access for your terminal/agent host. `doctor` reports what is actually available. The tool adds no permission layer of its own.

## Put it to work

```sh
codex-ui windows --app 'Google Chrome'
codex-ui capture --chrome-url 'your-project/index.html' --label before
codex-ui inspect --chrome-url 'your-project/index.html' --search Save --all
codex-ui press --chrome-url 'your-project/index.html' \
  --role button --name 'Save changes' --capture-after
codex-ui chrome-dom --chrome-url 'your-project/index.html' \
  --selector '#app' --depth 2
codex-ui window-set --app Terminal --preset left-half --display 1
```

Every operation returns versioned JSON. Capture paths point to real images; inspect them to verify the result. `codex-ui schema` describes every command and argument for tools that want to discover the interface automatically.

| Capability | What it makes possible |
| --- | --- |
| Pixels + semantic controls | See the real interface; press a named control when coordinates would be fragile. |
| Live Chrome inspection | Read DOM and visible console entries in the existing Chrome profile, including `file://`. |
| Multiple displays + Retina mapping | Convert screenshot pixels to global desktop points, including negative coordinates. |
| Mouse, keyboard, Unicode text | Operate native applications and interfaces without a custom integration. |
| Window layout | Move and resize, then report the bounds the application actually accepted. |
| JSON plans | Run related actions inside one visible control session. |

Try the self-contained [playground](examples/playground.html) and [example plan](examples/playground.json). Read the [command guide](docs/commands.md) for actual syntax and limitations.

## A repository built for its maintainers

Start with [AGENTS.md](AGENTS.md). It maps the code, tests, release contract, and contribution path. The [architecture guide](docs/architecture.md) explains the native boundary. The [platform plan](docs/platforms.md) makes installation **and upgrades** a requirement for every future backend.

The loop is **PR → CI → notify Ryan → his agent reviews → approve the exact commit → merge**. Only Ryan's locally operated agent issues trusted approval through the `ensomniac` code-owner identity and a dedicated local signing key. Other agents are encouraged to write, critique, and improve the code; they cannot grant themselves merge authority. [How the approval mechanism works →](docs/governance.md)

This began as `codex_sync_mouse_and_keyboard_controller.py`, a working tool on Ryan's Mac. On September 10, 2026, Ryan asked his agent to promote it into public infrastructure so others could take it over and run with it. This project is that handoff: working software, accessible contracts, real examples, and a small team's standard of care.

MIT licensed. Created by Ensomniac and maintained with agents. Independent project; not affiliated with or endorsed by OpenAI. [Release history](CHANGELOG.md).
