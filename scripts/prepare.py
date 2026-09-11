"""Synchronize release metadata and the bundled agent skill; --check detects drift."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


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
