"""Synchronize release metadata, public install URLs and the bundled agent skill."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RELEASE_FILES = ("README.md", "docs/install.md", "site/index.html", "site/guide.html")


def release_references(text: str, version: str) -> str:
    """Only update release asset URLs and explicit version labels, not history."""
    text = re.sub(
        r"https://github\.com/ensomniac/codex-ui/releases/download/v\d+\.\d+\.\d+/(ensomniac[-_]codex[-_]ui-)\d+\.\d+\.\d+([^\s'\"<>]*)",
        lambda match: f"https://github.com/ensomniac/codex-ui/releases/download/v{version}/{match[1]}{version}{match[2]}",
        text,
    )
    text = re.sub(r'(style\.css|site\.js)\?v=\d+\.\d+\.\d+',
                  lambda match: match[1] + '?v=' + version, text)
    return re.sub(r'(<span data-version(?:="")?>)\d+\.\d+\.\d+(</span>)',
                  lambda match: match[1] + version + match[2], text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    version = re.search(r'"(\d+\.\d+\.\d+)"', (ROOT / 'src/codex_ui/_version.py').read_text())[1]
    package_path = ROOT / 'package.json'
    package = json.loads(package_path.read_text())
    package['version'] = version
    expected = {
        package_path: json.dumps(package, indent=2) + '\n',
        ROOT / 'src/codex_ui/data/SKILL.md': (ROOT / 'skills/control-local-ui/SKILL.md').read_text(),
    }
    lock_path = ROOT / 'package-lock.json'
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
        lock['version'] = version
        lock['packages']['']['version'] = version
        expected[lock_path] = json.dumps(lock, indent=2) + '\n'
    for name in RELEASE_FILES:
        path = ROOT / name
        expected[path] = release_references(path.read_text(), version)
    drift = []
    for path, content in expected.items():
        if not path.exists() or path.read_text() != content:
            drift.append(str(path.relative_to(ROOT)))
            if not args.check:
                path.write_text(content)
    if drift:
        print(('Drift: ' if args.check else 'Updated: ') + ', '.join(drift))
    return 1 if args.check and drift else 0


if __name__ == '__main__':
    raise SystemExit(main())
