"""Install/remove the maintainer's read-only macOS notification LaunchAgent."""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LABEL = "com.ensomniac.codex-ui.reviews"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("The maintainer notification installer currently supports macOS")
    target = Path.home() / f"Library/LaunchAgents/{LABEL}.plist"
    domain = f"gui/{os.getuid()}"
    if target.exists():
        subprocess.run(["launchctl", "bootout", domain, str(target)], capture_output=True)
    if args.uninstall:
        target.unlink(missing_ok=True)
        print("Removed PR notification watcher")
        return
    gh = shutil.which("gh")
    if not gh:
        raise SystemExit("Install and authenticate gh first")
    logs = Path.home() / "Library/Logs/codex-ui"
    logs.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    settings = {"Label": LABEL, "ProgramArguments": [sys.executable, str(ROOT / "scripts/notify_reviews.py")],
                "StartInterval": 180, "RunAtLoad": True,
                "EnvironmentVariables": {"PATH": f"{Path(gh).parent}:/usr/bin:/bin:/usr/sbin:/sbin"},
                "StandardOutPath": str(logs / "reviews.log"),
                "StandardErrorPath": str(logs / "reviews.error.log")}
    target.write_bytes(plistlib.dumps(settings))
    subprocess.run(["launchctl", "bootstrap", domain, str(target)], check=True)
    print(f"Installed {target}; checks every three minutes and never executes a model")


if __name__ == "__main__":
    main()
