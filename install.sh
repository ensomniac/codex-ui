#!/bin/sh
# Install the latest stable GitHub release in an isolated uv tool environment.
set -eu
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
  export PATH
fi
codex_ui_metadata=$(mktemp)
trap 'rm -f "$codex_ui_metadata"' EXIT HUP INT TERM
curl -fsSL https://api.github.com/repos/ensomniac/codex-ui/releases/latest > "$codex_ui_metadata"
codex_ui_wheel=$(uv run --no-project --python 3.12 python - "$codex_ui_metadata" <<'PY'
import json, re, sys
release = json.load(open(sys.argv[1]))
tag = release['tag_name']
assert re.fullmatch(r'v\d+\.\d+\.\d+', tag), 'Expected a stable release'
name = 'ensomniac_codex_ui-' + tag[1:] + '-py3-none-any.whl'
asset = next(a for a in release['assets'] if a['name'] == name)
url = 'https://github.com/ensomniac/codex-ui/releases/download/' + tag + '/' + name
assert asset['browser_download_url'] == url
digest = asset.get('digest', '')
assert re.fullmatch(r'sha256:[0-9a-f]{64}', digest), 'Missing release digest'
print(url + '#sha256=' + digest[7:])
PY
)
uv tool install --python 3.12 --force "$codex_ui_wheel"
uv tool update-shell
printf '\ncodex-ui is installed. Open a new shell if needed, then run:\n  codex-ui doctor\n  codex-ui skill install\n'
