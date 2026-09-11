#!/usr/bin/env python3
"""For Ryan's local agent: approve reviewed commits and optionally merge them."""
import argparse
from pathlib import Path
import subprocess

from review_lib import REPO, envelope, gh_api, payload, sign


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("number", type=int)
    parser.add_argument("--head", required=True, help="The exact commit actually reviewed")
    parser.add_argument("--body-file", required=True, type=Path, help="Review findings and evidence")
    parser.add_argument("--key", type=Path, default=Path.home() / ".config/codex-ui/maintainer_ed25519")
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()
    if gh_api("user")["login"] != "ensomniac":
        raise SystemExit("Trusted approval requires the ensomniac GitHub identity")
    pr = gh_api(f"repos/{REPO}/pulls/{args.number}")
    if pr["state"] != "open" or pr["draft"] or pr["head"]["sha"] != args.head:
        raise SystemExit("PR is not ready or its head changed; review the current diff")
    if pr["base"]["ref"] != "main" or pr["user"]["login"] == "ensomniac":
        raise SystemExit("Requires a contributor PR targeting main; GitHub forbids self-approval")
    checks = gh_api(f"repos/{REPO}/commits/{args.head}/check-runs?per_page=100")["check_runs"]
    ci = [c for c in checks if c["name"] == "CI"]
    if not ci or max(ci, key=lambda c: c["id"])["conclusion"] != "success":
        raise SystemExit("The current head must have a successful CI check")
    evidence = args.body_file.read_text().strip()
    if len(evidence) < 30:
        raise SystemExit("Provide a concrete review and validation evidence in --body-file")
    value = payload(args.number, args.head, pr["base"]["sha"])
    body = "Reviewed by Ryan's local agent.\n\n" + evidence + "\n\n" + envelope(value, sign(value, args.key))
    # Pin approval to the inspected commit; a subsequent push invalidates the gate.
    gh_api(f"repos/{REPO}/pulls/{args.number}/reviews",
           {"commit_id": args.head, "event": "APPROVE", "body": body})
    subprocess.run(["gh", "workflow", "run", "trusted-review.yml", "--repo", REPO,
                    "--ref", "main", "-f", f"pr={args.number}"], check=True)
    print(f"Approved {REPO}#{args.number} at {args.head}; trusted verification queued.")
    if args.merge:
        subprocess.run(["gh", "pr", "merge", str(args.number), "--repo", REPO,
                        "--squash", "--auto", "--match-head-commit", args.head], check=True)


if __name__ == "__main__":
    main()
