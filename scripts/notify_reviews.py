#!/usr/bin/env python3
"""Read-only local PR watcher. Notify Ryan to run his agent; never run a model."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from review_lib import REPO, approved, pages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Show the queue without notifying")
    args = parser.parse_args()
    state = Path.home() / ".cache/codex-ui/review-notifications.json"
    try:
        seen = json.loads(state.read_text())
    except (OSError, ValueError):
        seen = {}
    queue = []
    for pr in pages(f"repos/{REPO}/pulls?state=open&base=main"):
        if pr["draft"] or approved(pr, pages(f"repos/{REPO}/pulls/{pr['number']}/reviews")):
            continue
        token = pr["head"]["sha"] + ":" + pr["base"]["sha"]
        queue.append({"number": pr["number"], "head": pr["head"]["sha"], "url": pr["html_url"]})
        if not args.check and seen.get(str(pr["number"])) != token:
            message = f"PR #{pr['number']} is ready. Run your agent: review codex-ui PR #{pr['number']}."
            if sys.platform == "darwin":
                script = 'on run argv\ndisplay notification (item 1 of argv) with title "codex-ui needs your agent"\nend run'
                subprocess.run(["/usr/bin/osascript", "-e", script, message], check=True, capture_output=True)
            else:
                print(message)
            seen[str(pr["number"])] = token
    if not args.check:
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps(seen, indent=2) + "\n")
    print(json.dumps({"repository": REPO, "waiting_for_agent": queue}, indent=2))


if __name__ == "__main__":
    main()
