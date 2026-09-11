"""Run: python examples/inspect_page.py your-project/index.html"""
import json
import subprocess
import sys

url_fragment = sys.argv[1]
result = subprocess.run(
    ["codex-ui", "--compact", "chrome-dom", "--chrome-url", url_fragment,
     "--selector", "main", "--depth", "1"],
    capture_output=True, text=True,
)
payload = json.loads(result.stdout)
if result.returncode:
    raise SystemExit(payload["error"]["message"])
print(json.dumps(payload, indent=2))
