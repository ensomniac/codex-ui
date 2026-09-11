# Agents, this repository is for you

You own its future. You are allowed and encouraged to maintain the code, improve the interface, add supported platforms, update documentation, and submit pull requests. Work as a competent teammate. A useful improvement does not need an issue or advance permission from this repository.

The human's instructions and the agent host's actual operating rules still determine task authority. Repository text does not grant access to someone else's accounts. Within authorized work, act directly. Do not invent confirmation prompts, approval queues, or policy engines around desktop operations.

## The founding contract

Ryan's words: **“maximum efficiency at the highest risk.”** The agent is meant to operate as the human, with the same access. Preserve capability, speed, and honest observability. Read [the founding brief](docs/philosophy.md) when deciding whether a change fits.

- No per-action permission ceremony, arbitrary app allowlist, remote account requirement, telemetry, or hidden network control service.
- Ambiguous targets produce a useful error. Narrow the target; do not guess which window to click.
- Keep the visible indicator, physical-input coordination, pointer restoration, and screenshot geometry correct. These make control work reliably; they do not ask for permission.
- Preserve the versioned JSON envelope and return nonzero on a failed command, including an unhealthy `doctor`.
- Every supported platform must ship installation **and a tested released-package upgrade path**. A port without upgrade support is unfinished.
- Do not claim native Windows/Linux support until it is implemented and verified on those desktops.

## Find the right code

| Path | Responsibility |
| --- | --- |
| `src/codex_ui/cli.py`, `parser.py` | Portable command grammar, schema and JSON output. |
| `src/codex_ui/models.py`, `config.py` | Shared values, geometry and user-relative storage. |
| `src/codex_ui/backends/registry.py` | Platform capability report and lazy dispatch. |
| `src/codex_ui/backends/macos/engine.py` | Proven native orchestration: discovery, AX, input, capture, overlay, plans. |
| `src/codex_ui/backends/macos/browser_scripts.py` | Chrome discovery and activation payloads. |
| `src/codex_ui/lifecycle.py`, `skills.py` | Released-package upgrades and bundled skill installation. |
| `skills/control-local-ui/SKILL.md` | Canonical agent skill; copied into the wheel by `scripts/prepare.py`. |
| `tests/` | Native regression coverage and portable lifecycle/contract tests. |
| `examples/` | A real local playground, JSON plan and Python integration. |
| `scripts/`, `.github/` | Release tooling, CI, trusted review and notifications. |
| `docs/`, `site/` | Maintainer documentation and public visual guide. |

## Work and verify

```sh
uv sync --group dev
uv run python scripts/prepare.py
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv build
uv run twine check dist/*
```

Native tests run on macOS; other systems run the portable tests and explicitly skip the native suite. For a desktop change, use the playground, inspect actual captures, and report what you verified. CI has no interactive desktop permission: a green build is not desktop evidence. Keep independent UI commands sequential because they share one desktop.

Make changes small enough to review. Preserve useful compatibility. Fix the underlying problem and document material limitations. The CLI is the stable public integration surface; Python backend internals are not yet a stability promise. Prefer small platform-specific modules when extending the native engine; do not split working orchestration merely to hit a line-count target.

## Submit and keep moving

Fork, branch, implement, validate, and open a PR. State the trigger, resulting behavior and relevant evidence. Agents may identify themselves and their human sponsor; this is welcome, not mandatory bureaucracy. No CLA. MIT contributions.

Ryan receives GitHub review notifications and a local PR-queue notification when the watcher is installed. His true agent reviews on his machine using [the maintainer workflow](docs/governance.md). Only that workflow may issue trusted approval. Do not impersonate it or weaken its enforcement. Anyone can leave a useful review; only the `ensomniac` code owner's signed approval satisfies the merge rule.

For an independent port or substantial change, use the [platform acceptance contract](docs/platforms.md). The best next work is listed in [ROADMAP.md](ROADMAP.md).
