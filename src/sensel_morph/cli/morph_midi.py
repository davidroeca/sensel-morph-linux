"""MIDI bridge for the Sensel Morph.

Opens a virtual MIDI port via python-rtmidi and translates Morph
contact events into NOTE_ON/NOTE_OFF (or CC) messages through a
YAML profile's region and force-curve definitions.
"""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

import rtmidi

from sensel_morph import CONTACT_END, Device, DeviceError
from sensel_morph.config import PressureCurve, load_profile
from sensel_morph.midi import MidiConfig, MidiEngine


_DEFAULT_PROFILE = (
    Path(__file__).resolve().parents[3] / "profiles" / "midi_drumpads.yaml"
)

_PORT_NAME = "Sensel Morph MIDI"


def _parse_midi_config(midi_data: dict | None) -> MidiConfig:
    """Build a MidiConfig from the profile's ``midi`` section."""
    if midi_data is None:
        return MidiConfig()

    curve_data = midi_data.get("velocity_curve")
    if curve_data is not None:
        raw = curve_data.get("points", [(0.0, 0.0), (1.0, 1.0)])
        curve = PressureCurve(
            points=tuple((float(p[0]), float(p[1])) for p in raw)
        )
    else:
        curve = PressureCurve()

    return MidiConfig(
        velocity_curve=curve,
        max_force=float(midi_data.get("max_force", 500.0)),
        aftertouch=bool(midi_data.get("aftertouch", False)),
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point for the MIDI bridge."""
    parser = argparse.ArgumentParser(
        description="MIDI bridge for the Sensel Morph."
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=_DEFAULT_PROFILE,
        help="path to a MIDI YAML profile (default: profiles/midi_drumpads.yaml)",
    )
    parser.add_argument(
        "--port-name",
        default=_PORT_NAME,
        help=f"virtual MIDI port name (default: {_PORT_NAME})",
    )
    args = parser.parse_args(argv)

    if not args.profile.exists():
        print(f"profile not found: {args.profile}", file=sys.stderr)
        return 1

    try:
        profile = load_profile(args.profile)
    except Exception as e:
        print(f"error loading profile: {e}", file=sys.stderr)
        return 1

    if profile.kind != "midi":
        print(
            f"warning: profile kind is '{profile.kind}', expected 'midi'",
            file=sys.stderr,
        )

    midi_out = rtmidi.MidiOut()
    midi_out.open_virtual_port(args.port_name)
    print(
        f"midi bridge: port='{args.port_name}' profile={profile.name}",
        file=sys.stderr,
    )

    midi_cfg = _parse_midi_config(profile.midi)
    engine: MidiEngine | None = None

    def _cleanup() -> None:
        if engine is not None:
            for msg in engine.all_notes_off():
                midi_out.send_message(list(msg))
        midi_out.close_port()

    def _sigint_handler(*_: object) -> None:
        _cleanup()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        with Device() as dev:
            info = dev.sensor_info()
            print(
                f"device: {info.width_mm:.1f}x{info.height_mm:.1f} mm, "
                f"max_contacts={info.max_contacts}",
                file=sys.stderr,
            )
            engine = MidiEngine(
                regions=profile.regions,
                config=midi_cfg,
                sensor_width_mm=info.width_mm,
                sensor_height_mm=info.height_mm,
            )
            for frame in dev.frames():
                for contact in frame.contacts:
                    messages = engine.process_contact(contact)
                    for msg in messages:
                        midi_out.send_message(list(msg))
    except DeviceError as e:
        print(f"error: {e}", file=sys.stderr)
        if "not found" in str(e).lower():
            print(
                "hint: is the Morph plugged in? "
                "is your user in the 'dialout' group?",
                file=sys.stderr,
            )
        return 1
    except SystemExit:
        pass
    finally:
        _cleanup()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
