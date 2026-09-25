"""Inspect a Chrome page whose URL contains a distinctive fragment."""
import argparse
import json
import subprocess


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Inspect the main element of a Chrome tab selected by URL fragment."
    )
    parser.add_argument(
        "url_fragment",
        help="distinctive part of the target tab URL (for example, my-project/index.html)",
    )
    args = parser.parse_args(argv)

    result = subprocess.run(
        ["codex-ui", "--compact", "chrome-dom", "--chrome-url", args.url_fragment,
         "--selector", "main", "--depth", "1"],
        capture_output=True, text=True,
    )
    payload = json.loads(result.stdout)
    if result.returncode:
        raise SystemExit(payload["error"]["message"])
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
