"""Platform-independent CLI grammar; also powers the agent command schema."""
import argparse
from ._version import __version__ as VERSION

WINDOW_PRESETS = (
    "maximize",
    "left-half",
    "right-half",
    "top-half",
    "bottom-half",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "center",
)

def target_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("target window")
    group.add_argument("--window-id", type=int)
    group.add_argument("--app", help="Application-owner name substring")
    group.add_argument("--title", help="Window-title substring")
    group.add_argument("--chrome-url", help="Literal URL substring across all Chrome tabs")
    group.add_argument("--frontmost", action="store_true", help="Use the frontmost application's top window")
    group.add_argument("--occurrence", type=int, help="1-based match when a selector intentionally matches several targets")


def chrome_target_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("Chrome target")
    group.add_argument(
        "--chrome-url",
        required=True,
        help="Literal URL substring across all Chrome tabs, including file://",
    )
    group.add_argument(
        "--occurrence",
        type=int,
        help="1-based match when the URL substring intentionally matches several tabs",
    )


def coordinate_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--at", nargs=2, type=float, metavar=("X", "Y"), help="Global screen point")
    parser.add_argument(
        "--window-point", nargs=2, type=float, metavar=("X", "Y"), help="Point relative to target window"
    )
    parser.add_argument(
        "--normalized", nargs=2, type=float, metavar=("X", "Y"), help="0..1 point relative to target window"
    )
    parser.add_argument("--capture", help="Screenshot image or metadata sidecar")
    parser.add_argument("--pixel", nargs=2, type=float, metavar=("X", "Y"), help="Pixel in --capture")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-ui",
        description="Your agent. Your computer. Full control. Versioned JSON on stdout.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check permissions and installed capabilities")
    subparsers.add_parser("displays", help="List active displays")

    windows = subparsers.add_parser("windows", help="List targetable windows")
    windows.add_argument("--app")
    windows.add_argument("--title")
    windows.add_argument("--all", action="store_true", help="Include off-screen/minimized windows")

    focus = subparsers.add_parser("focus", help="Focus a window or Chrome tab")
    target_flags(focus)

    window_set = subparsers.add_parser(
        "window-set",
        help="Move, resize, or arrange a window with verified global bounds",
    )
    target_flags(window_set)
    window_set.add_argument("--position", nargs=2, type=float, metavar=("X", "Y"))
    window_set.add_argument("--size", nargs=2, type=float, metavar=("W", "H"))
    window_set.add_argument("--bounds", nargs=4, type=float, metavar=("X", "Y", "W", "H"))
    window_set.add_argument("--preset", choices=WINDOW_PRESETS)
    window_set.add_argument("--display", type=int, help="1-based display index for --preset")
    window_set.add_argument("--margin", type=float, default=0.0)
    window_set.add_argument("--allow-partial", action="store_true")
    window_set.add_argument("--allow-constrained", action="store_true")
    window_set.add_argument("--capture-after", action="store_true")

    open_parser = subparsers.add_parser("open", help="Open a URL in a named application")
    open_parser.add_argument("url")
    open_parser.add_argument("--application", default="Google Chrome")
    open_parser.add_argument("--wait", type=float, default=0.5)

    capture = subparsers.add_parser("capture", help="Capture a target window, display, or region")
    target_flags(capture)
    capture.add_argument("--display", type=int, help="1-based active display index")
    capture.add_argument("--region", nargs=4, type=float, metavar=("X", "Y", "W", "H"))
    capture.add_argument("--focus", action="store_true")
    capture.add_argument("--label")
    capture.add_argument("--format", choices=("jpg", "png"), default="jpg")
    capture.add_argument("--quality", type=float, default=0.92)

    inspect_parser = subparsers.add_parser("inspect", help="List visible actionable Accessibility elements")
    target_flags(inspect_parser)
    inspect_parser.add_argument("--search")
    inspect_parser.add_argument("--all", action="store_true", help="Include non-actionable nodes")
    inspect_parser.add_argument("--limit", type=int, default=500)
    inspect_parser.add_argument("--focus", action="store_true")

    press = subparsers.add_parser("press", help="Press one semantic Accessibility element")
    target_flags(press)
    press.add_argument("--name", required=True)
    press.add_argument("--role")
    press.add_argument("--contains", action="store_true")
    press.add_argument("--element-occurrence", type=int)
    press.add_argument("--capture-after", action="store_true")

    click_text = subparsers.add_parser("click-text", help="Press accessible text or fall back to OCR")
    target_flags(click_text)
    click_text.add_argument("text")
    click_text.add_argument("--role")
    click_text.add_argument("--contains", action="store_true")
    click_text.add_argument("--element-occurrence", type=int)
    click_text.add_argument("--capture-after", action="store_true")

    for name in ("click", "double-click", "move"):
        action = subparsers.add_parser(name, help=f"{name.title()} at an explicit coordinate")
        target_flags(action)
        coordinate_flags(action)
        if name != "move":
            action.add_argument("--button", choices=("left", "right"), default="left")
        action.add_argument("--capture-after", action="store_true")

    drag = subparsers.add_parser("drag", help="Drag between two global screen points")
    target_flags(drag)
    drag.add_argument("--from", dest="start", nargs=2, type=float, required=True, metavar=("X", "Y"))
    drag.add_argument("--to", dest="end", nargs=2, type=float, required=True, metavar=("X", "Y"))
    drag.add_argument("--duration", type=float, default=0.4)
    drag.add_argument("--capture-after", action="store_true")

    scroll = subparsers.add_parser("scroll", help="Scroll at a target point")
    target_flags(scroll)
    coordinate_flags(scroll)
    scroll.add_argument("--delta-x", type=int, default=0)
    scroll.add_argument("--delta-y", type=int, required=True)
    scroll.add_argument("--capture-after", action="store_true")

    type_parser = subparsers.add_parser("type", help="Type Unicode text into the focused target")
    target_flags(type_parser)
    type_parser.add_argument("text")
    type_parser.add_argument("--capture-after", action="store_true")

    key = subparsers.add_parser("key", help="Send a key chord such as cmd+l or escape")
    target_flags(key)
    key.add_argument("chord")
    key.add_argument("--capture-after", action="store_true")

    chrome_console = subparsers.add_parser(
        "chrome-console",
        help="Read visible Chrome DevTools Console entries",
    )
    chrome_target_flags(chrome_console)
    chrome_console.add_argument("--search", help="Case-insensitive message substring")
    chrome_console.add_argument(
        "--level",
        choices=("all", "error", "warning", "info", "log", "debug", "verbose", "unknown"),
        default="all",
    )
    chrome_console.add_argument("--limit", type=int, default=200)
    chrome_console.add_argument("--keep-open", action="store_true")
    chrome_console.add_argument("--capture-after", action="store_true")

    chrome_dom = subparsers.add_parser(
        "chrome-dom",
        help="Query and serialize the live DOM through Chrome DevTools",
    )
    chrome_target_flags(chrome_dom)
    chrome_dom.add_argument("--selector", default="html", help="CSS selector for root elements")
    chrome_dom.add_argument("--depth", type=int, default=3, help="Descendant depth per matched root")
    chrome_dom.add_argument("--node-limit", type=int, default=200)
    chrome_dom.add_argument("--text-limit", type=int, default=500)
    chrome_dom.add_argument("--include-html", action="store_true")
    chrome_dom.add_argument("--html-limit", type=int, default=20000)
    chrome_dom.add_argument("--pierce-shadow", action="store_true")
    chrome_dom.add_argument("--timeout", type=float, default=5.0)
    chrome_dom.add_argument("--keep-open", action="store_true")
    chrome_dom.add_argument("--capture-after", action="store_true")

    chrome_eval = subparsers.add_parser(
        "chrome-eval",
        help="Evaluate a JavaScript expression in the page through Chrome DevTools",
    )
    chrome_target_flags(chrome_eval)
    chrome_eval.add_argument("expression")
    chrome_eval.add_argument("--timeout", type=float, default=5.0)
    chrome_eval.add_argument("--keep-open", action="store_true")
    chrome_eval.add_argument("--capture-after", action="store_true")

    run = subparsers.add_parser("run", help="Execute a versioned JSON action sequence")
    plan_group = run.add_mutually_exclusive_group(required=True)
    plan_group.add_argument("--plan", help="Inline JSON object")
    plan_group.add_argument("--plan-file", help="Path to a JSON plan")
    run.add_argument("--capture-after", action="store_true")
    subparsers.add_parser("capabilities", help="Report backend support without touching the desktop")
    subparsers.add_parser("schema", help="Print the machine-readable command reference")
    upgrade = subparsers.add_parser("upgrade", help="Check or install the latest stable GitHub release")
    upgrade.add_argument("--check", action="store_true", help="Check without installing")
    skill = subparsers.add_parser("skill", help="Install the bundled agent skill")
    skill.add_argument("action", choices=("install",))
    skill.add_argument("--agent", choices=("codex", "claude", "generic"), default="codex")
    skill.add_argument("--path", help="Explicit skill directory; must end with control-local-ui")
    return parser
