"""Portable screen geometry, target contracts, and semantic node values."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

class UIControlError(RuntimeError):
    """A predictable command failure suitable for structured output."""


class AmbiguousTargetError(UIControlError):
    """More than one target matched a fail-closed selector."""


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.right and self.y <= y <= self.bottom

    def intersects(self, other: "Rect") -> bool:
        return not (
            self.right <= other.x
            or other.right <= self.x
            or self.bottom <= other.y
            or other.bottom <= self.y
        )

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def intersection_area(self, other: "Rect") -> float:
        width = max(0.0, min(self.right, other.right) - max(self.x, other.x))
        height = max(0.0, min(self.bottom, other.bottom) - max(self.y, other.y))
        return width * height

    def to_int_tuple(self) -> tuple[int, int, int, int]:
        return tuple(int(round(value)) for value in (self.x, self.y, self.width, self.height))

    def to_json(self) -> dict[str, int | float]:
        values = self.to_int_tuple()
        return dict(zip(("x", "y", "width", "height"), values, strict=True))

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "Rect":
        return cls(float(row["X"]), float(row["Y"]), float(row["Width"]), float(row["Height"]))


@dataclass(frozen=True)
class DisplayInfo:
    index: int
    display_id: int
    rect: Rect
    pixel_width: int
    pixel_height: int
    is_main: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "display_id": self.display_id,
            "rect_points": self.rect.to_json(),
            "pixel_size": {"width": self.pixel_width, "height": self.pixel_height},
            "is_main": self.is_main,
        }


@dataclass(frozen=True)
class WindowInfo:
    window_id: int
    pid: int
    app: str
    title: str
    rect: Rect
    layer: int
    z_index: int
    on_screen: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "pid": self.pid,
            "app": self.app,
            "title": self.title,
            "rect_points": self.rect.to_json(),
            "layer": self.layer,
            "z_index": self.z_index,
            "on_screen": self.on_screen,
        }


@dataclass(frozen=True)
class ChromeTabInfo:
    window_index: int
    tab_index: int
    active_tab_index: int
    title: str
    url: str
    rect: Rect
    visible: bool
    minimized: bool
    window_id: int | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "window_index": self.window_index,
            "tab_index": self.tab_index,
            "active_tab_index": self.active_tab_index,
            "chrome_window_id": self.window_id,
            "title": self.title,
            "url": self.url,
            "rect_points": self.rect.to_json(),
            "visible": self.visible,
            "minimized": self.minimized,
        }


@dataclass(frozen=True)
class TargetSpec:
    window_id: int | None = None
    app: str | None = None
    title: str | None = None
    chrome_url: str | None = None
    frontmost: bool = False
    occurrence: int | None = None


@dataclass
class ResolvedTarget:
    window: WindowInfo
    chrome_tab: ChromeTabInfo | None = None
    ax_window: Any | None = None

    def to_json(self) -> dict[str, Any]:
        payload = {"window": self.window.to_json()}
        if self.chrome_tab is not None:
            payload["chrome_tab"] = self.chrome_tab.to_json()
        return payload


@dataclass
class AXNode:
    element: Any
    parent: "AXNode | None"
    depth: int
    role: str
    subrole: str
    title: str
    description: str
    value: Any
    enabled: bool
    frame: Rect | None
    actions: tuple[str, ...]

    @property
    def name(self) -> str:
        for value in (self.title, self.description):
            if value:
                return value
        if isinstance(self.value, (str, int, float, bool)):
            return str(self.value)
        return ""

    def to_json(self) -> dict[str, Any]:
        return {
            "role": friendly_role(self.role),
            "ax_role": self.role,
            "subrole": self.subrole or None,
            "name": self.name,
            "title": self.title or None,
            "description": self.description or None,
            "value": json_value(self.value),
            "enabled": self.enabled,
            "frame_points": self.frame.to_json() if self.frame else None,
            "actions": [friendly_action(action) for action in self.actions],
            "ax_actions": list(self.actions),
            "depth": self.depth,
        }

def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value[:100]]
    return str(value)


def friendly_role(role: str) -> str:
    role = role.removeprefix("AX")
    output: list[str] = []
    for index, char in enumerate(role):
        if index and char.isupper() and role[index - 1].islower():
            output.append("_")
        output.append(char.lower())
    return "".join(output)


def friendly_action(action: str) -> str:
    return friendly_role(action)


def normalize_role(role: str | None) -> str | None:
    if role is None:
        return None
    normalized = role.casefold()
    if normalized.startswith("ax"):
        normalized = normalized[2:]
    return "".join(character for character in normalized if character.isalnum())


def text_matches(actual: str, wanted: str, contains: bool = False) -> bool:
    actual_folded = actual.strip().casefold()
    wanted_folded = wanted.strip().casefold()
    return wanted_folded in actual_folded if contains else actual_folded == wanted_folded
