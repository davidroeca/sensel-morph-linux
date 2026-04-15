"""Typed Frame and Contact dataclasses.

Higher-level code consumes these immutable snapshots instead of the raw
ctypes Structures exposed by lib/sensel.py.
"""

from __future__ import annotations

from dataclasses import dataclass


CONTACT_INVALID = 0
CONTACT_START = 1
CONTACT_MOVE = 2
CONTACT_END = 3


@dataclass(frozen=True, slots=True)
class Contact:
    """A single contact at a single instant.

    x and y are in millimeters from the top-left of the sensor.
    force is in grams. area is in square millimeters.
    """

    id: int
    state: int
    x: float
    y: float
    force: float
    area: float
    orientation: float
    major_axis: float
    minor_axis: float


@dataclass(frozen=True, slots=True)
class Frame:
    """A snapshot of all active contacts at one scan."""

    lost_frame_count: int
    contacts: tuple[Contact, ...]


def frame_to_dict(frame: "Frame") -> dict:
    """Serialize a Frame to a JSON-compatible dict."""
    return {
        "lost_frame_count": frame.lost_frame_count,
        "contacts": [
            {
                "id": c.id,
                "state": c.state,
                "x": c.x,
                "y": c.y,
                "force": c.force,
                "area": c.area,
                "orientation": c.orientation,
                "major_axis": c.major_axis,
                "minor_axis": c.minor_axis,
            }
            for c in frame.contacts
        ],
    }


def frame_from_dict(d: dict) -> "Frame":
    """Deserialize a Frame from a JSON-compatible dict."""
    contacts = tuple(
        Contact(
            id=int(c["id"]),
            state=int(c["state"]),
            x=float(c["x"]),
            y=float(c["y"]),
            force=float(c["force"]),
            area=float(c["area"]),
            orientation=float(c.get("orientation", 0.0)),
            major_axis=float(c.get("major_axis", 0.0)),
            minor_axis=float(c.get("minor_axis", 0.0)),
        )
        for c in d.get("contacts", ())
    )
    return Frame(
        lost_frame_count=int(d.get("lost_frame_count", 0)),
        contacts=contacts,
    )


def contact_from_struct(c) -> Contact:  # type: ignore[no-untyped-def]
    """Convert a ctypes SenselContact Structure into a typed Contact."""
    return Contact(
        id=int(c.id),
        state=int(c.state),
        x=float(c.x_pos),
        y=float(c.y_pos),
        force=float(c.total_force),
        area=float(c.area),
        orientation=float(c.orientation),
        major_axis=float(c.major_axis),
        minor_axis=float(c.minor_axis),
    )
