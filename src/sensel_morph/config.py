"""YAML profile loader and validation.

A profile is a YAML file describing how touches map to actions. It is shared
by the tablet bridge (M4) and the MIDI bridge (M5). The loader reads the raw
dict, performs basic validation, and returns a typed ``Profile`` object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .regions import Region, regions_from_yaml


@dataclass(frozen=True, slots=True)
class PressureCurve:
    """Piecewise-linear pressure curve.

    ``points`` is a list of (input_fraction, output_fraction) tuples sorted by
    input. Linear interpolation is applied between points; values outside
    [0, 1] are clamped.
    """

    points: tuple[tuple[float, float], ...] = ((0.0, 0.0), (1.0, 1.0))

    def apply(self, fraction: float) -> float:
        t = max(0.0, min(fraction, 1.0))
        pts = self.points
        if t <= pts[0][0]:
            return pts[0][1]
        if t >= pts[-1][0]:
            return pts[-1][1]
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            if x0 <= t <= x1:
                span = x1 - x0
                if span == 0.0:
                    return y1
                alpha = (t - x0) / span
                return y0 + alpha * (y1 - y0)
        return t


def _parse_pressure_curve(data: dict | None) -> PressureCurve:
    if data is None:
        return PressureCurve()
    raw = data.get("points", [(0.0, 0.0), (1.0, 1.0)])
    return PressureCurve(points=tuple((float(p[0]), float(p[1])) for p in raw))


@dataclass(frozen=True, slots=True)
class TabletMode:
    """Tablet-specific profile settings."""

    mode: str = "pen"
    pressure_curve: PressureCurve = field(default_factory=PressureCurve)
    max_force: float = 500.0
    active_surface: tuple[float, float, float, float] | None = None


@dataclass(frozen=True, slots=True)
class Profile:
    """A fully loaded and validated profile."""

    name: str
    kind: str
    tablet: TabletMode | None = None
    midi: dict | None = None
    regions: list[Region] = field(default_factory=list)


class ProfileError(ValueError):
    """Raised when a profile file is invalid."""


def load_profile(path: Path) -> Profile:
    """Load and validate a YAML profile from disk."""
    text = path.read_text()
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ProfileError(f"profile must be a YAML mapping, got {type(data).__name__}")

    name = data.get("name", path.stem)
    kind = data.get("kind", "")
    regions = regions_from_yaml(data)

    tablet: TabletMode | None = None
    td = data.get("tablet")
    if td is not None:
        if not isinstance(td, dict):
            raise ProfileError("'tablet' section must be a mapping")
        pc = _parse_pressure_curve(td.get("pressure_curve"))
        as_ = td.get("active_surface")
        if as_ is not None:
            if not isinstance(as_, (list, tuple)) or len(as_) != 4:
                raise ProfileError(
                    "'active_surface' must be a list of 4 floats [x, y, w, h]"
                )
            as_ = tuple(float(v) for v in as_)
        tablet = TabletMode(
            mode=td.get("mode", "pen"),
            pressure_curve=pc,
            max_force=float(td.get("max_force", 500.0)),
            active_surface=as_,
        )

    midi = data.get("midi")

    return Profile(name=name, kind=kind, tablet=tablet, midi=midi, regions=regions)
