"""MIDI mapping engine tests (no hardware, no rtmidi required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sensel_morph.config import PressureCurve, load_profile
from sensel_morph.frames import Contact
from sensel_morph.midi import (
    CONTROL_CHANGE,
    NOTE_OFF,
    NOTE_ON,
    POLY_AFTERTOUCH,
    CCMapping,
    MidiConfig,
    MidiEngine,
    NoteMapping,
    parse_mapping,
    velocity_from_force,
)
from sensel_morph.regions import Rect, Region

# Constants matching sensel_morph.frames
_START = 1
_MOVE = 2
_END = 3

_WIDTH = 250.0
_HEIGHT = 140.0


def _make_contact(
    id: int,
    state: int,
    x: float,
    y: float,
    force: float = 100.0,
) -> Contact:
    return Contact(
        id=id,
        state=state,
        x=x,
        y=y,
        force=force,
        area=10.0,
        orientation=0.0,
        major_axis=5.0,
        minor_axis=3.0,
    )


def _note_region(
    name: str, x: float, y: float, w: float, h: float, note: int, channel: int = 0
) -> Region:
    return Region(
        name=name,
        rect=Rect(x=x, y=y, w=w, h=h),
        action={"type": "note", "note": note, "channel": channel},
    )


def _cc_region(
    name: str, x: float, y: float, w: float, h: float, cc: int, channel: int = 0
) -> Region:
    return Region(
        name=name,
        rect=Rect(x=x, y=y, w=w, h=h),
        action={"type": "cc", "cc": cc, "channel": channel},
    )


class TestParseMapping:
    def test_note_mapping(self) -> None:
        rgn = _note_region("pad", 0, 0, 0.5, 0.5, note=36, channel=9)
        mapping = parse_mapping(rgn)
        assert isinstance(mapping, NoteMapping)
        assert mapping.note == 36
        assert mapping.channel == 9

    def test_cc_mapping(self) -> None:
        rgn = _cc_region("slider", 0, 0, 1, 0.1, cc=1, channel=0)
        mapping = parse_mapping(rgn)
        assert isinstance(mapping, CCMapping)
        assert mapping.cc == 1

    def test_unknown_action_returns_none(self) -> None:
        rgn = Region(name="btn", rect=Rect(0, 0, 0.1, 0.1), action={"type": "button"})
        assert parse_mapping(rgn) is None

    def test_no_action_returns_none(self) -> None:
        rgn = Region(name="empty", rect=Rect(0, 0, 0.1, 0.1))
        assert parse_mapping(rgn) is None


class TestVelocityFromForce:
    def test_zero_force(self) -> None:
        assert velocity_from_force(0.0, 500.0, PressureCurve()) == 0

    def test_max_force(self) -> None:
        assert velocity_from_force(500.0, 500.0, PressureCurve()) == 127

    def test_half_force_linear(self) -> None:
        v = velocity_from_force(250.0, 500.0, PressureCurve())
        assert 62 <= v <= 64

    def test_clamps_above_max(self) -> None:
        assert velocity_from_force(1000.0, 500.0, PressureCurve()) == 127


class TestMidiEngine:
    def _engine(
        self,
        regions: list[Region] | None = None,
        aftertouch: bool = False,
    ) -> MidiEngine:
        if regions is None:
            regions = [
                _note_region("pad_a", 0.0, 0.0, 0.5, 0.5, note=36, channel=9),
                _note_region("pad_b", 0.5, 0.0, 0.5, 0.5, note=38, channel=9),
            ]
        return MidiEngine(
            regions=regions,
            config=MidiConfig(aftertouch=aftertouch),
            sensor_width_mm=_WIDTH,
            sensor_height_mm=_HEIGHT,
        )

    def test_note_on_at_contact_start(self) -> None:
        engine = self._engine()
        contact = _make_contact(id=0, state=_START, x=50.0, y=30.0, force=200.0)
        msgs = engine.process_contact(contact)
        assert len(msgs) == 1
        status, note, vel = msgs[0]
        assert status == NOTE_ON | 9
        assert note == 36
        assert 1 <= vel <= 127

    def test_note_off_at_contact_end(self) -> None:
        engine = self._engine()
        engine.process_contact(
            _make_contact(id=0, state=_START, x=50.0, y=30.0, force=200.0)
        )
        msgs = engine.process_contact(
            _make_contact(id=0, state=_END, x=50.0, y=30.0, force=0.0)
        )
        assert len(msgs) == 1
        status, note, vel = msgs[0]
        assert status == NOTE_OFF | 9
        assert note == 36
        assert vel == 0

    def test_no_message_outside_regions(self) -> None:
        engine = self._engine()
        contact = _make_contact(id=0, state=_START, x=125.0, y=105.0)
        msgs = engine.process_contact(contact)
        assert msgs == []

    def test_aftertouch_on_move(self) -> None:
        engine = self._engine(aftertouch=True)
        engine.process_contact(
            _make_contact(id=0, state=_START, x=50.0, y=30.0, force=100.0)
        )
        msgs = engine.process_contact(
            _make_contact(id=0, state=_MOVE, x=55.0, y=32.0, force=300.0)
        )
        at_msgs = [m for m in msgs if (m[0] & 0xF0) == POLY_AFTERTOUCH]
        assert len(at_msgs) == 1
        assert at_msgs[0][1] == 36

    def test_no_aftertouch_when_disabled(self) -> None:
        engine = self._engine(aftertouch=False)
        engine.process_contact(
            _make_contact(id=0, state=_START, x=50.0, y=30.0, force=100.0)
        )
        msgs = engine.process_contact(
            _make_contact(id=0, state=_MOVE, x=55.0, y=32.0, force=300.0)
        )
        at_msgs = [m for m in msgs if (m[0] & 0xF0) == POLY_AFTERTOUCH]
        assert len(at_msgs) == 0

    def test_multiple_simultaneous_contacts(self) -> None:
        engine = self._engine()
        msgs_a = engine.process_contact(
            _make_contact(id=0, state=_START, x=50.0, y=30.0, force=200.0)
        )
        msgs_b = engine.process_contact(
            _make_contact(id=1, state=_START, x=175.0, y=30.0, force=150.0)
        )
        assert len(msgs_a) == 1
        assert len(msgs_b) == 1
        assert msgs_a[0][1] == 36
        assert msgs_b[0][1] == 38

    def test_all_notes_off(self) -> None:
        engine = self._engine()
        engine.process_contact(
            _make_contact(id=0, state=_START, x=50.0, y=30.0, force=200.0)
        )
        engine.process_contact(
            _make_contact(id=1, state=_START, x=175.0, y=30.0, force=150.0)
        )
        off_msgs = engine.all_notes_off()
        assert len(off_msgs) == 2
        notes = {m[1] for m in off_msgs}
        assert notes == {36, 38}

    def test_cc_on_start(self) -> None:
        regions = [_cc_region("slider", 0.0, 0.0, 1.0, 0.1, cc=1)]
        engine = self._engine(regions=regions)
        msgs = engine.process_contact(
            _make_contact(id=0, state=_START, x=125.0, y=7.0, force=250.0)
        )
        assert len(msgs) == 1
        assert msgs[0][0] == CONTROL_CHANGE
        assert msgs[0][1] == 1

    def test_cc_updates_on_move(self) -> None:
        regions = [_cc_region("slider", 0.0, 0.0, 1.0, 0.1, cc=1)]
        engine = self._engine(regions=regions)
        engine.process_contact(
            _make_contact(id=0, state=_START, x=125.0, y=7.0, force=100.0)
        )
        msgs = engine.process_contact(
            _make_contact(id=0, state=_MOVE, x=125.0, y=7.0, force=400.0)
        )
        cc_msgs = [m for m in msgs if (m[0] & 0xF0) == CONTROL_CHANGE]
        assert len(cc_msgs) == 1


class TestProfileLoading:
    def test_loads_drumpads_profile(self) -> None:
        path = Path(__file__).resolve().parents[1] / "profiles" / "midi_drumpads.yaml"
        profile = load_profile(path)
        assert profile.name == "midi_drumpads"
        assert profile.kind == "midi"
        assert len(profile.regions) == 16
        assert profile.midi is not None

    def test_loads_keyboard_profile(self) -> None:
        path = Path(__file__).resolve().parents[1] / "profiles" / "midi_keyboard.yaml"
        profile = load_profile(path)
        assert profile.name == "midi_keyboard"
        assert profile.kind == "midi"
        assert len(profile.regions) == 13
        assert profile.midi is not None
        assert profile.midi["aftertouch"] is True

    def test_drumpads_regions_cover_surface(self) -> None:
        """All 16 pads tile the surface with no gaps or overlaps."""
        path = Path(__file__).resolve().parents[1] / "profiles" / "midi_drumpads.yaml"
        profile = load_profile(path)
        for rgn in profile.regions:
            r = rgn.rect
            assert 0.0 <= r.x <= 1.0
            assert 0.0 <= r.y <= 1.0
            assert r.x + r.w <= 1.001
            assert r.y + r.h <= 1.001
