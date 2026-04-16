"""Region schema and hit-testing.

Regions are defined as normalised rectangles (0-1 range) over the device
surface. A profile lists regions that map touches to actions (button clicks,
MIDI notes, etc.). Hit-testing resolves a contact's (x_mm, y_mm) position
against the active region list.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .device import SensorInfo


@dataclass(frozen=True, slots=True)
class Rect:
    """Axis-aligned rectangle in normalised coordinates (0-1)."""

    x: float
    y: float
    w: float
    h: float

    def contains(self, nx: float, ny: float) -> bool:
        return self.x <= nx < self.x + self.w and self.y <= ny < self.y + self.h


@dataclass(frozen=True, slots=True)
class Region:
    """A named, rectangular region on the device surface."""

    name: str
    rect: Rect
    action: dict = field(default_factory=dict)

    def hit(self, x_mm: float, y_mm: float, info: SensorInfo) -> bool:
        nx = x_mm / info.width_mm
        ny = y_mm / info.height_mm
        return self.rect.contains(nx, ny)


def regions_from_yaml(data: dict) -> list[Region]:
    """Parse a list of region dicts from a YAML profile.

    Each entry must have ``name`` and ``rect`` (with x, y, w, h).
    An optional ``action`` dict is carried through unchanged.
    """
    out: list[Region] = []
    for entry in data.get("regions", []):
        r = entry["rect"]
        out.append(
            Region(
                name=entry["name"],
                rect=Rect(
                    x=float(r["x"]), y=float(r["y"]), w=float(r["w"]), h=float(r["h"])
                ),
                action=entry.get("action", {}),
            )
        )
    return out


def find_region(
    x_mm: float, y_mm: float, info: SensorInfo, regions: list[Region]
) -> Region | None:
    """Return the first region that contains the given point, or None."""
    for region in regions:
        if region.hit(x_mm, y_mm, info):
            return region
    return None
