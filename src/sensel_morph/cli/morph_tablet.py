"""uinput tablet bridge for the Sensel Morph.

Modes
-----
pen (default)
    The highest-force contact drives a single virtual stylus via evdev.
    All other contacts are ignored. Pressure is remapped through the
    profile's pressure curve.

multitouch
    Each contact is assigned an MT slot. Up to max_contacts simultaneous
    touches are reported through ABS_MT_POSITION_X/Y and ABS_MT_PRESSURE.
"""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

from evdev import AbsInfo, UInput, UInputError
from evdev.ecodes import (
    ABS_MT_POSITION_X,
    ABS_MT_POSITION_Y,
    ABS_MT_PRESSURE,
    ABS_MT_SLOT,
    ABS_MT_TOOL_TYPE,
    ABS_MT_TRACKING_ID,
    ABS_PRESSURE,
    ABS_X,
    ABS_Y,
    BTN_STYLUS,
    BTN_STYLUS2,
    BTN_TOOL_FINGER,
    BTN_TOOL_PEN,
    BTN_TOUCH,
    EV_ABS,
    EV_KEY,
    EV_SYN,
    SYN_REPORT,
)

from sensel_morph import (
    CONTACT_END,
    CONTACT_START,
    Device,
    DeviceError,
)
from sensel_morph.config import Profile, load_profile
from sensel_morph.regions import find_region

_DEFAULT_PROFILE = (
    Path(__file__).resolve().parents[3] / "profiles" / "tablet_default.yaml"
)

_UINPUT_NAME_PEN = "Sensel Morph Pen"
_UINPUT_NAME_MT = "Sensel Morph Touch"

_ABS_MAX_X = 32767
_ABS_MAX_Y = 32767
_ABS_MAX_PRESSURE = 65535
_MT_MAX_SLOTS = 16


def _pen_absinfo_x(width_mm: float) -> AbsInfo:
    return AbsInfo(value=0, min=0, max=_ABS_MAX_X, fuzz=0, flat=0, resolution=0)


def _pen_absinfo_y(height_mm: float) -> AbsInfo:
    return AbsInfo(value=0, min=0, max=_ABS_MAX_Y, fuzz=0, flat=0, resolution=0)


def _pen_absinfo_pressure() -> AbsInfo:
    return AbsInfo(
        value=0, min=0, max=_ABS_MAX_PRESSURE, fuzz=0, flat=0, resolution=0
    )


def _create_pen_device() -> UInput:
    try:
        return UInput(
            name=_UINPUT_NAME_PEN,
            events={  # ty: ignore[invalid-argument-type]
                EV_KEY: [BTN_TOOL_PEN, BTN_TOUCH, BTN_STYLUS, BTN_STYLUS2],
                EV_ABS: [
                    (ABS_X, AbsInfo(0, 0, _ABS_MAX_X, 0, 0, 0)),
                    (ABS_Y, AbsInfo(0, 0, _ABS_MAX_Y, 0, 0, 0)),
                    (ABS_PRESSURE, AbsInfo(0, 0, _ABS_MAX_PRESSURE, 0, 0, 0)),
                ],
            },
        )
    except UInputError:
        sys.exit(
            "Permission denied: cannot open /dev/uinput.\n"
            "Install the udev rule and add your user to the input group:\n"
            "  sudo cp udev/99-sensel.rules /etc/udev/rules.d/\n"
            "  sudo udevadm control --reload-rules && sudo udevadm trigger\n"
            "  sudo usermod -aG input $USER\n"
            "Then log out and back in."
        )


def _create_mt_device(max_slots: int) -> UInput:
    try:
        return UInput(
            name=_UINPUT_NAME_MT,
            events={  # ty: ignore[invalid-argument-type]
                EV_KEY: [BTN_TOUCH, BTN_TOOL_FINGER],
                EV_ABS: [
                    (ABS_MT_POSITION_X, AbsInfo(0, 0, _ABS_MAX_X, 0, 0, 0)),
                    (ABS_MT_POSITION_Y, AbsInfo(0, 0, _ABS_MAX_Y, 0, 0, 0)),
                    (
                        ABS_MT_PRESSURE,
                        AbsInfo(0, 0, _ABS_MAX_PRESSURE, 0, 0, 0),
                    ),
                    (ABS_MT_SLOT, AbsInfo(0, 0, max_slots - 1, 0, 0, 0)),
                    (ABS_MT_TRACKING_ID, AbsInfo(0, 0, max_slots, 0, 0, 0)),
                    (ABS_MT_TOOL_TYPE, AbsInfo(0, 0, 1, 0, 0, 0)),
                ],
            },
        )
    except UInputError:
        sys.exit(
            "Permission denied: cannot open /dev/uinput.\n"
            "Install the udev rule and add your user to the input group:\n"
            "  sudo cp udev/99-sensel.rules /etc/udev/rules.d/\n"
            "  sudo udevadm control --reload-rules && sudo udevadm trigger\n"
            "  sudo usermod -aG input $USER\n"
            "Then log out and back in."
        )


