"""Render practical release notes with only the selected version's changes."""
from pathlib import Path
import re

from codex_ui import __version__

ROOT = Path(__file__).resolve().parents[1]


def render_notes(version: str, intro: str, changelog: str) -> str:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected a stable version, without v")
    sections = re.split(r"(?m)^## ", changelog)
    matches = [section.strip() for section in sections[1:]
               if re.match(re.escape(version) + r"(?:\s|$)", section)]
    if len(matches) != 1 or not matches[0].partition("\n")[2].strip():
        raise ValueError(f"Expected one nonempty changelog section for {version}")
    return (intro.format(version=version).strip() + "\n\n## " + matches[0]
            + f"\n\n[Full changelog](https://github.com/ensomniac/codex-ui/blob/v{version}/CHANGELOG.md)\n")


if __name__ == "__main__":
    print(render_notes(__version__, (ROOT / "docs/release-intro.md").read_text(encoding="utf-8"),
                       (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")), end="")
