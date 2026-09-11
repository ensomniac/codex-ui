"""Local signing and CI verification for one exact PR head and base.

This module never imports code from a pull request. All subprocesses use argv.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

REPO = "ensomniac/codex-ui"
IDENTITY = "ryan-agent"
NAMESPACE = "codex-ui-review"
CONTEXT = "trusted-agent/approval"
ROOT = Path(__file__).resolve().parents[1]


def gh_api(endpoint: str, data: dict | None = None, *, method: str | None = None):
    args = ["gh", "api", endpoint]
    if method:
        args += ["--method", method]
    if data is not None:
        args += ["--input", "-"]
    result = subprocess.run(args, input=json.dumps(data) if data is not None else None,
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def pages(endpoint: str) -> list:
    rows = []
    page = 1
    while True:
        chunk = gh_api(f"{endpoint}{'&' if '?' in endpoint else '?'}per_page=100&page={page}")
        rows.extend(chunk)
        if len(chunk) < 100:
            return rows
        page += 1


def payload(number: int, head: str, base: str, *, issued: int | None = None) -> dict:
    return {"repository": REPO, "pull_request": number, "head": head, "base": base,
            "issued": int(time.time()) if issued is None else issued}


def canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sign(value: dict, key: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="codex-ui-sign-") as directory:
        document = Path(directory) / "approval.json"
        document.write_bytes(canonical(value))
        subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", NAMESPACE,
                        str(document)], check=True, capture_output=True)
        return base64.b64encode(document.with_suffix(".json.sig").read_bytes()).decode()


def verify(value: dict, signature: str, expected: dict, signers: Path | None = None) -> bool:
    if set(value) != {"repository", "pull_request", "head", "base", "issued"}:
        return False
    if any(value.get(key) != expected[key] for key in ("repository", "pull_request", "head", "base")):
        return False
    issued = value.get("issued")
    if not isinstance(issued, int) or not -300 <= time.time() - issued <= 7 * 86400:
        return False
    try:
        raw = base64.b64decode(signature, validate=True)
        with tempfile.TemporaryDirectory(prefix="codex-ui-verify-") as directory:
            sig = Path(directory) / "approval.sig"
            sig.write_bytes(raw)
            result = subprocess.run(["ssh-keygen", "-Y", "verify", "-f",
                                     str(signers or ROOT / ".github/trusted-agent-signers"),
                                     "-I", IDENTITY, "-n", NAMESPACE, "-s", str(sig)],
                                    input=canonical(value), capture_output=True)
            return result.returncode == 0
    except (ValueError, OSError):
        return False


def envelope(value: dict, signature: str) -> str:
    return "```codex-ui-approval\n" + json.dumps({"payload": value, "signature": signature}, sort_keys=True) + "\n```"


def approved(pr: dict, reviews: list, signers: Path | None = None) -> bool:
    owner_reviews = [r for r in reviews if r.get("user", {}).get("login") == "ensomniac"
                     and r.get("state") in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}]
    if not owner_reviews:
        return False
    review = max(owner_reviews, key=lambda row: row["id"])
    if review["state"] != "APPROVED" or review.get("commit_id") != pr["head"]["sha"]:
        return False
    match = re.search(r"```codex-ui-approval\n([^\n]+)\n```", review.get("body") or "")
    if not match:
        return False
    try:
        signed = json.loads(match[1])
        expected = payload(pr["number"], pr["head"]["sha"], pr["base"]["sha"])
        return verify(signed["payload"], signed["signature"], expected, signers)
    except (ValueError, KeyError, TypeError):
        return False
