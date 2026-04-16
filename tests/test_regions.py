"""Tests for regions, config, and pressure curves (no hardware required)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from sensel_morph import (
    PressureCurve,
    ProfileError,
    Rect,
    Region,
    SensorInfo,
    find_region,
    load_profile,
    regions_from_yaml,
)

_SENSOR_INFO = SensorInfo(
    max_contacts=16, num_rows=105, num_cols=185, width_mm=250.0, height_mm=140.0
)


class TestRect:
    def test_contains_center(self) -> None:
        r = Rect(x=0.1, y=0.2, w=0.5, h=0.4)
        assert r.contains(0.3, 0.4) is True

    def test_excludes_outside(self) -> None:
        r = Rect(x=0.1, y=0.2, w=0.5, h=0.4)
        assert r.contains(0.0, 0.0) is False
        assert r.contains(0.7, 0.7) is False

    def test_contains_upper_left_inclusive(self) -> None:
        r = Rect(x=0.1, y=0.2, w=0.5, h=0.4)
        assert r.contains(0.1, 0.2) is True

    def test_excludes_right_edge(self) -> None:
        r = Rect(x=0.1, y=0.2, w=0.5, h=0.4)
        assert r.contains(0.6, 0.3) is False


class TestRegion:
    def test_hit_inside(self) -> None:
        rgn = Region(name="pad", rect=Rect(0.0, 0.0, 0.25, 0.25))
        assert rgn.hit(10.0, 10.0, _SENSOR_INFO) is True

    def test_hit_outside(self) -> None:
        rgn = Region(name="pad", rect=Rect(0.5, 0.5, 0.25, 0.25))
        assert rgn.hit(10.0, 10.0, _SENSOR_INFO) is False


class TestFindRegion:
    def test_returns_first_match(self) -> None:
        regions = [
            Region(name="a", rect=Rect(0.0, 0.0, 0.5, 0.5)),
            Region(name="b", rect=Rect(0.0, 0.0, 0.5, 0.5)),
        ]
        result = find_region(10.0, 10.0, _SENSOR_INFO, regions)
        assert result is not None
        assert result.name == "a"

    def test_returns_none_when_no_match(self) -> None:
        regions = [
            Region(name="a", rect=Rect(0.8, 0.8, 0.2, 0.2)),
        ]
        assert find_region(10.0, 10.0, _SENSOR_INFO, regions) is None


class TestRegionsFromYaml:
    def test_parses_regions(self) -> None:
        data = {
            "regions": [
                {
                    "name": "left",
                    "rect": {"x": 0.0, "y": 0.9, "w": 0.12, "h": 0.1},
                    "action": {"type": "button", "code": "BTN_STYLUS"},
                }
            ]
        }
        result = regions_from_yaml(data)
        assert len(result) == 1
        assert result[0].name == "left"
        assert result[0].rect.x == 0.0
        assert result[0].action["type"] == "button"

    def test_empty_regions(self) -> None:
        assert regions_from_yaml({}) == []


class TestPressureCurve:
    def test_identity(self) -> None:
        c = PressureCurve()
        assert c.apply(0.0) == pytest.approx(0.0)
        assert c.apply(0.5) == pytest.approx(0.5)
        assert c.apply(1.0) == pytest.approx(1.0)

    def test_custom_curve(self) -> None:
        c = PressureCurve(points=((0.0, 0.0), (0.5, 0.0), (1.0, 1.0)))
        assert c.apply(0.25) == pytest.approx(0.0)
        assert c.apply(0.75) == pytest.approx(0.5)
        assert c.apply(1.0) == pytest.approx(1.0)

    def test_clamps_out_of_range(self) -> None:
        c = PressureCurve()
        assert c.apply(-0.5) == pytest.approx(0.0)
        assert c.apply(1.5) == pytest.approx(1.0)


class TestLoadProfile:
    def test_loads_tablet_default(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "profiles"
            / "tablet_default.yaml"
        )
        profile = load_profile(path)
        assert profile.name == "tablet_default"
        assert profile.kind == "tablet"
        assert profile.tablet is not None
        assert profile.tablet.mode == "pen"
        assert len(profile.regions) == 2

    def test_loads_minimal_profile(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("name: minimal\nkind: tablet\n")
            f.flush()
            profile = load_profile(Path(f.name))
        assert profile.name == "minimal"
        assert profile.regions == []

    def test_invalid_profile_raises(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("- just\n- a\n- list\n")
            f.flush()
            with pytest.raises(ProfileError, match="mapping"):
                load_profile(Path(f.name))

    def test_active_surface_must_be_four_floats(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(
                "name: bad\nkind: tablet\ntablet:\n  active_surface: [1, 2]\n"
            )
            f.flush()
            with pytest.raises(ProfileError, match="4 floats"):
                load_profile(Path(f.name))
