"""Stable-release upgrades, independent of the desktop backend.

GitHub release assets are the distribution source. Nothing executes from main.
Package-manager output goes to stderr so stdout remains a single JSON result.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

from ._version import __version__
from .models import UIControlError

REPOSITORY = "ensomniac/codex-ui"
PACKAGE = "ensomniac-codex-ui"


def version_tuple(version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise UIControlError(f"Expected a stable semantic version, got {version!r}")
    return tuple(int(part) for part in match.groups())


def latest_release() -> dict:
    request = Request(f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
                      headers={"Accept": "application/vnd.github+json", "User-Agent": "codex-ui"})
    with urlopen(request, timeout=30) as response:
        release = json.load(response)
    version_tuple(release["tag_name"])
    if release.get("draft") or release.get("prerelease"):
        raise UIControlError("Expected a published stable release")
    return release


def wheel_asset(release: dict) -> dict:
    version = release["tag_name"].removeprefix("v")
    name = f"ensomniac_codex_ui-{version}-py3-none-any.whl"
    for asset in release.get("assets", []):
        if asset["name"] == name:
            expected = f"https://github.com/{REPOSITORY}/releases/download/{release['tag_name']}/{name}"
            if asset["browser_download_url"] != expected:
                raise UIControlError("Release wheel has an unexpected origin")
            return asset
    raise UIControlError(f"Release does not contain {name}")


def manager() -> str:
    prefix = Path(sys.prefix)
    if os.environ.get("CODEX_UI_MANAGER") == "homebrew":
        return "homebrew"
    if (prefix / "pipx_metadata.json").exists():
        return "pipx"
    if (prefix / "uv-receipt.toml").exists():
        return "uv"
    if sys.prefix != sys.base_prefix:
        return "venv"
    return "pip"


def upgrade_command(method: str, wheel: str) -> list[str]:
    if method == "homebrew":
        return ["brew", "upgrade", "ensomniac/codex-ui/codex-ui"]
    if method == "pipx":
        # Reinstall a direct wheel requirement; `pipx upgrade` preserves old URL pins.
        return ["pipx", "install", "--force", "--python", sys._base_executable, wheel]
    if method == "uv":
        return ["uv", "tool", "install", "--force", "--python", sys._base_executable, wheel]
    if shutil.which("uv"):
        return ["uv", "pip", "install", "--python", sys.executable, "--upgrade", wheel]
    return [sys.executable, "-m", "pip", "install", "--upgrade", wheel]


def run_installer(command: list[str]) -> None:
    result = subprocess.run(command, stdout=sys.stderr, stderr=sys.stderr, check=False)
    if result.returncode:
        raise UIControlError(f"Upgrade installer exited with {result.returncode}; see stderr")


def verify_installed_version(expected: str, method: str) -> None:
    executable = sys.executable
    if method == "homebrew":
        prefix = subprocess.check_output(["brew", "--prefix", "ensomniac/codex-ui/codex-ui"], text=True).strip()
        executable = str(Path(prefix) / "libexec/bin/python")
    result = subprocess.run(
        [executable, "-c", "from importlib.metadata import version; print(version('ensomniac-codex-ui'))"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode or result.stdout.strip() != expected:
        raise UIControlError("Installer completed, but the new runtime version could not be verified")


def upgrade(*, check: bool = False) -> dict:
    release = latest_release()
    latest = release["tag_name"].removeprefix("v")
    available = version_tuple(latest) > version_tuple(__version__)
    method = manager()
    result = {"installed_version": __version__, "latest_version": latest,
              "update_available": available, "manager": method, "updated": False,
              "release_url": release["html_url"]}
    if check or not available:
        return result
    if method == "homebrew":
        run_installer(["brew", "update"])
        run_installer(upgrade_command(method, ""))
    else:
        asset = wheel_asset(release)
        digest = asset.get("digest") or ""
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise UIControlError("Release wheel is missing its GitHub SHA-256 digest")
        with tempfile.TemporaryDirectory(prefix="codex-ui-upgrade-") as directory:
            wheel = Path(directory) / asset["name"]
            request = Request(asset["browser_download_url"], headers={"User-Agent": "codex-ui"})
            with urlopen(request, timeout=60) as response:
                data = response.read(32 * 1024 * 1024 + 1)
            if len(data) > 32 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != digest[7:]:
                raise UIControlError("Release wheel checksum mismatch")
            wheel.write_bytes(data)
            run_installer(upgrade_command(method, str(wheel)))
    verify_installed_version(latest, method)
    result.update(updated=True, installed_version=latest)
    return result