def _run_pen(dev: Device, profile: Profile) -> None:
    tablet = profile.tablet
    assert tablet is not None
    info = dev.sensor_info()
    curve = tablet.pressure_curve
    max_force = tablet.max_force

    active_surface = tablet.active_surface
    if active_surface is not None:
        surf_x, surf_y, surf_w, surf_h = active_surface
        x_lo_mm = surf_x * info.width_mm
        x_hi_mm = (surf_x + surf_w) * info.width_mm
        y_lo_mm = surf_y * info.height_mm
        y_hi_mm = (surf_y + surf_h) * info.height_mm
    else:
        x_lo_mm, x_hi_mm = 0.0, info.width_mm
        y_lo_mm, y_hi_mm = 0.0, info.height_mm

    regions = profile.regions

    ui = _create_pen_device()
    pen_down = False
    prev_stylus = False
    prev_stylus2 = False

    def _cleanup() -> None:
        if pen_down:
            ui.write(EV_KEY, BTN_TOOL_PEN, 0)
            ui.write(EV_KEY, BTN_TOUCH, 0)
            ui.write(EV_ABS, ABS_PRESSURE, 0)
            ui.write(EV_SYN, SYN_REPORT, 0)
        ui.write(EV_KEY, BTN_STYLUS, 0)
        ui.write(EV_KEY, BTN_STYLUS2, 0)
        ui.write(EV_SYN, SYN_REPORT, 0)
        ui.close()

    def _sigint_handler(*_: object) -> None:
        _cleanup()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        for frame in dev.frames():
            pen_contact = None
            button_contacts: list = []

            for c in frame.contacts:
                if c.state == CONTACT_END:
                    continue
                if pen_contact is None or c.force > pen_contact.force:
                    pen_contact = c

            for c in frame.contacts:
                if c.state == CONTACT_END:
                    continue
                if pen_contact is not None and c.id == pen_contact.id:
                    continue
                rgn = find_region(c.x, c.y, info, regions)
                if rgn and rgn.action.get("type") == "button":
                    button_contacts.append((c, rgn))

            if pen_contact is None:
                if pen_down:
                    ui.write(EV_KEY, BTN_TOUCH, 0)
                    ui.write(EV_KEY, BTN_TOOL_PEN, 0)
                    ui.write(EV_ABS, ABS_PRESSURE, 0)
                    ui.write(EV_SYN, SYN_REPORT, 0)
                    pen_down = False
            else:
                nx = max(
                    0.0,
                    min((pen_contact.x - x_lo_mm) / (x_hi_mm - x_lo_mm), 1.0),
                )
                ny = max(
                    0.0,
                    min((pen_contact.y - y_lo_mm) / (y_hi_mm - y_lo_mm), 1.0),
                )
                nf = max(0.0, min(pen_contact.force / max_force, 1.0))
                pressure_frac = curve.apply(nf)

                abs_x = int(nx * _ABS_MAX_X)
                abs_y = int(ny * _ABS_MAX_Y)
                abs_p = int(pressure_frac * _ABS_MAX_PRESSURE)

                if not pen_down:
                    ui.write(EV_KEY, BTN_TOOL_PEN, 1)
                    pen_down = True

                ui.write(EV_KEY, BTN_TOUCH, 1)
                ui.write(EV_ABS, ABS_X, abs_x)
                ui.write(EV_ABS, ABS_Y, abs_y)
                ui.write(EV_ABS, ABS_PRESSURE, abs_p)

            stylus_on = any(
                rgn.action.get("code") == "BTN_STYLUS"
                for _, rgn in button_contacts
            )
            stylus2_on = any(
                rgn.action.get("code") == "BTN_STYLUS2"
                for _, rgn in button_contacts
            )

            if stylus_on != prev_stylus:
                ui.write(EV_KEY, BTN_STYLUS, 1 if stylus_on else 0)
                prev_stylus = stylus_on
            if stylus2_on != prev_stylus2:
                ui.write(EV_KEY, BTN_STYLUS2, 1 if stylus2_on else 0)
                prev_stylus2 = stylus2_on

            ui.write(EV_SYN, SYN_REPORT, 0)

    except SystemExit:
        pass
    finally:
        _cleanup()


