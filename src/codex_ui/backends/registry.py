"""One honest platform boundary. Installation is portable; desktop support is explicit."""
import sys
from typing import Any

from ..models import UIControlError


def capabilities(platform_name: str | None = None) -> dict[str, Any]:
    current = platform_name or sys.platform
    supported = current == "darwin"
    return {
        "platform": current,
        "desktop_supported": supported,
        "backend": "macos" if supported else None,
        "desktop": {name: supported for name in (
            "capture", "windows", "accessibility", "ocr_optional", "mouse", "keyboard",
            "chrome_dom", "chrome_console", "window_layout", "visible_indicator",
        )},
        "lifecycle": {"install": True, "upgrade": True, "skill_install": True, "schema": True},
        "roadmap": "https://github.com/ensomniac/codex-ui/blob/main/docs/platforms.md",
    }


def execute(args: Any) -> dict[str, Any]:
    if sys.platform != "darwin":
        raise UIControlError(
            f"Desktop control is not released for {sys.platform} yet. "
            "Installation, upgrade, schema and skills work. Run codex-ui capabilities."
        )
    from .macos import engine
    return engine.execute(args)
