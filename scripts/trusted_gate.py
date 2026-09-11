"""Trusted base-branch verifier. Never check out or execute PR code."""
import json
import os
from pathlib import Path

from review_lib import CONTEXT, REPO, approved, gh_api, pages


def main() -> None:
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise SystemExit("This workflow is reserved for the upstream repository")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    number = event.get("pull_request", {}).get("number") or event.get("inputs", {}).get("pr")
    if number:
        prs = [gh_api(f"repos/{REPO}/pulls/{int(number)}")]
    else:
        prs = pages(f"repos/{REPO}/pulls?state=open&base=main")
    for pr in prs:
        if pr["state"] != "open" or pr["base"]["ref"] != "main":
            continue
        reviews = pages(f"repos/{REPO}/pulls/{pr['number']}/reviews")
        ready = not pr["draft"] and approved(pr, reviews)
        gh_api(f"repos/{REPO}/statuses/{pr['head']['sha']}", {
            "state": "success" if ready else "pending", "context": CONTEXT,
            "description": "Ryan's agent approved this head and base" if ready else "Awaiting Ryan's locally signed agent review",
            "target_url": f"https://github.com/{REPO}/pull/{pr['number']}",
        })
        print(f"PR #{pr['number']}: {'approved' if ready else 'awaiting trusted review'}")


if __name__ == "__main__":
    main()