def _run_multitouch(dev: Device, profile: Profile) -> None:
    info = dev.sensor_info()
    max_slots = min(info.max_contacts, _MT_MAX_SLOTS)
    ui = _create_mt_device(max_slots)

    contact_slots: dict[int, int] = {}
    next_slot = 0
    active_slots: dict[int, int] = {}

    def _cleanup() -> None:
        for slot in active_slots.values():
            ui.write(EV_ABS, ABS_MT_SLOT, slot)
            ui.write(EV_ABS, ABS_MT_TRACKING_ID, -1)
        ui.write(EV_SYN, SYN_REPORT, 0)
        ui.close()

    def _sigint_handler(*_: object) -> None:
        _cleanup()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        for frame in dev.frames():
            current_ids: set[int] = set()

            for c in frame.contacts:
                current_ids.add(c.id)

                if c.state == CONTACT_END:
                    if c.id in contact_slots:
                        slot = contact_slots.pop(c.id)
                        active_slots.pop(c.id, None)
                        ui.write(EV_ABS, ABS_MT_SLOT, slot)
                        ui.write(EV_ABS, ABS_MT_TRACKING_ID, -1)
                    continue

                if c.id not in contact_slots:
                    if next_slot < max_slots:
                        contact_slots[c.id] = next_slot
                        active_slots[c.id] = next_slot
                        next_slot += 1
                    else:
                        continue

                slot = contact_slots[c.id]
                active_slots[c.id] = slot
                ui.write(EV_ABS, ABS_MT_SLOT, slot)

                if c.state == CONTACT_START:
                    ui.write(EV_ABS, ABS_MT_TRACKING_ID, c.id)

                nx = max(0.0, min(c.x / info.width_mm, 1.0))
                ny = max(0.0, min(c.y / info.height_mm, 1.0))
                ui.write(EV_ABS, ABS_MT_POSITION_X, int(nx * _ABS_MAX_X))
                ui.write(EV_ABS, ABS_MT_POSITION_Y, int(ny * _ABS_MAX_Y))
                ui.write(EV_ABS, ABS_MT_TOOL_TYPE, 1)

                nf = min(c.force / 500.0, 1.0)
                ui.write(EV_ABS, ABS_MT_PRESSURE, int(nf * _ABS_MAX_PRESSURE))

            ended = [cid for cid in contact_slots if cid not in current_ids]
            for cid in ended:
                slot = contact_slots.pop(cid)
                active_slots.pop(cid, None)
                ui.write(EV_ABS, ABS_MT_SLOT, slot)
                ui.write(EV_ABS, ABS_MT_TRACKING_ID, -1)

            num_active = sum(
                1 for c in frame.contacts if c.state != CONTACT_END
            )
            ui.write(EV_KEY, BTN_TOUCH, 1 if num_active > 0 else 0)
            ui.write(EV_SYN, SYN_REPORT, 0)

    except SystemExit:
        pass
    finally:
        _cleanup()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="uinput tablet bridge for the Sensel Morph."
    )
    parser.add_argument(
        "--mode",
        choices=["pen", "multitouch"],
        default="pen",
        help="tablet mode: pen (default) or multitouch",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=_DEFAULT_PROFILE,
        help="path to a YAML profile (default: profiles/tablet_default.yaml)",
    )
    args = parser.parse_args(argv)

    profile: Profile | None = None
    if args.profile.exists():
        try:
            profile = load_profile(args.profile)
        except Exception as e:
            print(f"error loading profile: {e}", file=sys.stderr)
            return 1
    else:
        print(f"profile not found: {args.profile}", file=sys.stderr)
        return 1

    mode = args.mode
    if profile.tablet and profile.tablet.mode:
        mode = profile.tablet.mode

    print(f"tablet bridge: mode={mode} profile={profile.name}", file=sys.stderr)

    try:
        with Device() as dev:
            info = dev.sensor_info()
            print(
                f"device: {info.width_mm:.1f}x{info.height_mm:.1f} mm, "
                f"max_contacts={info.max_contacts}",
                file=sys.stderr,
            )
            if mode == "pen":
                _run_pen(dev, profile)
            else:
                _run_multitouch(dev, profile)
    except DeviceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
