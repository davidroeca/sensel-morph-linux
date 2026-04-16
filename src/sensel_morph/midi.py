"""MIDI mapping engine.

Translates Morph contact events into MIDI messages using a profile's
region definitions and force-to-velocity curves. The engine is stateful:
it tracks which contacts are active and which notes are currently on,
so that NOTE_OFF is correctly emitted when a contact ends or leaves
its originating region.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import PressureCurve
from .frames import CONTACT_END, CONTACT_MOVE, CONTACT_START, Contact
from .regions import Region


NOTE_ON = 0x90
NOTE_OFF = 0x80
POLY_AFTERTOUCH = 0xA0
CONTROL_CHANGE = 0xB0


@dataclass(frozen=True, slots=True)
class NoteMapping:
    """A region that triggers a MIDI note."""

    note: int
    channel: int = 0


@dataclass(frozen=True, slots=True)
class CCMapping:
    """A region that sends a MIDI CC value proportional to force."""

    cc: int
    channel: int = 0


@dataclass(frozen=True, slots=True)
class MidiConfig:
    """Global MIDI settings from a profile."""

    velocity_curve: PressureCurve = field(default_factory=PressureCurve)
    max_force: float = 500.0
    aftertouch: bool = False


@dataclass
class ActiveNote:
    """Tracks a note that is currently on for a given contact."""

    channel: int
    note: int
    region_name: str


def parse_mapping(region: Region) -> NoteMapping | CCMapping | None:
    """Extract a MIDI mapping from a region's action dict.

    Returns None if the region has no MIDI action.
    """
    action = region.action
    atype = action.get("type", "")
    channel = int(action.get("channel", 0))

    if atype == "note":
        return NoteMapping(note=int(action["note"]), channel=channel)
    elif atype == "cc":
        return CCMapping(cc=int(action["cc"]), channel=channel)
    return None


def velocity_from_force(
    force: float, max_force: float, curve: PressureCurve
) -> int:
    """Convert a force value (grams) to a MIDI velocity (0-127)."""
    fraction = max(0.0, min(force / max_force, 1.0))
    curved = curve.apply(fraction)
    return max(0, min(int(curved * 127), 127))


def aftertouch_from_force(
    force: float, max_force: float, curve: PressureCurve
) -> int:
    """Convert a force value to a polyphonic aftertouch value (0-127)."""
    return velocity_from_force(force, max_force, curve)


class MidiEngine:
    """Stateful engine that converts contacts to MIDI messages.

    Call ``process_contact`` for each contact in each frame. It returns
    a list of raw MIDI byte-tuples ready to be sent via rtmidi.
    """

    def __init__(
        self,
        regions: list[Region],
        config: MidiConfig,
        sensor_width_mm: float,
        sensor_height_mm: float,
    ) -> None:
        self._regions = regions
        self._config = config
        self._width = sensor_width_mm
        self._height = sensor_height_mm
        self._active: dict[int, ActiveNote] = {}
        self._mappings: dict[str, NoteMapping | CCMapping] = {}

        for rgn in regions:
            mapping = parse_mapping(rgn)
            if mapping is not None:
                self._mappings[rgn.name] = mapping

    def _find_region(self, x_mm: float, y_mm: float) -> Region | None:
        nx = x_mm / self._width
        ny = y_mm / self._height
        for rgn in self._regions:
            if rgn.rect.contains(nx, ny):
                return rgn
        return None

    def process_contact(self, contact: Contact) -> list[tuple[int, ...]]:
        """Process a single contact and return MIDI messages.

        Each message is a tuple of ints (status_byte, data1, data2).
        """
        messages: list[tuple[int, ...]] = []
        cfg = self._config

        if contact.state == CONTACT_START:
            rgn = self._find_region(contact.x, contact.y)
            if rgn is None:
                return messages
            mapping = self._mappings.get(rgn.name)
            if mapping is None:
                return messages

            if isinstance(mapping, NoteMapping):
                vel = velocity_from_force(
                    contact.force, cfg.max_force, cfg.velocity_curve
                )
                vel = max(vel, 1)
                messages.append(
                    (NOTE_ON | mapping.channel, mapping.note, vel)
                )
                self._active[contact.id] = ActiveNote(
                    channel=mapping.channel,
                    note=mapping.note,
                    region_name=rgn.name,
                )
            elif isinstance(mapping, CCMapping):
                val = velocity_from_force(
                    contact.force, cfg.max_force, cfg.velocity_curve
                )
                messages.append(
                    (CONTROL_CHANGE | mapping.channel, mapping.cc, val)
                )

        elif contact.state == CONTACT_MOVE:
            active = self._active.get(contact.id)
            if active is not None and cfg.aftertouch:
                at_val = aftertouch_from_force(
                    contact.force, cfg.max_force, cfg.velocity_curve
                )
                messages.append(
                    (
                        POLY_AFTERTOUCH | active.channel,
                        active.note,
                        at_val,
                    )
                )
            rgn = self._find_region(contact.x, contact.y)
            if rgn is not None:
                mapping = self._mappings.get(rgn.name)
                if isinstance(mapping, CCMapping):
                    val = velocity_from_force(
                        contact.force, cfg.max_force, cfg.velocity_curve
                    )
                    messages.append(
                        (
                            CONTROL_CHANGE | mapping.channel,
                            mapping.cc,
                            val,
                        )
                    )

        elif contact.state == CONTACT_END:
            active = self._active.pop(contact.id, None)
            if active is not None:
                messages.append(
                    (NOTE_OFF | active.channel, active.note, 0)
                )

        return messages

    def all_notes_off(self) -> list[tuple[int, ...]]:
        """Generate NOTE_OFF for all currently active notes."""
        messages: list[tuple[int, ...]] = []
        for active in self._active.values():
            messages.append(
                (NOTE_OFF | active.channel, active.note, 0)
            )
        self._active.clear()
        return messages
