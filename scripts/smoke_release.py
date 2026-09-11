"""Verify fresh installation and upgrades using real GitHub release artifacts.

Candidate preflight uses an explicit synthetic version to exercise its updater.
Post-publication checks install the actual previous release and upgrade it.
Every tool environment is temporary and independent of the maintainer's CLI.
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
import zipfile

from codex_ui.lifecycle import REPOSITORY, latest_release, version_tuple, wheel_asset
from codex_ui import __version__


def prior_fixture(data: bytes, version: str, target: Path) -> None:
    old_info = f"ensomniac_codex_ui-{version}.dist-info/"
    new_info = "ensomniac_codex_ui-0.0.0.dist-info/"
    entries = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            content = archive.read(name)
            if name.endswith(".dist-info/RECORD"):
                continue
            if name == "codex_ui/_version.py":
                content = b'__version__ = "0.0.0"\n'
            if name == old_info + "METADATA":
                content = content.replace(f"Version: {version}\n".encode(), b"Version: 0.0.0\n")
            entries[name.replace(old_info, new_info)] = content
    records = io.StringIO()
    writer = csv.writer(records, lineterminator="\n")
    for name, content in entries.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
        writer.writerow([name, f"sha256={digest}", len(content)])
    writer.writerow([new_info + "RECORD", "", ""])
    entries[new_info + "RECORD"] = records.getvalue().encode()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def run(command: list[str], env: dict) -> str:
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    if result.returncode:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    return result.stdout


def select_previous(releases: list[dict], current: str) -> dict:
    candidates = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        try:
            value = version_tuple(release["tag_name"])
        except (ValueError, KeyError, RuntimeError):
            continue
        if value < version_tuple(current):
            candidates.append(release)
    if not candidates:
        raise RuntimeError("No actual previous stable release is available")
    return max(candidates, key=lambda release: version_tuple(release["tag_name"]))


def previous_release(current: str) -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "codex-ui-release-check"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=100", headers=headers)
    with urlopen(request, timeout=30) as response:
        return select_previous(json.load(response), current)


def download(release: dict) -> bytes:
    asset = wheel_asset(release)
    with urlopen(asset["browser_download_url"], timeout=60) as response:
        data = response.read()
    assert "sha256:" + hashlib.sha256(data).hexdigest() == asset["digest"]
    return data


def install(root: Path, wheel: Path) -> tuple[str, dict]:
    env = {**os.environ, "UV_TOOL_DIR": str(root / "tools"), "UV_TOOL_BIN_DIR": str(root / "bin")}
    run(["uv", "tool", "install", "--python", sys._base_executable, str(wheel)], env)
    command = str(root / "bin" / ("codex-ui.exe" if sys.platform == "win32" else "codex-ui"))
    return command, env


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, help="Exercise a locally built updater against the current release")
    args = parser.parse_args()
    if args.candidate and args.candidate.is_dir():
        args.candidate = args.candidate / f"ensomniac_codex_ui-{__version__}-py3-none-any.whl"
    release = latest_release()
    version = release["tag_name"][1:]
    with tempfile.TemporaryDirectory(prefix="codex-ui-release-smoke-") as directory:
        root = Path(directory)
        current = root / wheel_asset(release)["name"]
        current.write_bytes(download(release))
        fresh, fresh_env = install(root / "fresh", current)
        assert run([fresh, "--version"], fresh_env).strip() == f"codex-ui {version}"
        assert json.loads(run([fresh, "capabilities"], fresh_env))["lifecycle"]["upgrade"]
        if args.candidate:
            prior_version = "0.0.0"
            prior = root / "ensomniac_codex_ui-0.0.0-py3-none-any.whl"
            candidate_version = args.candidate.name.removeprefix("ensomniac_codex_ui-").removesuffix("-py3-none-any.whl")
            prior_fixture(args.candidate.read_bytes(), candidate_version, prior)
        else:
            previous = previous_release(release["tag_name"])
            prior_version = previous["tag_name"][1:]
            prior = root / wheel_asset(previous)["name"]
            prior.write_bytes(download(previous))
        command, env = install(root / "upgrade", prior)
        assert run([command, "--version"], env).strip() == f"codex-ui {prior_version}"
        result = json.loads(run([command, "upgrade"], env))
        assert result["updated"] and result["installed_version"] == version, result
        assert run([command, "--version"], env).strip() == f"codex-ui {version}"
        assert not json.loads(run([command, "upgrade", "--check"], env))["update_available"]
        assert json.loads(run([command, "capabilities"], env))["lifecycle"]["upgrade"]
        print(json.dumps({"ok": True, "platform": sys.platform, "from_version": prior_version,
                          "installed_release": version, "fresh_install": True,
                          "synthetic_candidate": bool(args.candidate), "actual_upgrade": True}))


if __name__ == "__main__":
    main()
