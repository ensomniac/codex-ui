"""User-relative storage, with explicit overrides for embedding applications."""
import os
from pathlib import Path

SCHEMA_VERSION = 1
SCREENSHOTS_ROOT = Path(os.environ.get("CODEX_UI_SCREENSHOTS", str(Path.home() / "screenshots"))).expanduser()
RUNTIME_STATE_PATH = Path(os.environ.get("CODEX_UI_STATE_DIR", str(Path.home() / ".cache/codex-ui"))).expanduser() / "state.json"
