"""Install the skill shipped with this exact package release."""
from importlib.resources import files
import os
from pathlib import Path

from .models import UIControlError


def install(agent: str, path: str | None = None) -> dict:
    roots = {
        "codex": Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills",
        "claude": Path.home() / ".claude/skills",
        "generic": Path.home() / ".agents/skills",
    }
    target = Path(path).expanduser() if path else roots[agent] / "control-local-ui"
    if target.name != "control-local-ui":
        raise UIControlError("Skill directory must end with control-local-ui")
    target.mkdir(parents=True, exist_ok=True)
    destination = target / "SKILL.md"
    content = files("codex_ui").joinpath("data/SKILL.md").read_text(encoding="utf-8")
    backup = None
    if destination.exists() and destination.read_text() != content:
        backup = target / "SKILL.md.previous"
        backup.write_bytes(destination.read_bytes())
    temporary = target / ".SKILL.md.tmp"
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(destination)
    return {"agent": agent, "skill_path": str(destination), "backup": str(backup) if backup else None}
