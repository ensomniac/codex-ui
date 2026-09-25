Native macOS desktop control for agents: capture windows, inspect controls, click, type, and use your existing Chrome session. MIT licensed; desktop control runs locally without a tool account or hosted service.

**Desktop support:** macOS 13+, Apple Silicon and Intel. Windows/Linux support installation, schemas, skills, and upgrades; native control is planned.

## Try it

[Give your agent its first desktop task](https://ensomniac.github.io/codex-ui/recipes.html#first-run), or install this exact release:

```sh
uv tool install --python 3.12 'https://github.com/ensomniac/codex-ui/releases/download/v{version}/ensomniac_codex_ui-{version}-py3-none-any.whl'
codex-ui doctor
codex-ui skill install
```

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/). macOS may request Accessibility, Screen Recording, or Automation access for your terminal or agent host. [All installation methods](https://ensomniac.github.io/codex-ui/guide.html#install) · [Ask a question](https://github.com/ensomniac/codex-ui/discussions/categories/q-a).

Already installed? Run `codex-ui upgrade --check`, then `codex-ui upgrade` to get the latest stable release.

## Downloads

Use the `.whl` for Python/uv or the `.tgz` for the npm bridge. The `.tar.gz` is the Python source distribution. `SHA256SUMS` covers the uploaded packages. GitHub's **Source code** archives are repository snapshots, not installed applications. [Package-manager instructions](https://github.com/ensomniac/codex-ui/blob/v{version}/docs/install.md).
