"""Exercise a real uv install and upgrade against public release artifacts.

The first public release has no prior wheel, so create a clearly synthetic 0.0.0
fixture from the released wheel, install it, then run its real upgrade command.
All installers operate inside a temporary tool directory, never the user's tool.
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
from urllib.request import urlopen
import zipfile

from codex_ui.lifecycle import latest_release, wheel_asset
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, help="Test a locally built updater against the published release")
    args = parser.parse_args()
    if args.candidate and args.candidate.is_dir():
        args.candidate = args.candidate / f"ensomniac_codex_ui-{__version__}-py3-none-any.whl"
    release = latest_release()
    version = release["tag_name"][1:]
    asset = wheel_asset(release)
    with urlopen(asset["browser_download_url"], timeout=60) as response:
        data = response.read()
    assert "sha256:" + hashlib.sha256(data).hexdigest() == asset["digest"]
    with tempfile.TemporaryDirectory(prefix="codex-ui-release-smoke-") as directory:
        root = Path(directory)
        env = {**os.environ, "UV_TOOL_DIR": str(root / "tools"), "UV_TOOL_BIN_DIR": str(root / "bin")}
        fixture = root / "ensomniac_codex_ui-0.0.0-py3-none-any.whl"
        prior_data = args.candidate.read_bytes() if args.candidate else data
        prior_version = args.candidate.name.removeprefix("ensomniac_codex_ui-").removesuffix("-py3-none-any.whl") if args.candidate else version
        prior_fixture(prior_data, prior_version, fixture)
        run(["uv", "tool", "install", "--python", sys._base_executable, str(fixture)], env)
        command = str(root / "bin" / ("codex-ui.exe" if sys.platform == "win32" else "codex-ui"))
        assert run([command, "--version"], env).strip() == "codex-ui 0.0.0"
        result = json.loads(run([command, "upgrade"], env))
        assert result["updated"] and result["installed_version"] == version, result
        assert run([command, "--version"], env).strip() == f"codex-ui {version}"
        assert not json.loads(run([command, "upgrade", "--check"], env))["update_available"]
        capabilities = json.loads(run([command, "capabilities"], env))
        assert capabilities["lifecycle"]["upgrade"]
        print(json.dumps({"ok": True, "platform": sys.platform, "fixture_version": "0.0.0",
                          "installed_release": version, "actual_upgrade": True}))


if __name__ == "__main__":
    main()
