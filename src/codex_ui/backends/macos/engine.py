"""Native macOS implementation. Imported only when a desktop command runs.

The original tested orchestration stays together during the first public release.
Portable values, command grammar, browser payloads and lifecycle live separately.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence
try:
    import ApplicationServices as AS
    import Quartz
    from AppKit import (
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSBackingStoreBuffered,
        NSBitmapImageFileTypeJPEG,
        NSBitmapImageFileTypePNG,
        NSBitmapImageRep,
        NSColor,
        NSFont,
        NSImageCompressionFactor,
        NSMakeRect,
        NSPanel,
        NSPasteboard,
        NSPasteboardItem,
        NSPasteboardTypeString,
        NSRunningApplication,
        NSScreen,
        NSTextField,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorFullScreenAuxiliary,
        NSWindowSharingNone,
        NSWindowStyleMaskBorderless,
        NSWindowStyleMaskNonactivatingPanel,
    )
    from Foundation import NSDate, NSRunLoop
except ImportError as exc:  # pragma: no cover - exercised by doctor in practice
    raise ImportError(
        "Missing PyObjC frameworks. Reinstall codex-ui with its dependencies. "
        f"Import error: {exc}"
    ) from exc
from ..._version import __version__ as VERSION
from ...config import SCHEMA_VERSION, SCREENSHOTS_ROOT, RUNTIME_STATE_PATH
from ...models import (AXNode, AmbiguousTargetError, ChromeTabInfo, DisplayInfo, Rect,
                       ResolvedTarget, TargetSpec, UIControlError, WindowInfo,
                       friendly_action, friendly_role, json_value, normalize_role, text_matches)
from ...parser import WINDOW_PRESETS, build_parser
from .browser_scripts import (CHROME_ACTIVE_QUERY_JXA, CHROME_ACTIVATE_JXA,
                              CHROME_DEVELOPER_MENU_JXA, CHROME_QUERY_JXA)

TESSERACT = shutil.which("tesseract") or "/opt/homebrew/bin/tesseract"
EVENT_MAGIC = 0x434F4445585549  # "CODEXUI"
DEFAULT_USER_IDLE_SECONDS = 3.0
INDICATOR_SHOW_SECONDS = 0.10
INDICATOR_DONE_SECONDS = 0.45
DEVTOOLS_RESULT_PREFIX = "__CODEX_UI_RESULT__:"

def filter_windows(
    windows: Iterable[WindowInfo],
    *,
    app: str | None = None,
    title: str | None = None,
    pid: int | None = None,
) -> list[WindowInfo]:
    matches = []
    for window in windows:
        if pid is not None and window.pid != pid:
            continue
        if app and app.casefold() not in window.app.casefold():
            continue
        if title and title.casefold() not in window.title.casefold():
            continue
        matches.append(window)
    return matches


def select_occurrence(items: Sequence[Any], occurrence: int | None, description: str) -> Any:
    if not items:
        raise UIControlError(f"No {description} matched")
    if occurrence is not None:
        if occurrence < 1 or occurrence > len(items):
            raise UIControlError(
                f"{description} occurrence {occurrence} is out of range; {len(items)} matched"
            )
        return items[occurrence - 1]
    if len(items) > 1:
        raise AmbiguousTargetError(
            f"{len(items)} {description}s matched; add --occurrence or a narrower selector"
        )
    return items[0]


def list_displays() -> list[DisplayInfo]:
    error, display_ids, count = Quartz.CGGetActiveDisplayList(32, None, None)
    if error != Quartz.kCGErrorSuccess:
        raise UIControlError(f"Could not list displays (Quartz error {error})")
    displays: list[DisplayInfo] = []
    for index, display_id in enumerate(display_ids[:count], start=1):
        bounds = Quartz.CGDisplayBounds(display_id)
        displays.append(
            DisplayInfo(
                index=index,
                display_id=int(display_id),
                rect=Rect(
                    float(bounds.origin.x),
                    float(bounds.origin.y),
                    float(bounds.size.width),
                    float(bounds.size.height),
                ),
                pixel_width=int(Quartz.CGDisplayPixelsWide(display_id)),
                pixel_height=int(Quartz.CGDisplayPixelsHigh(display_id)),
                is_main=bool(Quartz.CGDisplayIsMain(display_id)),
            )
        )
    return displays


def list_windows(on_screen_only: bool = True) -> list[WindowInfo]:
    options = Quartz.kCGWindowListExcludeDesktopElements
    options |= (
        Quartz.kCGWindowListOptionOnScreenOnly
        if on_screen_only
        else Quartz.kCGWindowListOptionAll
    )
    rows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
    windows: list[WindowInfo] = []
    for z_index, row in enumerate(rows):
        try:
            rect = Rect.from_mapping(row[Quartz.kCGWindowBounds])
            app = str(row.get(Quartz.kCGWindowOwnerName, ""))
            if not app or rect.width < 20 or rect.height < 20:
                continue
            windows.append(
                WindowInfo(
                    window_id=int(row[Quartz.kCGWindowNumber]),
                    pid=int(row[Quartz.kCGWindowOwnerPID]),
                    app=app,
                    title=str(row.get(Quartz.kCGWindowName, "")),
                    rect=rect,
                    layer=int(row.get(Quartz.kCGWindowLayer, 0)),
                    z_index=z_index,
                    on_screen=bool(row.get(Quartz.kCGWindowIsOnscreen, False)),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return windows


def frontmost_pid() -> int:
    app = NSApplication.sharedApplication()
    del app
    workspace = __import__("AppKit").NSWorkspace.sharedWorkspace()
    frontmost = workspace.frontmostApplication()
    if frontmost is None:
        raise UIControlError("Could not determine the frontmost application")
    return int(frontmost.processIdentifier())


def query_chrome_tabs(*, active_only: bool = False) -> list[ChromeTabInfo]:
    result = subprocess.run(
        [
            "/usr/bin/osascript",
            "-l",
            "JavaScript",
            "-e",
            CHROME_ACTIVE_QUERY_JXA if active_only else CHROME_QUERY_JXA,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or "Unknown Chrome query error"
        if "-1743" in error:
            raise UIControlError(
                "macOS denied Chrome Automation access. Enable it under Privacy & Security > Automation"
            )
        raise UIControlError(f"Could not query Google Chrome: {error}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise UIControlError("Google Chrome returned invalid window data") from exc
    if not payload.get("running"):
        return []
    tabs: list[ChromeTabInfo] = []
    for row in payload.get("tabs", []):
        bounds = row["bounds"]
        tabs.append(
            ChromeTabInfo(
                window_index=int(row["windowIndex"]),
                tab_index=int(row["tabIndex"]),
                active_tab_index=int(row["activeTabIndex"]),
                title=str(row.get("title", "")),
                url=str(row.get("url", "")),
                rect=Rect(
                    float(bounds["x"]),
                    float(bounds["y"]),
                    float(bounds["width"]),
                    float(bounds["height"]),
                ),
                visible=bool(row.get("visible", True)),
                minimized=bool(row.get("minimized", False)),
                window_id=int(row["windowId"]) if row.get("windowId") is not None else None,
            )
        )
    return tabs


def select_chrome_tab(
    tabs: Sequence[ChromeTabInfo], url_match: str, occurrence: int | None = None
) -> ChromeTabInfo:
    matches = [tab for tab in tabs if url_match in tab.url]
    return select_occurrence(matches, occurrence, "Chrome tab")


def activate_chrome_tab(tab: ChromeTabInfo) -> None:
    result = subprocess.run(
        [
            "/usr/bin/osascript",
            "-l",
            "JavaScript",
            "-e",
            CHROME_ACTIVATE_JXA,
            str(tab.window_index),
            str(tab.tab_index),
            str(tab.window_id or 0),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise UIControlError(
            "Could not activate the Chrome tab: "
            + (result.stderr.strip() or "unknown JXA error")
        )
    try:
        selected = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise UIControlError("Chrome tab activation returned invalid verification data") from exc
    if int(selected.get("tabIndex", 0)) != tab.tab_index or selected.get("url") != tab.url:
        raise UIControlError(
            "Chrome activated a different tab than requested; refusing to continue "
            f"(requested {tab.url!r}, selected {selected.get('url')!r})"
        )
    time.sleep(0.12)


def activate_chrome_target(target: ResolvedTarget) -> None:
    """Activate a Chrome tab and bind the target to its actual Quartz window.

    Several Chrome windows can share identical bounds. Geometry alone cannot
    safely map an inactive tab to a Quartz window, so resolve that mapping only
    after Chrome has promoted the requested AppleScript window to the front.
    """
    if target.chrome_tab is None:
        raise UIControlError("Chrome activation requires a resolved Chrome tab")
    requested = target.chrome_tab
    activate_chrome_tab(requested)
    active_tabs = query_chrome_tabs(active_only=True)
    matches = [
        tab
        for tab in active_tabs
        if tab.url == requested.url
        and (
            requested.window_id is None
            or tab.window_id is None
            or tab.window_id == requested.window_id
        )
    ]
    selected = select_occurrence(matches, None, "activated Chrome tab")
    target.chrome_tab = selected
    app = AS.AXUIElementCreateApplication(target.window.pid)
    focused = ax_get(app, AS.kAXFocusedWindowAttribute)
    if focused is None:
        raise UIControlError("Chrome did not expose the activated window as focused")
    frame = ax_frame(focused)
    if frame is None:
        raise UIControlError("Chrome's activated window has no readable Accessibility frame")
    distance = sum(
        abs(left - right)
        for left, right in zip(frame.to_int_tuple(), selected.rect.to_int_tuple(), strict=True)
    )
    if distance > 12:
        raise UIControlError(
            "Chrome focused a window with different bounds than the requested tab; refusing to continue"
        )
    document = str(ax_get(focused, "AXDocument", "") or "")
    if document != selected.url:
        raise UIControlError(
            "Chrome's focused Accessibility window belongs to a different document; "
            f"refusing to continue (requested {selected.url!r}, focused {document!r})"
        )
    target.ax_window = focused
    target.window = replace(
        target.window,
        title=selected.title,
        rect=frame,
    )


def click_chrome_developer_menu(item_name: str) -> None:
    result = subprocess.run(
        [
            "/usr/bin/osascript",
            "-l",
            "JavaScript",
            "-e",
            CHROME_DEVELOPER_MENU_JXA,
            item_name,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return
    error = result.stderr.strip() or "unknown System Events error"
    if "-1743" in error or "not authorized" in error.casefold():
        raise UIControlError(
            "macOS denied UI access to Chrome's Developer menu. "
            "Enable Accessibility and Automation for the Codex terminal process"
        )
    raise UIControlError(f"Could not use Chrome's Developer menu: {error}")


def nearest_window_for_chrome(tab: ChromeTabInfo) -> WindowInfo:
    matches = []
    for window in list_windows(on_screen_only=False):
        if window.app != "Google Chrome" or window.layer != 0:
            continue
        distance = sum(
            abs(left - right)
            for left, right in zip(window.rect.to_int_tuple(), tab.rect.to_int_tuple(), strict=True)
        )
        if distance <= 12:
            matches.append((distance, window))
    if not matches:
        raise UIControlError("Chrome tab matched, but its macOS window could not be resolved")
    return sorted(matches, key=lambda item: (item[0], item[1].z_index))[0][1]


def target_from_args(args: argparse.Namespace) -> TargetSpec:
    return TargetSpec(
        window_id=getattr(args, "window_id", None),
        app=getattr(args, "app", None),
        title=getattr(args, "title", None),
        chrome_url=getattr(args, "chrome_url", None),
        frontmost=getattr(args, "frontmost", False),
        occurrence=getattr(args, "occurrence", None),
    )


def target_from_mapping(row: dict[str, Any] | None) -> TargetSpec:
    row = row or {}
    return TargetSpec(
        window_id=int(row["window_id"]) if row.get("window_id") is not None else None,
        app=row.get("app"),
        title=row.get("title"),
        chrome_url=row.get("chrome_url"),
        frontmost=bool(row.get("frontmost", False)),
        occurrence=int(row["occurrence"]) if row.get("occurrence") else None,
    )


def resolve_target(spec: TargetSpec, *, activate_chrome: bool = False) -> ResolvedTarget:
    if spec.chrome_url:
        active_tabs = query_chrome_tabs(active_only=True)
        active_matches = [tab for tab in active_tabs if spec.chrome_url in tab.url]
        if active_matches and spec.occurrence is None:
            tab = select_occurrence(active_matches, None, "active Chrome tab")
        else:
            tab = select_chrome_tab(query_chrome_tabs(), spec.chrome_url, spec.occurrence)
        target = ResolvedTarget(nearest_window_for_chrome(tab), tab)
        if activate_chrome:
            activate_chrome_target(target)
        return target

    windows = [window for window in list_windows() if window.layer == 0]
    using_frontmost = False
    if spec.window_id is not None:
        matches = [window for window in windows if window.window_id == spec.window_id]
    else:
        using_frontmost = spec.frontmost or not (spec.app or spec.title)
        pid = frontmost_pid() if using_frontmost else None
        matches = filter_windows(windows, app=spec.app, title=spec.title, pid=pid)
    if spec.window_id is None and using_frontmost and spec.occurrence is None and matches:
        window = matches[0]
    else:
        window = select_occurrence(matches, spec.occurrence, "window")
    return ResolvedTarget(window)


def display_for_rect(rect: Rect) -> DisplayInfo:
    matches = [display for display in list_displays() if display.rect.intersects(rect)]
    if not matches:
        return next(display for display in list_displays() if display.is_main)
    return max(
        matches,
        key=lambda display: max(0, min(rect.right, display.rect.right) - max(rect.x, display.rect.x))
        * max(0, min(rect.bottom, display.rect.bottom) - max(rect.y, display.rect.y)),
    )



def display_by_index(index: int) -> DisplayInfo:
    displays = list_displays()
    if index < 1 or index > len(displays):
        raise UIControlError(f"Display index must be between 1 and {len(displays)}")
    return displays[index - 1]


def preset_window_rect(current: Rect, preset: str, display: DisplayInfo, margin: float) -> Rect:
    if margin < 0:
        raise UIControlError("Window preset margin cannot be negative")
    usable = Rect(
        display.rect.x + margin,
        display.rect.y + margin,
        display.rect.width - 2 * margin,
        display.rect.height - 2 * margin,
    )
    if usable.width <= 0 or usable.height <= 0:
        raise UIControlError("Window preset margin leaves no usable display area")
    if preset == "maximize":
        return usable
    if preset == "center":
        return Rect(
            usable.x + (usable.width - current.width) / 2,
            usable.y + (usable.height - current.height) / 2,
            current.width,
            current.height,
        )
    half_width = usable.width / 2
    half_height = usable.height / 2
    presets = {
        "left-half": Rect(usable.x, usable.y, half_width, usable.height),
        "right-half": Rect(usable.x + half_width, usable.y, half_width, usable.height),
        "top-half": Rect(usable.x, usable.y, usable.width, half_height),
        "bottom-half": Rect(usable.x, usable.y + half_height, usable.width, half_height),
        "top-left": Rect(usable.x, usable.y, half_width, half_height),
        "top-right": Rect(usable.x + half_width, usable.y, half_width, half_height),
        "bottom-left": Rect(usable.x, usable.y + half_height, half_width, half_height),
        "bottom-right": Rect(
            usable.x + half_width,
            usable.y + half_height,
            half_width,
            half_height,
        ),
    }
    try:
        return presets[preset]
    except KeyError as exc:  # pragma: no cover - argparse normally constrains this
        raise UIControlError(f"Unsupported window preset {preset!r}") from exc


def requested_window_rect(
    current: Rect,
    *,
    position: Sequence[float] | None = None,
    size: Sequence[float] | None = None,
    bounds: Sequence[float] | None = None,
    preset: str | None = None,
    display_index: int | None = None,
    margin: float = 0.0,
) -> tuple[Rect, bool, bool]:
    if bounds is not None and (position is not None or size is not None or preset is not None):
        raise UIControlError("--bounds cannot be combined with --position, --size, or --preset")
    if preset is not None and (position is not None or size is not None):
        raise UIControlError("--preset cannot be combined with --position or --size")
    if bounds is None and preset is None and position is None and size is None:
        raise UIControlError("Provide --position, --size, --bounds, or --preset")
    if display_index is not None and preset is None:
        raise UIControlError("--display is only valid with --preset")
    if margin and preset is None:
        raise UIControlError("--margin is only valid with --preset")

    if bounds is not None:
        requested = Rect(*map(float, bounds))
        change_position = True
        change_size = True
    elif preset is not None:
        display = display_by_index(display_index) if display_index else display_for_rect(current)
        requested = preset_window_rect(current, preset, display, float(margin))
        change_position = True
        change_size = preset != "center"
    else:
        requested = Rect(
            float(position[0]) if position is not None else current.x,
            float(position[1]) if position is not None else current.y,
            float(size[0]) if size is not None else current.width,
            float(size[1]) if size is not None else current.height,
        )
        change_position = position is not None
        change_size = size is not None

    if requested.width <= 0 or requested.height <= 0:
        raise UIControlError("Window width and height must be greater than zero")
    return requested, change_position, change_size


def validate_window_visibility(rect: Rect, allow_partial: bool) -> None:
    covered_area = sum(rect.intersection_area(display.rect) for display in list_displays())
    minimum_visible_area = min(64.0, rect.width) * min(64.0, rect.height)
    if covered_area + 0.5 < minimum_visible_area:
        raise UIControlError("Requested bounds would leave less than 64x64 points visible")
    if not allow_partial and covered_area + 0.5 < rect.area:
        raise UIControlError(
            "Requested bounds extend outside the active displays; pass --allow-partial "
            "to keep at least 64x64 points visible"
        )


def rect_matches(
    actual: Rect,
    requested: Rect,
    *,
    position: bool,
    size: bool,
    tolerance: float = 2.0,
) -> bool:
    values: list[tuple[float, float]] = []
    if position:
        values.extend(((actual.x, requested.x), (actual.y, requested.y)))
    if size:
        values.extend(((actual.width, requested.width), (actual.height, requested.height)))
    return all(abs(left - right) <= tolerance for left, right in values)


def set_ax_window_rect(
    element: Any,
    rect: Rect,
    *,
    position: bool,
    size: bool,
) -> None:
    def set_value(attribute: str, value_type: int, value: Any, label: str) -> None:
        wrapped = AS.AXValueCreate(value_type, value)
        if wrapped is None:
            raise UIControlError(f"Could not encode requested window {label}")
        error = AS.AXUIElementSetAttributeValue(element, attribute, wrapped)
        if error != AS.kAXErrorSuccess:
            raise UIControlError(f"Could not set window {label} (Accessibility error {error})")

    if position:
        set_value(
            AS.kAXPositionAttribute,
            AS.kAXValueCGPointType,
            Quartz.CGPointMake(rect.x, rect.y),
            "position",
        )
    if size:
        set_value(
            AS.kAXSizeAttribute,
            AS.kAXValueCGSizeType,
            Quartz.CGSizeMake(rect.width, rect.height),
            "size",
        )
    if position and size:
        # Some applications shift a window while applying their minimum size.
        # Reapply the position so the final frame converges on the requested bounds.
        set_value(
            AS.kAXPositionAttribute,
            AS.kAXValueCGPointType,
            Quartz.CGPointMake(rect.x, rect.y),
            "position",
        )


def apply_window_rect(
    target: ResolvedTarget,
    requested: Rect,
    *,
    change_position: bool,
    change_size: bool,
    allow_constrained: bool,
) -> tuple[Rect, bool]:
    element = target.ax_window if target.ax_window is not None else ax_window_for(target.window)
    original = ax_frame(element)
    if original is None:
        raise UIControlError("Target window has no readable Accessibility frame")
    try:
        set_ax_window_rect(
            element,
            requested,
            position=change_position,
            size=change_size,
        )
        time.sleep(0.18)
        actual = ax_frame(element)
        if actual is None:
            raise UIControlError("Target window frame became unreadable after the change")
        validate_window_visibility(actual, allow_partial=True)
        constrained = not rect_matches(
            actual,
            requested,
            position=change_position,
            size=change_size,
        )
        if constrained and not allow_constrained:
            raise UIControlError(
                "Application constrained the requested geometry: "
                f"requested={requested.to_json()} actual={actual.to_json()}; "
                "pass --allow-constrained to accept the actual bounds"
            )
        return actual, constrained
    except Exception as error:
        rollback_error: Exception | None = None
        try:
            set_ax_window_rect(element, original, position=True, size=True)
            time.sleep(0.15)
            restored = ax_frame(element)
            if restored is None or not rect_matches(
                restored, original, position=True, size=True, tolerance=3.0
            ):
                raise UIControlError(
                    f"rollback ended at {restored.to_json() if restored else None}"
                )
        except Exception as restore_error:
            rollback_error = restore_error
        if rollback_error is not None:
            raise UIControlError(
                f"{error}; window geometry rollback also failed: {rollback_error}"
            ) from rollback_error
        raise


def update_target_rect(target: ResolvedTarget, rect: Rect) -> None:
    target.window = replace(target.window, rect=rect)
    if target.chrome_tab is not None:
        target.chrome_tab = replace(target.chrome_tab, rect=rect)


def ax_get(element: Any, attribute: str, default: Any = None) -> Any:
    try:
        error, value = AS.AXUIElementCopyAttributeValue(element, attribute, None)
    except Exception:
        return default
    return value if error == AS.kAXErrorSuccess else default


def ax_frame(element: Any) -> Rect | None:
    position = ax_get(element, AS.kAXPositionAttribute)
    size = ax_get(element, AS.kAXSizeAttribute)
    if position is None or size is None:
        return None
    ok_position, point = AS.AXValueGetValue(position, AS.kAXValueCGPointType, None)
    ok_size, dimensions = AS.AXValueGetValue(size, AS.kAXValueCGSizeType, None)
    if not ok_position or not ok_size:
        return None
    return Rect(float(point.x), float(point.y), float(dimensions.width), float(dimensions.height))


def ax_actions(element: Any) -> tuple[str, ...]:
    try:
        error, actions = AS.AXUIElementCopyActionNames(element, None)
    except Exception:
        return ()
    return tuple(str(action) for action in actions) if error == AS.kAXErrorSuccess else ()


def ax_window_for(window: WindowInfo) -> Any:
    app = AS.AXUIElementCreateApplication(window.pid)
    candidates = ax_get(app, AS.kAXWindowsAttribute, ()) or ()
    ranked: list[tuple[float, Any]] = []
    for candidate in candidates:
        frame = ax_frame(candidate)
        if frame is None:
            continue
        distance = sum(
            abs(left - right)
            for left, right in zip(frame.to_int_tuple(), window.rect.to_int_tuple(), strict=True)
        )
        title = str(ax_get(candidate, AS.kAXTitleAttribute, "") or "")
        if window.title and window.title.casefold() in title.casefold():
            distance -= 100
        ranked.append((distance, candidate))
    if not ranked:
        raise UIControlError(f"No Accessibility window was found for {window.app!r}")
    return min(ranked, key=lambda item: item[0])[1]


def activate_window(window: WindowInfo) -> None:
    running = NSRunningApplication.runningApplicationWithProcessIdentifier_(window.pid)
    if running is None:
        raise UIControlError(f"Application process {window.pid} is no longer running")
    options = 1 | 2  # NSApplicationActivateAllWindows | IgnoringOtherApps
    running.activateWithOptions_(options)
    ax_window = ax_window_for(window)
    error = AS.AXUIElementPerformAction(ax_window, AS.kAXRaiseAction)
    if error not in (AS.kAXErrorSuccess, AS.kAXErrorActionUnsupported):
        raise UIControlError(f"Could not raise window (Accessibility error {error})")
    time.sleep(0.10)


def traverse_ax(target: WindowInfo | ResolvedTarget, max_nodes: int = 8000) -> list[AXNode]:
    root = (
        target.ax_window
        if isinstance(target, ResolvedTarget) and target.ax_window is not None
        else ax_window_for(target.window if isinstance(target, ResolvedTarget) else target)
    )
    queue: deque[tuple[Any, AXNode | None, int]] = deque([(root, None, 0)])
    nodes: list[AXNode] = []
    while queue and len(nodes) < max_nodes:
        element, parent, depth = queue.popleft()
        node = AXNode(
            element=element,
            parent=parent,
            depth=depth,
            role=str(ax_get(element, AS.kAXRoleAttribute, "") or ""),
            subrole=str(ax_get(element, AS.kAXSubroleAttribute, "") or ""),
            title=str(ax_get(element, AS.kAXTitleAttribute, "") or ""),
            description=str(ax_get(element, AS.kAXDescriptionAttribute, "") or ""),
            value=ax_get(element, AS.kAXValueAttribute),
            enabled=bool(ax_get(element, AS.kAXEnabledAttribute, True)),
            frame=ax_frame(element),
            actions=ax_actions(element),
        )
        nodes.append(node)
        children = ax_get(element, AS.kAXChildrenAttribute, ()) or ()
        for child in children:
            queue.append((child, node, depth + 1))
    if queue:
        raise UIControlError(f"Accessibility tree exceeded the {max_nodes}-node safety limit")
    return nodes


def actionable_ancestor(node: AXNode) -> AXNode | None:
    current: AXNode | None = node
    while current is not None:
        if AS.kAXPressAction in current.actions:
            return current
        current = current.parent
    return None


def find_ax_nodes(
    nodes: Sequence[AXNode],
    *,
    name: str,
    role: str | None = None,
    contains: bool = False,
    actionable: bool = False,
) -> list[AXNode]:
    normalized_role = normalize_role(role)
    output: list[AXNode] = []
    seen_elements: set[str] = set()
    for node in nodes:
        candidates = [node.title, node.description]
        if isinstance(node.value, (str, int, float, bool)):
            candidates.append(str(node.value))
        if not any(text_matches(candidate, name, contains) for candidate in candidates if candidate):
            continue
        selected = actionable_ancestor(node) if actionable else node
        if selected is None:
            continue
        if normalized_role and normalize_role(selected.role) != normalized_role:
            continue
        identity = str(selected.element)
        if identity not in seen_elements:
            output.append(selected)
            seen_elements.add(identity)
    return output


DEVTOOLS_PANEL_NAMES = {
    "Elements",
    "Console",
    "Sources",
    "Network",
    "Performance",
    "Memory",
    "Application",
    "Security",
    "Lighthouse",
    "Recorder",
}


@dataclass(frozen=True)
class DevToolsState:
    was_open: bool
    active_panel: str | None


def devtools_state(nodes: Sequence[AXNode]) -> DevToolsState:
    panels = [
        node
        for node in nodes
        if node.subrole == "AXTabButton" and node.description in DEVTOOLS_PANEL_NAMES
    ]
    active = next((node.description for node in panels if bool(node.value)), None)
    return DevToolsState(bool(panels), active)


def console_prompt(nodes: Sequence[AXNode]) -> AXNode | None:
    return next(
        (
            node
            for node in nodes
            if node.role == "AXTextArea" and node.description == "Console prompt"
        ),
        None,
    )


def ensure_chrome_console(
    target: ResolvedTarget,
    initial_nodes: Sequence[AXNode] | None = None,
    initial_ocr_location: tuple[dict[str, Any], dict[str, Any]] | None = None,
) -> list[AXNode]:
    if target.chrome_tab is None:
        raise UIControlError("Chrome DevTools commands require --chrome-url")
    nodes = list(initial_nodes) if initial_nodes is not None else traverse_ax(target)
    if console_prompt(nodes) is not None:
        return nodes
    ocr_location = initial_ocr_location
    if ocr_location is None:
        # The menu bar can apply its Developer action to a different Chrome
        # window when several windows span multiple displays. Chrome's native
        # shortcut is delivered to the resolved front window.
        press_key_chord("option+cmd+j")
        for delay in (0.45, 0.80):
            time.sleep(delay)
            ocr_location = chrome_console_ocr_location(target)
            if ocr_location is not None:
                break
    if ocr_location is None:
        raise UIControlError("Chrome DevTools Console did not become visible")
    focus_chrome_console_ocr(ocr_location)
    nodes = traverse_ax(target)
    if console_prompt(nodes) is not None:
        return nodes
    # Current Chrome builds can render docked DevTools while omitting the
    # WebContents subtree from macOS Accessibility. The JavaScript Console menu
    # still focuses the prompt, so DOM/eval commands can use the guarded
    # keyboard fallback in evaluate_in_devtools.
    return nodes


def restore_devtools(target: ResolvedTarget, state: DevToolsState, keep_open: bool) -> None:
    if keep_open:
        return
    if not state.was_open:
        location = chrome_console_ocr_location(target)
        if location is None:
            raise UIControlError("Chrome DevTools could not be located for safe restoration")
        capture, match = location
        rect = match["pixel_rect"]
        _, toolbar_y = capture_pixel_to_screen(
            capture,
            rect["x"] + rect["width"] / 2,
            rect["y"] + rect["height"] / 2,
        )
        click_mouse(target.window.rect.right - 18, toolbar_y)
        time.sleep(0.30)
        if chrome_console_ocr_location(target) is not None:
            raise UIControlError("Chrome DevTools remained visible after its close control was pressed")
        return
    if not state.active_panel or state.active_panel == "Console":
        return
    panels = [
        node
        for node in traverse_ax(target)
        if node.subrole == "AXTabButton" and node.description == state.active_panel
    ]
    panel = select_occurrence(panels, None, f"DevTools {state.active_panel} panel")
    if panel.frame is None:
        raise UIControlError(f"DevTools {state.active_panel} panel has no accessible frame")
    click_mouse(*panel.frame.center)
    time.sleep(0.15)


def node_is_descendant(node: AXNode, ancestor: AXNode) -> bool:
    current = node.parent
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


def console_level(node: AXNode) -> str:
    classes = ax_get(node.element, "AXDOMClassList", ()) or ()
    for name in map(str, classes):
        match = re.fullmatch(r"console-([a-z]+)-level", name)
        if match:
            return match.group(1)
    return "unknown"


def console_source(node: AXNode, nodes: Sequence[AXNode]) -> str | None:
    source_pattern = re.compile(
        r"(?:file://[^\s]+|(?:[A-Za-z0-9_@.-]+/)*[A-Za-z0-9_@.-]+\.(?:js|mjs|cjs|ts|tsx|jsx|html|css)):\d+(?::\d+)?"
    )
    candidates: list[str] = []
    for child in nodes:
        if not node_is_descendant(child, node):
            continue
        for value in (child.title, child.description, child.value):
            if isinstance(value, str) and value:
                candidates.append(value)
    for value in candidates:
        match = source_pattern.search(value)
        if match:
            return match.group(0)
    return None


def collect_console_entries(
    nodes: Sequence[AXNode],
    *,
    search: str | None,
    level: str,
    limit: int,
) -> tuple[list[dict[str, Any]], int, int]:
    logs = [node for node in nodes if node.subrole == "AXApplicationLog"]
    output: list[dict[str, Any]] = []
    for node in logs:
        message = (node.description or node.name or str(node.value or "")).strip()
        entry_level = console_level(node)
        if level != "all" and entry_level != level:
            continue
        if search and search.casefold() not in message.casefold():
            continue
        output.append(
            {
                "level": entry_level,
                "message": message,
                "source": console_source(node, nodes),
            }
        )
    return output[:limit], len(logs), len(output)


def console_empty_levels_from_ocr_words(words: Sequence[dict[str, Any]]) -> set[str]:
    empty: set[str] = set()
    targets = {
        "error": "error",
        "warn": "warning",
        "info": "info",
        "verbose": "verbose",
        "messa": "message",
    }
    no_words = [word for word in words if word["text"].casefold().strip(".:") == "no"]
    for no_word in no_words:
        left = no_word["pixel_rect"]
        for word in words:
            right = word["pixel_rect"]
            if not 0 < right["x"] - left["x"] < 180:
                continue
            if abs(right["y"] - left["y"]) > 24:
                continue
            normalized = word["text"].casefold().strip(".:…")
            for prefix, level in targets.items():
                if normalized.startswith(prefix):
                    empty.add(level)
    return empty


def snapshot_clipboard() -> list[dict[str, Any]]:
    pasteboard = NSPasteboard.generalPasteboard()
    snapshot: list[dict[str, Any]] = []
    for item in pasteboard.pasteboardItems() or ():
        values: dict[str, Any] = {}
        for data_type in item.types() or ():
            data = item.dataForType_(data_type)
            if data is not None:
                values[str(data_type)] = data
        snapshot.append(values)
    return snapshot


def restore_clipboard(snapshot: Sequence[dict[str, Any]]) -> None:
    pasteboard = NSPasteboard.generalPasteboard()
    pasteboard.clearContents()
    items = []
    for values in snapshot:
        item = NSPasteboardItem.alloc().init()
        for data_type, data in values.items():
            item.setData_forType_(data, data_type)
        items.append(item)
    if items:
        pasteboard.writeObjects_(items)


def set_clipboard_text(value: str) -> None:
    pasteboard = NSPasteboard.generalPasteboard()
    pasteboard.clearContents()
    if not pasteboard.setString_forType_(value, NSPasteboardTypeString):
        raise UIControlError("Could not prepare clipboard text")


def devtools_eval_wrapper(expression: str) -> str:
    prefix = json.dumps(DEVTOOLS_RESULT_PREFIX)
    return f"""(() => {{
const prefix = {prefix};
const seen = new WeakSet();
const replacer = (_key, item) => {{
  if (typeof item === 'bigint') return `${{item}}n`;
  if (typeof item === 'function') return `[Function ${{item.name || 'anonymous'}}]`;
  if (typeof item === 'symbol') return String(item);
  if (typeof Element !== 'undefined' && item instanceof Element) return {{
    __type: 'Element', tag: item.tagName.toLowerCase(), id: item.id || null,
    classes: Array.from(item.classList), text: (item.innerText || item.textContent || '').trim().slice(0, 500)
  }};
  if (item && typeof item === 'object') {{
    if (seen.has(item)) return '[Circular]';
    seen.add(item);
  }}
  return item;
}};
try {{
  const value = ({expression});
  const encoded = JSON.stringify(value, replacer);
  copy(prefix + JSON.stringify({{ok: true, value: encoded === undefined ? {{__type: 'undefined'}} : JSON.parse(encoded)}}));
}} catch (error) {{
  copy(prefix + JSON.stringify({{ok: false, error: {{name: error.name, message: error.message, stack: error.stack || null}}}}));
}}
}})()"""


def evaluate_in_devtools(
    nodes: Sequence[AXNode],
    expression: str,
    context: "CommandContext",
    timeout: float,
) -> Any:
    prompt = console_prompt(nodes)
    clipboard = snapshot_clipboard()
    marker = f"{DEVTOOLS_RESULT_PREFIX}pending-{time.time_ns()}"
    try:
        set_clipboard_text(marker)
        source = devtools_eval_wrapper(expression)
        if prompt is not None and prompt.frame is not None:
            error = AS.AXUIElementSetAttributeValue(prompt.element, AS.kAXValueAttribute, source)
            if error != AS.kAXErrorSuccess:
                raise UIControlError(f"Could not fill the DevTools prompt (Accessibility error {error})")
            context.wait_for_user()
            click_mouse(*prompt.frame.center)
        else:
            context.wait_for_user()
            type_text(source, context.monitor, context.indicator)
        press_key_chord("enter")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = NSPasteboard.generalPasteboard().stringForType_(NSPasteboardTypeString)
            if isinstance(value, str) and value.startswith(DEVTOOLS_RESULT_PREFIX):
                if value == marker:
                    context.indicator.pump(0.03)
                    continue
                try:
                    payload = json.loads(value.removeprefix(DEVTOOLS_RESULT_PREFIX))
                except json.JSONDecodeError as exc:
                    raise UIControlError("DevTools returned malformed JSON") from exc
                if not payload.get("ok"):
                    detail = payload.get("error") or {}
                    raise UIControlError(
                        f"Chrome evaluation failed: {detail.get('name', 'Error')}: "
                        f"{detail.get('message', 'unknown error')}"
                    )
                return payload.get("value")
            context.indicator.pump(0.03)
        raise UIControlError(f"Chrome evaluation did not finish within {timeout:g} seconds")
    finally:
        restore_clipboard(clipboard)


def build_dom_expression(
    selector: str,
    *,
    depth: int,
    node_limit: int,
    text_limit: int,
    include_html: bool,
    html_limit: int,
    pierce_shadow: bool,
) -> str:
    return f"""(() => {{
const selector = {json.dumps(selector)};
const maxDepth = {depth};
const nodeLimit = {node_limit};
const textLimit = {text_limit};
const includeHTML = {str(include_html).lower()};
const htmlLimit = {html_limit};
const pierceShadow = {str(pierce_shadow).lower()};
let visited = 0;
let truncated = false;
const clip = (value, limit) => {{
  const text = String(value || '').trim().replace(/\\s+/g, ' ');
  return text.length > limit ? text.slice(0, limit) + '…' : text;
}};
const pathFor = (element) => {{
  if (element.id) return '#' + CSS.escape(element.id);
  const parts = [];
  let current = element;
  while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 6) {{
    let part = current.tagName.toLowerCase();
    const siblings = current.parentElement ? Array.from(current.parentElement.children).filter(node => node.tagName === current.tagName) : [];
    if (siblings.length > 1) part += `:nth-of-type(${{siblings.indexOf(current) + 1}})`;
    parts.unshift(part);
    current = current.parentElement;
  }}
  return parts.join(' > ');
}};
const visit = (element, currentDepth) => {{
  if (visited >= nodeLimit) {{ truncated = true; return null; }}
  visited += 1;
  const rect = element.getBoundingClientRect();
  const style = getComputedStyle(element);
  const attributes = Object.fromEntries(Array.from(element.attributes).map(attribute => [attribute.name, attribute.value]));
  const record = {{
    path: pathFor(element),
    tag: element.tagName.toLowerCase(),
    id: element.id || null,
    classes: Array.from(element.classList),
    attributes,
    text: clip(element.innerText || element.textContent, textLimit),
    rect: {{x: rect.x, y: rect.y, width: rect.width, height: rect.height}},
    visible: style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) !== 0 && rect.width > 0 && rect.height > 0,
    computed_style: {{display: style.display, visibility: style.visibility, opacity: style.opacity, color: style.color, background_color: style.backgroundColor, font_size: style.fontSize}},
    child_element_count: element.children.length,
    shadow_root: Boolean(element.shadowRoot),
  }};
  if (includeHTML) record.outer_html = clip(element.outerHTML, htmlLimit);
  if (currentDepth < maxDepth) {{
    const children = Array.from(element.children);
    if (pierceShadow && element.shadowRoot) children.push(...element.shadowRoot.querySelectorAll(':scope > *'));
    record.children = children.map(child => visit(child, currentDepth + 1)).filter(Boolean);
  }}
  return record;
}};
const matches = Array.from(document.querySelectorAll(selector));
const roots = [];
for (const element of matches) {{
  const record = visit(element, 0);
  if (record) roots.push(record);
  if (visited >= nodeLimit) break;
}}
return {{url: location.href, title: document.title, selector, matched_count: matches.length, visited_count: visited, truncated, roots}};
}})()"""


def press_ax(
    target: ResolvedTarget,
    *,
    name: str,
    role: str | None,
    contains: bool,
    occurrence: int | None,
) -> dict[str, Any]:
    nodes = traverse_ax(target)
    matches = find_ax_nodes(
        nodes, name=name, role=role, contains=contains, actionable=True
    )
    enabled_matches = [node for node in matches if node.enabled]
    node = select_occurrence(enabled_matches, occurrence, "Accessibility element")
    ancestor = node.parent
    in_web_content = False
    while ancestor is not None:
        if ancestor.role == "AXWebArea":
            in_web_content = True
            break
        ancestor = ancestor.parent
    if target.window.app == "Google Chrome" and in_web_content and node.frame is not None:
        # Chrome can acknowledge AXPress without dispatching an ordinary page
        # button's click handler. Use its semantic frame once, instead of trying
        # AXPress and risking a second activation when a handler is just slow.
        if "AXScrollToVisible" in node.actions:
            AS.AXUIElementPerformAction(node.element, "AXScrollToVisible")
            time.sleep(0.08)
        frame = ax_frame(node.element) or node.frame
        if not target.window.rect.contains(*frame.center):
            raise UIControlError("The semantic Chrome control is outside the visible target window")
        click_mouse(*frame.center)
        payload = node.to_json()
        payload["activation"] = "accessibility_frame_click"
        return payload
    original_value = node.value
    error = AS.AXUIElementPerformAction(node.element, AS.kAXPressAction)
    if error != AS.kAXErrorSuccess:
        raise UIControlError(f"AXPress failed with Accessibility error {error}")
    activation = "accessibility"
    if normalize_role(node.role) in {"radiobutton", "checkbox"} and not bool(original_value):
        time.sleep(0.12)
        updated_value = ax_get(node.element, AS.kAXValueAttribute)
        if not bool(updated_value) and node.frame is not None:
            # Chromium exposes local-file controls through Accessibility, but
            # some builds acknowledge AXPress without dispatching the page's
            # click handler. The AX-derived frame is still a precise semantic
            # target, so use it as the deterministic fallback.
            click_mouse(*node.frame.center)
            activation = "accessibility_frame_click"
            time.sleep(0.15)
    payload = node.to_json()
    payload["activation"] = activation
    return payload


class StatusIndicator:
    COLORS = {
        "observing": NSColor.colorWithCalibratedRed_green_blue_alpha_(0.18, 0.55, 1.0, 0.96),
        "controlling": NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.22, 0.18, 0.96),
        "paused": NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.62, 0.08, 0.98),
        "done": NSColor.colorWithCalibratedRed_green_blue_alpha_(0.20, 0.80, 0.40, 0.96),
        "error": NSColor.colorWithCalibratedRed_green_blue_alpha_(0.85, 0.16, 0.35, 0.98),
    }
    LABELS = {
        "observing": "CODEX OBSERVING",
        "controlling": "CODEX CONTROL",
        "paused": "CODEX PAUSED — USER ACTIVE",
        "done": "CODEX DONE",
        "error": "CODEX ERROR",
    }

    def __init__(self, target_rect: Rect, state: str) -> None:
        self.target_rect = target_rect
        self.state = state
        self.app = NSApplication.sharedApplication()
        self.app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        self.panels: list[Any] = []
        self.badge: Any | None = None
        self.label: Any | None = None
        self._create()

    def _cocoa_rect(self, rect: Rect, display: DisplayInfo, screen: Any) -> tuple[float, float, float, float]:
        screen_frame = screen.frame()
        local_x = rect.x - display.rect.x
        local_y = rect.y - display.rect.y
        cocoa_x = float(screen_frame.origin.x) + local_x
        cocoa_y = (
            float(screen_frame.origin.y)
            + display.rect.height
            - local_y
            - rect.height
        )
        return cocoa_x, cocoa_y, rect.width, rect.height

    def _screen_for_display(self, display: DisplayInfo) -> Any:
        for screen in NSScreen.screens():
            number = int(screen.deviceDescription().get("NSScreenNumber", -1))
            if number == display.display_id:
                return screen
        return NSScreen.mainScreen()

    def _panel(self, frame: tuple[float, float, float, float], color: Any) -> Any:
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(*frame),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        panel.setOpaque_(True)
        panel.setBackgroundColor_(color)
        panel.setIgnoresMouseEvents_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setHasShadow_(False)
        panel.setSharingType_(NSWindowSharingNone)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        panel.setLevel_(int(Quartz.CGWindowLevelForKey(Quartz.kCGStatusWindowLevelKey)))
        panel.orderFrontRegardless()
        return panel

    def _create(self) -> None:
        display = display_for_rect(self.target_rect)
        screen = self._screen_for_display(display)
        x, y, width, height = self._cocoa_rect(self.target_rect, display, screen)
        color = self.COLORS[self.state]
        thickness = 4.0
        frames = [
            (x, y, width, thickness),
            (x, y + height - thickness, width, thickness),
            (x, y, thickness, height),
            (x + width - thickness, y, thickness, height),
        ]
        self.panels = [self._panel(frame, color) for frame in frames]

        badge_width = 250.0 if self.state == "paused" else 172.0
        badge_frame = (x + 12, y + height - 42, badge_width, 30.0)
        self.badge = self._panel(badge_frame, color)
        label = NSTextField.labelWithString_(self.LABELS[self.state])
        label.setTextColor_(NSColor.whiteColor())
        label.setFont_(NSFont.boldSystemFontOfSize_(12.0))
        label.setAlignment_(1)
        label.setFrame_(NSMakeRect(6, 5, badge_width - 12, 19))
        self.badge.contentView().addSubview_(label)
        self.label = label
        self.pump(INDICATOR_SHOW_SECONDS)

    def pump(self, seconds: float = 0.01) -> None:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(seconds))
        self.app.updateWindows()

    def update(self, state: str) -> None:
        if state == self.state:
            self.pump(0.01)
            return
        self.state = state
        color = self.COLORS[state]
        for panel in self.panels:
            panel.setBackgroundColor_(color)
        if self.badge is not None:
            self.badge.setBackgroundColor_(color)
        if self.label is not None:
            self.label.setStringValue_(self.LABELS[state])
        self.pump(0.03)

    def retarget(self, target_rect: Rect) -> None:
        self.close()
        self.target_rect = target_rect
        self._create()

    def finish(self, success: bool = True) -> None:
        self.update("done" if success else "error")
        self.pump(INDICATOR_DONE_SECONDS if success else 0.70)
        self.close()

    def close(self) -> None:
        for panel in [*self.panels, self.badge]:
            if panel is not None:
                panel.orderOut_(None)
                panel.close()
        self.panels = []
        self.badge = None
        self.pump(0.01)


class UserActivityMonitor:
    EVENT_TYPES = (
        Quartz.kCGEventLeftMouseDown,
        Quartz.kCGEventLeftMouseUp,
        Quartz.kCGEventRightMouseDown,
        Quartz.kCGEventRightMouseUp,
        Quartz.kCGEventMouseMoved,
        Quartz.kCGEventLeftMouseDragged,
        Quartz.kCGEventRightMouseDragged,
        Quartz.kCGEventScrollWheel,
        Quartz.kCGEventKeyDown,
        Quartz.kCGEventKeyUp,
        Quartz.kCGEventFlagsChanged,
    )

    def __init__(self) -> None:
        seconds_since_input = float(
            Quartz.CGEventSourceSecondsSinceLastEventType(
                Quartz.kCGEventSourceStateCombinedSessionState,
                Quartz.kCGAnyInputEventType,
            )
        )
        recent_event_wall = time.time() - seconds_since_input
        last_agent_event_wall: float | None = None
        try:
            last_agent_event_wall = float(
                json.loads(RUNTIME_STATE_PATH.read_text()).get("last_agent_input_wall")
            )
        except (FileNotFoundError, TypeError, ValueError, json.JSONDecodeError):
            pass
        recent_event_was_agent = (
            last_agent_event_wall is not None
            and abs(recent_event_wall - last_agent_event_wall) < 0.75
        )
        self.last_user_input: float | None = None
        if seconds_since_input < DEFAULT_USER_IDLE_SECONDS and not recent_event_was_agent:
            self.last_user_input = time.monotonic() - seconds_since_input
        self._stop = threading.Event()
        self.pause_count = 0
        self._ready = threading.Event()
        self._error: Exception | None = None
        self._thread = threading.Thread(target=self._run, name="codex-ui-input-monitor", daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(1.0)
        if self._error:
            raise UIControlError(f"Could not monitor physical input: {self._error}")

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)

    def _callback(self, proxy: Any, event_type: int, event: Any, refcon: Any) -> Any:
        del proxy, event_type, refcon
        tag = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData)
        if int(tag) != EVENT_MAGIC:
            self.last_user_input = time.monotonic()
        return event

    def _run(self) -> None:
        try:
            mask = 0
            for event_type in self.EVENT_TYPES:
                mask |= Quartz.CGEventMaskBit(event_type)
            tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionListenOnly,
                mask,
                self._callback,
                None,
            )
            if tap is None:
                raise RuntimeError("CGEventTapCreate returned no event tap")
            source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            run_loop = Quartz.CFRunLoopGetCurrent()
            Quartz.CFRunLoopAddSource(run_loop, source, Quartz.kCFRunLoopDefaultMode)
            Quartz.CGEventTapEnable(tap, True)
            self._ready.set()
            while not self._stop.is_set():
                Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.05, False)
            Quartz.CGEventTapEnable(tap, False)
        except Exception as exc:  # pragma: no cover - depends on host permissions
            self._error = exc
            self._ready.set()

    def wait_until_idle(
        self,
        indicator: StatusIndicator,
        active_state: str,
        idle_seconds: float = DEFAULT_USER_IDLE_SECONDS,
    ) -> bool:
        paused = False
        while self.last_user_input is not None:
            remaining = idle_seconds - (time.monotonic() - self.last_user_input)
            if remaining <= 0:
                break
            if not paused:
                indicator.update("paused")
                paused = True
            indicator.pump(min(0.05, max(0.01, remaining)))
        if paused:
            self.pause_count += 1
            indicator.update(active_state)
        return paused


def tagged_event(event: Any) -> Any:
    Quartz.CGEventSetIntegerValueField(event, Quartz.kCGEventSourceUserData, EVENT_MAGIC)
    return event


def mouse_position() -> tuple[float, float]:
    event = Quartz.CGEventCreate(None)
    point = Quartz.CGEventGetLocation(event)
    return float(point.x), float(point.y)


def validate_point(x: float, y: float) -> None:
    if not any(display.rect.contains(x, y) for display in list_displays()):
        raise UIControlError(f"Point ({x}, {y}) is outside all active displays")


def post_mouse_event(event_type: int, x: float, y: float, button: int = 0) -> None:
    validate_point(x, y)
    event = tagged_event(
        Quartz.CGEventCreateMouseEvent(None, event_type, (float(x), float(y)), button)
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def move_mouse(x: float, y: float, duration: float = 0.0) -> None:
    start_x, start_y = mouse_position()
    steps = max(1, int(max(duration, 0.0) * 60))
    for index in range(1, steps + 1):
        fraction = index / steps
        post_mouse_event(
            Quartz.kCGEventMouseMoved,
            start_x + (x - start_x) * fraction,
            start_y + (y - start_y) * fraction,
        )
        if duration > 0:
            time.sleep(duration / steps)


def click_mouse(x: float, y: float, count: int = 1, button_name: str = "left") -> None:
    button_data = {
        "left": (Quartz.kCGMouseButtonLeft, Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp),
        "right": (Quartz.kCGMouseButtonRight, Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp),
    }
    button, down_type, up_type = button_data[button_name]
    move_mouse(x, y, duration=0.04)
    for click_count in range(1, count + 1):
        down = tagged_event(Quartz.CGEventCreateMouseEvent(None, down_type, (x, y), button))
        up = tagged_event(Quartz.CGEventCreateMouseEvent(None, up_type, (x, y), button))
        Quartz.CGEventSetIntegerValueField(down, Quartz.kCGMouseEventClickState, click_count)
        Quartz.CGEventSetIntegerValueField(up, Quartz.kCGMouseEventClickState, click_count)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        if count > 1:
            time.sleep(0.06)


def drag_mouse(start: tuple[float, float], end: tuple[float, float], duration: float) -> None:
    validate_point(*start)
    validate_point(*end)
    move_mouse(*start, duration=0.05)
    down = tagged_event(
        Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseDown, start, Quartz.kCGMouseButtonLeft
        )
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    steps = max(2, int(max(duration, 0.1) * 60))
    try:
        for index in range(1, steps + 1):
            fraction = index / steps
            point = (
                start[0] + (end[0] - start[0]) * fraction,
                start[1] + (end[1] - start[1]) * fraction,
            )
            post_mouse_event(
                Quartz.kCGEventLeftMouseDragged, *point, button=Quartz.kCGMouseButtonLeft
            )
            time.sleep(max(duration, 0.1) / steps)
    finally:
        up = tagged_event(
            Quartz.CGEventCreateMouseEvent(
                None, Quartz.kCGEventLeftMouseUp, end, Quartz.kCGMouseButtonLeft
            )
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def scroll_mouse(x: float, y: float, delta_x: int, delta_y: int) -> None:
    move_mouse(x, y, duration=0.03)
    event = tagged_event(
        Quartz.CGEventCreateScrollWheelEvent(
            None, Quartz.kCGScrollEventUnitPixel, 2, int(delta_y), int(delta_x)
        )
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


KEY_CODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
    "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29,
    "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "enter": 36,
    "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43,
    "/": 44, "n": 45, "m": 46, ".": 47, "tab": 48, "space": 49,
    "backspace": 51, "escape": 53, "left": 123, "right": 124, "down": 125,
    "up": 126, "delete": 117, "home": 115, "end": 119, "pageup": 116,
    "pagedown": 121, "f1": 122, "f2": 120, "f3": 99, "f4": 118,
    "f5": 96, "f6": 97, "f7": 98, "f8": 100, "f9": 101, "f10": 109,
    "f11": 103, "f12": 111,
}
MODIFIER_FLAGS = {
    "cmd": Quartz.kCGEventFlagMaskCommand,
    "command": Quartz.kCGEventFlagMaskCommand,
    "meta": Quartz.kCGEventFlagMaskCommand,
    "shift": Quartz.kCGEventFlagMaskShift,
    "ctrl": Quartz.kCGEventFlagMaskControl,
    "control": Quartz.kCGEventFlagMaskControl,
    "alt": Quartz.kCGEventFlagMaskAlternate,
    "option": Quartz.kCGEventFlagMaskAlternate,
}


def press_key_chord(chord: str) -> None:
    parts = [part.strip().casefold() for part in chord.replace("+", " ").split() if part.strip()]
    if not parts:
        raise UIControlError("Key chord is empty")
    modifiers = 0
    keys = []
    for part in parts:
        if part in MODIFIER_FLAGS:
            modifiers |= MODIFIER_FLAGS[part]
        else:
            keys.append(part)
    if len(keys) != 1 or keys[0] not in KEY_CODES:
        raise UIControlError(f"Unsupported key chord {chord!r}")
    keycode = KEY_CODES[keys[0]]
    down = tagged_event(Quartz.CGEventCreateKeyboardEvent(None, keycode, True))
    up = tagged_event(Quartz.CGEventCreateKeyboardEvent(None, keycode, False))
    Quartz.CGEventSetFlags(down, modifiers)
    Quartz.CGEventSetFlags(up, modifiers)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def type_text(text: str, monitor: UserActivityMonitor | None, indicator: StatusIndicator) -> None:
    if not text:
        return
    if monitor:
        monitor.wait_until_idle(indicator, "controlling")
    clipboard = snapshot_clipboard()
    try:
        set_clipboard_text(text)
        press_key_chord("cmd+v")
        # CGEventPost is asynchronous across processes. Keep the temporary
        # pasteboard value alive long enough for slower targets (notably Chrome
        # just after Command-L) to consume it before restoration.
        indicator.pump(0.4)
    finally:
        restore_clipboard(clipboard)


def capture_rect(
    rect: Rect,
    *,
    label: str | None = None,
    image_format: str = "jpg",
    quality: float = 0.92,
    target: ResolvedTarget | None = None,
) -> dict[str, Any]:
    SCREENSHOTS_ROOT.mkdir(parents=True, exist_ok=True)
    image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectMake(rect.x, rect.y, rect.width, rect.height),
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
        Quartz.kCGWindowImageDefault,
    )
    if image is None:
        raise UIControlError(
            "Screen capture failed. Check Privacy & Security > Screen & System Audio Recording"
        )
    pixel_width = int(Quartz.CGImageGetWidth(image))
    pixel_height = int(Quartz.CGImageGetHeight(image))
    if pixel_width <= 0 or pixel_height <= 0:
        raise UIControlError("Screen capture returned an empty image")

    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S.%f%z")
    safe_label = ""
    if label:
        normalized = "".join(char if char.isalnum() or char in "-_" else "-" for char in label)
        safe_label = f"__{normalized.strip('-')[:48]}" if normalized.strip("-") else ""
    x, y, width, height = rect.to_int_tuple()
    scale_x = pixel_width / rect.width
    scale_y = pixel_height / rect.height
    scale_label = f"{(scale_x + scale_y) / 2:.3f}".rstrip("0").rstrip(".")
    suffix = "jpg" if image_format == "jpg" else "png"
    filename = (
        f"screen_{timestamp}{safe_label}"
        f"__screen_xywh_{x}_{y}_{width}_{height}pt"
        f"__image_{pixel_width}x{pixel_height}px"
        f"__scale_{scale_label}x.{suffix}"
    )
    image_path = SCREENSHOTS_ROOT / filename
    rep = NSBitmapImageRep.alloc().initWithCGImage_(image)
    if image_format == "jpg":
        data = rep.representationUsingType_properties_(
            NSBitmapImageFileTypeJPEG, {NSImageCompressionFactor: float(quality)}
        )
    else:
        data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
    if data is None:
        raise UIControlError("Could not encode the captured image")
    image_path.write_bytes(bytes(data))

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "captured_at": datetime.now().astimezone().isoformat(),
        "path": str(image_path.resolve()),
        "format": image_format,
        "screen_rect_points": rect.to_json(),
        "image_size_pixels": {"width": pixel_width, "height": pixel_height},
        "scale": {"x": scale_x, "y": scale_y},
        "target": target.to_json() if target else None,
        "cursor_points": {"x": mouse_position()[0], "y": mouse_position()[1]},
    }
    metadata_path = image_path.with_suffix(image_path.suffix + ".json")
    metadata["metadata_path"] = str(metadata_path.resolve())
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return metadata


def load_capture_metadata(image_or_metadata_path: str) -> dict[str, Any]:
    path = Path(image_or_metadata_path).expanduser().resolve()
    candidates = [path]
    if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        candidates.insert(0, path.with_suffix(path.suffix + ".json"))
    for candidate in candidates:
        if candidate.exists() and candidate.suffix == ".json":
            return json.loads(candidate.read_text())
    raise UIControlError(f"No screenshot metadata sidecar was found for {path}")


def capture_pixel_to_screen(
    metadata: dict[str, Any], pixel_x: float, pixel_y: float
) -> tuple[float, float]:
    rect = metadata["screen_rect_points"]
    scale = metadata["scale"]
    return (
        float(rect["x"]) + pixel_x / float(scale["x"]),
        float(rect["y"]) + pixel_y / float(scale["y"]),
    )


def run_ocr(image_path: str, *, psm: int = 11) -> list[dict[str, Any]]:
    if not Path(TESSERACT).exists():
        raise UIControlError("Tesseract is unavailable; OCR fallback cannot run")
    result = subprocess.run(
        [TESSERACT, image_path, "stdout", "--psm", str(psm), "tsv"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise UIControlError("Tesseract failed: " + (result.stderr.strip() or "unknown error"))
    rows: list[dict[str, Any]] = []
    # OCR text is untrusted TSV data and frequently contains bare quote marks
    # from page copy. Treat quotes literally so one glyph cannot make the CSV
    # reader swallow the remaining lines into a single field.
    for row in csv.DictReader(
        io.StringIO(result.stdout), delimiter="\t", quoting=csv.QUOTE_NONE
    ):
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            confidence = float(row.get("conf", -1))
            rows.append(
                {
                    "text": text,
                    "confidence": confidence,
                    "line_key": ":".join(
                        str(row.get(name, ""))
                        for name in ("page_num", "block_num", "par_num", "line_num")
                    ),
                    "word_number": int(row.get("word_num", 0)),
                    "pixel_rect": {
                        "x": int(row["left"]),
                        "y": int(row["top"]),
                        "width": int(row["width"]),
                        "height": int(row["height"]),
                    },
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def ocr_text_matches(
    words: Sequence[dict[str, Any]], text: str, contains: bool
) -> list[dict[str, Any]]:
    direct = [word for word in words if text_matches(word["text"], text, contains)]
    if direct or len(text.split()) < 2:
        return direct
    groups: dict[str, list[dict[str, Any]]] = {}
    for word in words:
        groups.setdefault(str(word.get("line_key", "")), []).append(word)
    wanted_count = len(text.split())
    matches: list[dict[str, Any]] = []
    for line in groups.values():
        ordered = sorted(
            line,
            key=lambda word: (
                int(word.get("word_number", 0)),
                word["pixel_rect"]["x"],
            ),
        )
        for start in range(len(ordered)):
            spans = range(start + 1, len(ordered) + 1) if contains else [start + wanted_count]
            for end in spans:
                if end > len(ordered):
                    continue
                phrase = ordered[start:end]
                actual = " ".join(word["text"] for word in phrase)
                if not text_matches(actual, text, contains):
                    continue
                left = min(word["pixel_rect"]["x"] for word in phrase)
                top = min(word["pixel_rect"]["y"] for word in phrase)
                right = max(
                    word["pixel_rect"]["x"] + word["pixel_rect"]["width"]
                    for word in phrase
                )
                bottom = max(
                    word["pixel_rect"]["y"] + word["pixel_rect"]["height"]
                    for word in phrase
                )
                matches.append(
                    {
                        "text": actual,
                        "confidence": min(word["confidence"] for word in phrase),
                        "line_key": phrase[0].get("line_key", ""),
                        "word_number": phrase[0].get("word_number", 0),
                        "pixel_rect": {
                            "x": left,
                            "y": top,
                            "width": right - left,
                            "height": bottom - top,
                        },
                    }
                )
    return matches


def chrome_console_ocr_location(
    target: ResolvedTarget,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    capture = capture_rect(target.window.rect, label="devtools-probe", target=target)
    # Sparse-page mode misses Chrome's small, tightly packed DevTools tabs on
    # high-density displays. Uniform-block mode reads that toolbar reliably.
    words = run_ocr(capture["path"], psm=6)
    panels = [word for word in words if word["text"] in DEVTOOLS_PANEL_NAMES]
    if len({word["text"] for word in panels}) < 3:
        return None
    console_words = [word for word in panels if word["text"] == "Console"]
    if not console_words:
        return None
    return capture, max(console_words, key=lambda word: word["pixel_rect"]["y"])


def focus_chrome_console_ocr(
    location: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    capture, match = location
    rect = match["pixel_rect"]
    tab_x, tab_y = capture_pixel_to_screen(
        capture,
        rect["x"] + rect["width"] / 2,
        rect["y"] + rect["height"] / 2,
    )
    click_mouse(tab_x, tab_y)
    time.sleep(0.18)
    # The first console prompt row is consistently one DevTools toolbar below
    # the panel tab in both bottom- and side-docked layouts.
    click_mouse(tab_x, tab_y + 52)
    time.sleep(0.12)


def click_text_fallback(
    target: ResolvedTarget,
    text: str,
    *,
    contains: bool,
    occurrence: int | None,
) -> dict[str, Any]:
    capture = capture_rect(target.window.rect, label="ocr-target", target=target)
    words = run_ocr(capture["path"])
    matches = ocr_text_matches(words, text, contains)
    match = select_occurrence(matches, occurrence, "OCR text match")
    pixel_rect = match["pixel_rect"]
    screen_x, screen_y = capture_pixel_to_screen(
        capture,
        pixel_rect["x"] + pixel_rect["width"] / 2,
        pixel_rect["y"] + pixel_rect["height"] / 2,
    )
    click_mouse(screen_x, screen_y)
    return {
        "method": "ocr",
        "match": match,
        "screen_point": {"x": screen_x, "y": screen_y},
        "capture": capture,
    }


def point_from_args(args: argparse.Namespace, target: ResolvedTarget | None) -> tuple[float, float]:
    if getattr(args, "at", None):
        return float(args.at[0]), float(args.at[1])
    if getattr(args, "window_point", None):
        if target is None:
            raise UIControlError("--window-point requires a resolved target window")
        return (
            target.window.rect.x + float(args.window_point[0]),
            target.window.rect.y + float(args.window_point[1]),
        )
    if getattr(args, "normalized", None):
        if target is None:
            raise UIControlError("--normalized requires a resolved target window")
        nx, ny = map(float, args.normalized)
        if not (0 <= nx <= 1 and 0 <= ny <= 1):
            raise UIControlError("Normalized coordinates must be between 0 and 1")
        return (
            target.window.rect.x + target.window.rect.width * nx,
            target.window.rect.y + target.window.rect.height * ny,
        )
    if getattr(args, "pixel", None):
        if not getattr(args, "capture", None):
            raise UIControlError("--pixel requires --capture IMAGE_OR_METADATA")
        metadata = load_capture_metadata(args.capture)
        return capture_pixel_to_screen(metadata, float(args.pixel[0]), float(args.pixel[1]))
    raise UIControlError("Provide --at, --window-point, --normalized, or --capture with --pixel")


class CommandContext:
    def __init__(self, target: ResolvedTarget, state: str, monitor_user: bool = False) -> None:
        self.target = target
        self.state = state
        self.indicator = StatusIndicator(target.window.rect, state)
        self.monitor = UserActivityMonitor() if monitor_user else None
        self.original_pointer = mouse_position()
        self.success = False

    def __enter__(self) -> "CommandContext":
        if self.monitor:
            self.monitor.start()
        return self

    def wait_for_user(self) -> bool:
        if self.monitor:
            return self.monitor.wait_until_idle(self.indicator, self.state)
        return False

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        monitor_error: Exception | None = None
        restore_error: Exception | None = None
        try:
            if self.monitor:
                self.monitor.stop()
        except Exception as error:  # pragma: no cover - defensive host cleanup
            monitor_error = error
        if self.state == "controlling":
            try:
                move_mouse(*self.original_pointer, duration=0.05)
            except Exception as error:  # pragma: no cover - depends on display state
                restore_error = error
            try:
                RUNTIME_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                RUNTIME_STATE_PATH.write_text(
                    json.dumps({"last_agent_input_wall": time.time()}) + "\n"
                )
            except Exception:
                pass
        self.indicator.finish(
            success=exc is None and restore_error is None and monitor_error is None
        )
        cleanup_error = restore_error or monitor_error
        if cleanup_error is not None:
            detail = "Pointer restoration" if restore_error is not None else "Input monitor cleanup"
            if exc is not None:
                raise UIControlError(
                    f"{exc}; additionally, {detail.casefold()} failed: {cleanup_error}"
                ) from cleanup_error
            raise UIControlError(f"{detail} failed: {cleanup_error}") from cleanup_error



def doctor_payload() -> dict[str, Any]:
    screen_capture = False
    try:
        image = Quartz.CGWindowListCreateImage(
            Quartz.CGRectMake(0, 0, 1, 1),
            Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID,
            Quartz.kCGWindowImageDefault,
        )
        screen_capture = image is not None
    except Exception:
        pass
    return {
        "ok": bool(AS.AXIsProcessTrusted()) and screen_capture,
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "platform": platform.platform(),
        "python": sys.executable,
        "accessibility_trusted": bool(AS.AXIsProcessTrusted()),
        "screen_capture_available": screen_capture,
        "tesseract": TESSERACT if Path(TESSERACT).exists() else None,
        "displays": [display.to_json() for display in list_displays()],
        "launcher": shutil.which("codex-ui"),
        "skill_path": str(Path.home() / ".codex/skills/control-local-ui"),
    }


def after_capture(target: ResolvedTarget, enabled: bool, label: str = "after") -> dict[str, Any] | None:
    if not enabled:
        return None
    time.sleep(0.18)
    return capture_rect(target.window.rect, label=label, target=target)


def perform_window_change(
    target: ResolvedTarget,
    context: CommandContext,
    *,
    position: Sequence[float] | None = None,
    size: Sequence[float] | None = None,
    bounds: Sequence[float] | None = None,
    preset: str | None = None,
    display_index: int | None = None,
    margin: float = 0.0,
    allow_partial: bool = False,
    allow_constrained: bool = False,
) -> dict[str, Any]:
    original = target.window.rect
    requested, change_position, change_size = requested_window_rect(
        original,
        position=position,
        size=size,
        bounds=bounds,
        preset=preset,
        display_index=display_index,
        margin=margin,
    )
    validate_window_visibility(requested, allow_partial)
    actual, constrained = apply_window_rect(
        target,
        requested,
        change_position=change_position,
        change_size=change_size,
        allow_constrained=allow_constrained,
    )
    update_target_rect(target, actual)
    context.indicator.retarget(actual)
    return {
        "original_bounds": original.to_json(),
        "requested_bounds": requested.to_json(),
        "actual_bounds": actual.to_json(),
        "position_changed": change_position,
        "size_changed": change_size,
        "constrained_by_application": constrained,
    }


def execute_chrome_inspection(
    args: argparse.Namespace, target: ResolvedTarget
) -> dict[str, Any]:
    if target.chrome_tab is None:
        raise UIControlError("Chrome inspection commands require --chrome-url")
    if getattr(args, "limit", 1) < 1:
        raise UIControlError("--limit must be at least 1")
    if getattr(args, "timeout", 1.0) <= 0:
        raise UIControlError("--timeout must be greater than 0")
    if args.command == "chrome-dom":
        if not 0 <= args.depth <= 10:
            raise UIControlError("--depth must be between 0 and 10")
        for name in ("node_limit", "text_limit", "html_limit"):
            if getattr(args, name) < 1:
                raise UIControlError(f"--{name.replace('_', '-')} must be at least 1")

    result: dict[str, Any]
    capture: dict[str, Any] | None = None
    initial_state: DevToolsState | None = None
    with CommandContext(target, "controlling", monitor_user=True) as context:
        context.wait_for_user()
        activate_chrome_target(target)
        context.wait_for_user()
        initial_nodes = traverse_ax(target)
        initial_state = devtools_state(initial_nodes)
        initial_ocr_location = None
        if not initial_state.was_open:
            initial_ocr_location = chrome_console_ocr_location(target)
            if initial_ocr_location is not None:
                initial_state = DevToolsState(was_open=True, active_panel=None)
        try:
            nodes = ensure_chrome_console(
                target,
                initial_nodes,
                initial_ocr_location=initial_ocr_location,
            )
            context.wait_for_user()
            if args.command == "chrome-console":
                if console_prompt(nodes) is None:
                    console_capture = capture_rect(
                        target.window.rect,
                        label="chrome-console-ocr",
                        target=target,
                    )
                    # The docked Console's compact level labels are another
                    # uniform UI block; sparse OCR drops them on Retina.
                    empty_levels = console_empty_levels_from_ocr_words(
                        run_ocr(console_capture["path"], psm=6)
                    )
                    requested_level = "message" if args.level == "all" else args.level
                    if requested_level not in empty_levels:
                        raise UIControlError(
                            "Chrome DevTools Console rows are not exposed by macOS "
                            "Accessibility, and OCR could not prove the requested level is empty"
                        )
                    result = {
                        "scope": "visible_ocr_summary",
                        "entries": [],
                        "visible_entry_count": 0,
                        "matched_count": 0,
                        "truncated": False,
                        "empty_levels": sorted(empty_levels),
                        "capture": console_capture,
                    }
                else:
                    entries, visible_count, matched_count = collect_console_entries(
                        nodes,
                        search=args.search,
                        level=args.level,
                        limit=args.limit,
                    )
                    result = {
                        "scope": "visible_accessibility_rows",
                        "entries": entries,
                        "visible_entry_count": visible_count,
                        "matched_count": matched_count,
                        "truncated": matched_count > len(entries),
                    }
            elif args.command == "chrome-dom":
                expression = build_dom_expression(
                    args.selector,
                    depth=args.depth,
                    node_limit=args.node_limit,
                    text_limit=args.text_limit,
                    include_html=args.include_html,
                    html_limit=args.html_limit,
                    pierce_shadow=args.pierce_shadow,
                )
                result = {
                    "dom": evaluate_in_devtools(nodes, expression, context, args.timeout)
                }
            elif args.command == "chrome-eval":
                result = {
                    "value": evaluate_in_devtools(
                        nodes, args.expression, context, args.timeout
                    )
                }
            else:  # pragma: no cover - caller constrains this branch
                raise UIControlError(f"Unsupported Chrome inspection command {args.command}")
            capture = after_capture(target, args.capture_after, f"after-{args.command}")
        finally:
            context.wait_for_user()
            restore_devtools(target, initial_state, args.keep_open)
        pause_count = context.monitor.pause_count if context.monitor else 0
    return {
        "target": target.to_json(),
        "result": result,
        "capture": capture,
        "devtools": {
            "was_open": initial_state.was_open,
            "original_panel": initial_state.active_panel,
            "kept_open": bool(args.keep_open or initial_state.was_open),
        },
        "collision_pauses": pause_count,
        "pointer_restored": True,
    }


def execute_plan(plan: dict[str, Any], capture_after: bool) -> dict[str, Any]:
    if int(plan.get("schema_version", 0)) != SCHEMA_VERSION:
        raise UIControlError(f"Plan schema_version must be {SCHEMA_VERSION}")
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        raise UIControlError("Plan actions must be a non-empty list")
    target_spec = target_from_mapping(plan.get("target"))
    target = resolve_target(target_spec)
    results: list[dict[str, Any]] = []
    with CommandContext(target, "controlling", monitor_user=True) as context:
        context.wait_for_user()
        if target.chrome_tab is not None:
            activate_chrome_target(target)
        else:
            activate_window(target.window)
        context.wait_for_user()
        for index, action in enumerate(actions):
            if not isinstance(action, dict) or not isinstance(action.get("type"), str):
                raise UIControlError(f"Action {index + 1} must be an object with a type")
            action_type = action["type"].replace("-", "_")
            context.wait_for_user()
            if action_type == "press":
                result = press_ax(
                    target,
                    name=str(action["name"]),
                    role=action.get("role"),
                    contains=bool(action.get("contains", False)),
                    occurrence=action.get("occurrence"),
                )
            elif action_type == "click_text":
                try:
                    result = {
                        "method": "accessibility",
                        "element": press_ax(
                            target,
                            name=str(action["text"]),
                            role=action.get("role"),
                            contains=bool(action.get("contains", False)),
                            occurrence=action.get("occurrence"),
                        ),
                    }
                except UIControlError:
                    result = click_text_fallback(
                        target,
                        str(action["text"]),
                        contains=bool(action.get("contains", False)),
                        occurrence=action.get("occurrence"),
                    )
            elif action_type == "click":
                x, y = map(float, action["at"])
                click_mouse(x, y, int(action.get("count", 1)), str(action.get("button", "left")))
                result = {"screen_point": {"x": x, "y": y}}
            elif action_type == "move":
                x, y = map(float, action["at"])
                move_mouse(x, y, float(action.get("duration", 0.05)))
                result = {"screen_point": {"x": x, "y": y}}
            elif action_type == "drag":
                start = tuple(map(float, action["from"]))
                end = tuple(map(float, action["to"]))
                drag_mouse(start, end, float(action.get("duration", 0.4)))
                result = {"from": start, "to": end}
            elif action_type == "scroll":
                point = tuple(map(float, action.get("at", target.window.rect.center)))
                scroll_mouse(*point, int(action.get("delta_x", 0)), int(action["delta_y"]))
                result = {"screen_point": point}
            elif action_type == "type":
                type_text(str(action["text"]), context.monitor, context.indicator)
                result = {"characters": len(str(action["text"]))}
            elif action_type == "key":
                press_key_chord(str(action["chord"]))
                result = {"chord": str(action["chord"])}
            elif action_type == "window_set":
                result = perform_window_change(
                    target,
                    context,
                    position=action.get("position"),
                    size=action.get("size"),
                    bounds=action.get("bounds"),
                    preset=action.get("preset"),
                    display_index=action.get("display"),
                    margin=float(action.get("margin", 0.0)),
                    allow_partial=bool(action.get("allow_partial", False)),
                    allow_constrained=bool(action.get("allow_constrained", False)),
                )
            elif action_type == "wait":
                seconds = float(action.get("seconds", 0))
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    context.wait_for_user()
                    context.indicator.pump(min(0.05, deadline - time.monotonic()))
                result = {"seconds": seconds}
            elif action_type == "capture":
                context.indicator.update("observing")
                result = capture_rect(
                    target.window.rect,
                    label=action.get("label", f"step-{index + 1}"),
                    target=target,
                )
                context.indicator.update("controlling")
            else:
                raise UIControlError(f"Unsupported plan action type {action['type']!r}")
            results.append({"index": index + 1, "type": action["type"], "result": result})
        final_capture = after_capture(target, capture_after, "after-plan")
        pause_count = context.monitor.pause_count if context.monitor else 0
    return {
        "target": target.to_json(),
        "actions": results,
        "capture": final_capture,
        "collision_pauses": pause_count,
        "pointer_restored": True,
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    command = args.command
    if command == "doctor":
        return doctor_payload()
    if command == "displays":
        displays = list_displays()
        main = next(display for display in displays if display.is_main)
        indicator = StatusIndicator(main.rect, "observing")
        try:
            return {"displays": [display.to_json() for display in displays]}
        finally:
            indicator.finish()
    if command == "windows":
        items = filter_windows(
            [window for window in list_windows(not args.all) if window.layer == 0],
            app=args.app,
            title=args.title,
        )
        rect = items[0].rect if items else next(display.rect for display in list_displays() if display.is_main)
        indicator = StatusIndicator(rect, "observing")
        try:
            return {"windows": [window.to_json() for window in items]}
        finally:
            indicator.finish()
    if command == "open":
        main = next(display for display in list_displays() if display.is_main)
        indicator = StatusIndicator(main.rect, "controlling")
        monitor = UserActivityMonitor()
        try:
            monitor.start()
            monitor.wait_until_idle(indicator, "controlling")
            result = subprocess.run(
                ["/usr/bin/open", "-a", args.application, args.url],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise UIControlError(result.stderr.strip() or "open failed")
            time.sleep(max(0, args.wait))
            target = resolve_target(
                TargetSpec(app=args.application, frontmost=True, occurrence=1)
            )
            indicator.finish(True)
        except Exception:
            indicator.finish(False)
            raise
        finally:
            monitor.stop()
        return {
            "url": args.url,
            "application": args.application,
            "target": target.to_json(),
            "collision_pauses": monitor.pause_count,
        }
    if command == "run":
        raw = Path(args.plan_file).read_text() if args.plan_file else args.plan
        try:
            plan = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UIControlError(f"Invalid JSON plan: {exc}") from exc
        if not isinstance(plan, dict):
            raise UIControlError("Plan must be a JSON object")
        return execute_plan(plan, args.capture_after)

    if command == "capture" and (args.region or args.display):
        if args.region:
            rect = Rect(*map(float, args.region))
        else:
            displays = list_displays()
            if args.display < 1 or args.display > len(displays):
                raise UIControlError(f"Display index must be between 1 and {len(displays)}")
            rect = displays[args.display - 1].rect
        indicator = StatusIndicator(rect, "observing")
        try:
            result = capture_rect(
                rect,
                label=args.label,
                image_format=args.format,
                quality=args.quality,
            )
            indicator.finish(True)
            return {"capture": result}
        except Exception:
            indicator.finish(False)
            raise

    target_spec = target_from_args(args)
    target = resolve_target(target_spec)

    if command in {"chrome-console", "chrome-dom", "chrome-eval"}:
        return execute_chrome_inspection(args, target)

    if command == "focus":
        with CommandContext(target, "controlling", monitor_user=True) as context:
            context.wait_for_user()
            if target.chrome_tab is not None:
                activate_chrome_target(target)
            else:
                activate_window(target.window)
            pause_count = context.monitor.pause_count if context.monitor else 0
        return {
            "target": target.to_json(),
            "collision_pauses": pause_count,
            "pointer_restored": True,
        }

    if command == "window-set":
        with CommandContext(target, "controlling", monitor_user=True) as context:
            context.wait_for_user()
            if target.chrome_tab is not None:
                activate_chrome_target(target)
            else:
                activate_window(target.window)
            context.wait_for_user()
            result = perform_window_change(
                target,
                context,
                position=args.position,
                size=args.size,
                bounds=args.bounds,
                preset=args.preset,
                display_index=args.display,
                margin=args.margin,
                allow_partial=args.allow_partial,
                allow_constrained=args.allow_constrained,
            )
            capture = after_capture(target, args.capture_after, "after-window-set")
            pause_count = context.monitor.pause_count if context.monitor else 0
        return {
            "target": target.to_json(),
            "result": result,
            "capture": capture,
            "collision_pauses": pause_count,
            "pointer_restored": True,
        }

    if command == "capture":
        if args.region:
            rect = Rect(*map(float, args.region))
            capture_target = None
        elif args.display:
            displays = list_displays()
            if args.display < 1 or args.display > len(displays):
                raise UIControlError(f"Display index must be between 1 and {len(displays)}")
            rect = displays[args.display - 1].rect
            capture_target = None
        else:
            if args.focus:
                if target.chrome_tab:
                    activate_chrome_target(target)
                else:
                    activate_window(target.window)
            rect = target.window.rect
            capture_target = target
        indicator = StatusIndicator(rect, "observing")
        try:
            return {
                "capture": capture_rect(
                    rect,
                    label=args.label,
                    image_format=args.format,
                    quality=args.quality,
                    target=capture_target,
                )
            }
        except Exception:
            indicator.finish(False)
            raise
        finally:
            if indicator.panels:
                indicator.finish(True)

    if command == "inspect":
        if args.focus:
            if target.chrome_tab:
                activate_chrome_target(target)
            else:
                activate_window(target.window)
        indicator = StatusIndicator(target.window.rect, "observing")
        try:
            nodes = traverse_ax(target)
            output = []
            for node in nodes:
                if not args.all and not node.actions:
                    continue
                if args.search:
                    haystack = " ".join((node.title, node.description, str(json_value(node.value))))
                    if args.search.casefold() not in haystack.casefold():
                        continue
                output.append(node.to_json())
                if len(output) >= args.limit:
                    break
            return {"target": target.to_json(), "elements": output, "total_nodes": len(nodes)}
        finally:
            indicator.finish()

    with CommandContext(target, "controlling", monitor_user=True) as context:
        context.wait_for_user()
        if target.chrome_tab is not None:
            activate_chrome_target(target)
        else:
            activate_window(target.window)
        context.wait_for_user()
        capture_after_enabled = getattr(args, "capture_after", False)
        if command == "press":
            result = {
                "method": "accessibility",
                "element": press_ax(
                    target,
                    name=args.name,
                    role=args.role,
                    contains=args.contains,
                    occurrence=args.element_occurrence,
                ),
            }
        elif command == "click-text":
            try:
                result = {
                    "method": "accessibility",
                    "element": press_ax(
                        target,
                        name=args.text,
                        role=args.role,
                        contains=args.contains,
                        occurrence=args.element_occurrence,
                    ),
                }
            except UIControlError:
                result = click_text_fallback(
                    target,
                    args.text,
                    contains=args.contains,
                    occurrence=args.element_occurrence,
                )
        elif command in {"click", "double-click", "move"}:
            point = point_from_args(args, target)
            if command == "move":
                move_mouse(*point, duration=0.08)
            else:
                click_mouse(*point, count=2 if command == "double-click" else 1, button_name=args.button)
            result = {"screen_point": {"x": point[0], "y": point[1]}}
        elif command == "drag":
            drag_mouse(tuple(args.start), tuple(args.end), args.duration)
            result = {"from": args.start, "to": args.end, "duration": args.duration}
        elif command == "scroll":
            try:
                point = point_from_args(args, target)
            except UIControlError:
                point = target.window.rect.center
            scroll_mouse(*point, args.delta_x, args.delta_y)
            result = {"screen_point": point, "delta_x": args.delta_x, "delta_y": args.delta_y}
        elif command == "type":
            type_text(args.text, context.monitor, context.indicator)
            result = {"characters": len(args.text)}
        elif command == "key":
            press_key_chord(args.chord)
            result = {"chord": args.chord}
        else:  # pragma: no cover - argparse constrains this branch
            raise UIControlError(f"Unsupported command {command}")
        capture = after_capture(target, capture_after_enabled)
        pause_count = context.monitor.pause_count if context.monitor else 0
    return {
        "target": target.to_json(),
        "result": result,
        "capture": capture,
        "collision_pauses": pause_count,
        "pointer_restored": True,
    }
