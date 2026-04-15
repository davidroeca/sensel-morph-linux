"""Print info about the first connected Sensel Morph and exit."""

from __future__ import annotations

import sys

from sensel_morph import Device, DeviceError, list_devices


def main() -> int:
    try:
        devices = list_devices()
    except DeviceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if not devices:
        print(
            "error: no Sensel Morph devices found.\n"
            "  - check the USB cable\n"
            "  - confirm your user is in the `dialout` group "
            "(or install a udev rule for /dev/ttyACM*)",
            file=sys.stderr,
        )
        return 1

    print(f"found {len(devices)} device(s):")
    for d in devices:
        print(f"  [{d.index}] serial={d.serial} port={d.com_port}")

    try:
        with Device() as dev:
            fw = dev.firmware_info()
            info = dev.sensor_info()
    except DeviceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print()
    print(f"firmware        : {fw.version}  (protocol {fw.protocol})")
    print(f"device id/rev   : 0x{fw.device_id:04x} rev {fw.device_revision}")
    print(f"sensor grid     : {info.num_cols} x {info.num_rows}")
    print(f"dimensions (mm) : {info.width_mm:.2f} x {info.height_mm:.2f}")
    print(f"max contacts    : {info.max_contacts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
