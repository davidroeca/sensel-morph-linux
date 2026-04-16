"""Frame/Contact parsing tests against recorded JSON fixtures.

These tests never touch hardware: they load a JSON fixture shaped exactly
like the output of tools/morph_record.py and verify that frame_from_dict
produces the expected immutable dataclasses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sensel_morph import (
    CONTACT_END,
    CONTACT_MOVE,
    CONTACT_START,
    Frame,
    frame_from_dict,
    frame_to_dict,
)

FIXTURE = Path(__file__).parent / "fixtures" / "frames_synthetic.json"


@pytest.fixture(scope="module")
def fixture_frames() -> list[Frame]:
    payload = json.loads(FIXTURE.read_text())
    return [frame_from_dict(f) for f in payload["frames"]]


def test_fixture_loads_expected_frame_count(
    fixture_frames: list[Frame],
) -> None:
    assert len(fixture_frames) == 6


def test_first_frame_has_no_contacts(fixture_frames: list[Frame]) -> None:
    assert fixture_frames[0].contacts == ()


def test_contact_lifecycle_states(fixture_frames: list[Frame]) -> None:
    # id 0: START -> MOVE -> MOVE -> END
    id0_states = [
        next((c.state for c in f.contacts if c.id == 0), None)
        for f in fixture_frames
    ]
    assert id0_states == [
        None,
        CONTACT_START,
        CONTACT_MOVE,
        CONTACT_MOVE,
        CONTACT_END,
        None,
    ]


def test_contact_force_is_float(fixture_frames: list[Frame]) -> None:
    for frame in fixture_frames:
        for c in frame.contacts:
            assert isinstance(c.force, float)
            assert c.force >= 0.0


def test_frame_is_immutable(fixture_frames: list[Frame]) -> None:
    frame = fixture_frames[2]
    with pytest.raises((AttributeError, TypeError)):
        frame.contacts = ()  # ty: ignore[invalid-assignment]
    if frame.contacts:
        c = frame.contacts[0]
        with pytest.raises((AttributeError, TypeError)):
            c.force = 0.0  # type: ignore[misc]


def test_roundtrip_preserves_contacts(fixture_frames: list[Frame]) -> None:
    for frame in fixture_frames:
        assert frame_from_dict(frame_to_dict(frame)) == frame


def test_lost_frame_count_carried_through(fixture_frames: list[Frame]) -> None:
    # frame index 4 was marked with lost_frame_count=1 in the fixture
    assert fixture_frames[4].lost_frame_count == 1
