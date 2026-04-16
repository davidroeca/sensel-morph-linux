"""Read, write, and reset the Sensel Morph's on-device configuration.

Subcommands:
    dump   Read all configurable registers and write them to a YAML file
           (or stdout).
    load   Write register values from a YAML file back to the device.
    reset  Issue a soft reset to restore factory defaults.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from sensel_morph import Device, DeviceError, list_devices
from sensel_morph.registers import config_from_dict, config_to_dict


def _open_or_exit() -> Device:
    """Return an entered Device context or print an error and exit."""
    try:
        devices = list_devices()
    except DeviceError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1)

    if not devices:
        print(
            "error: no Sensel Morph devices found.\n"
            "  - check the USB cable\n"
            "  - confirm your user is in the `dialout` group "
            "(or install a udev rule for /dev/ttyACM*)",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return Device()


def _cmd_dump(args: argparse.Namespace) -> int:
    """Read all configurable registers and emit YAML."""
    dev = _open_or_exit()
    try:
        with dev:
            fw = dev.firmware_info()
            cfg = dev.read_config()
    except DeviceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    output: dict[str, object] = {
        "firmware_version": fw.version,
        "device_id": f"0x{fw.device_id:04x}",
        "config": config_to_dict(cfg),
    }

    text = yaml.safe_dump(
        output, default_flow_style=False, sort_keys=False
    )

    if args.output is None:
        sys.stdout.write(text)
    else:
        out_path = Path(args.output)
        out_path.write_text(text)
        print(f"config written to {out_path}")
    return 0


def _cmd_load(args: argparse.Namespace) -> int:
    """Write register values from a YAML file to the device."""
    path = Path(args.file)
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1

    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        print(f"error: invalid YAML: {e}", file=sys.stderr)
        return 1

    if not isinstance(data, dict) or "config" not in data:
        print(
            "error: YAML file must contain a top-level 'config' key",
            file=sys.stderr,
        )
        return 1

    cfg = config_from_dict(data["config"])

    dev = _open_or_exit()
    try:
        with dev:
            dev.write_config(cfg)
    except DeviceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print("config loaded successfully")
    return 0


def _cmd_reset(args: argparse.Namespace) -> int:
    """Issue a soft reset to the device."""
    dev = _open_or_exit()
    try:
        with dev:
            dev.soft_reset()
    except DeviceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print("device reset successfully")
    return 0


def main() -> int:
    """Entry point for morph-config."""
    parser = argparse.ArgumentParser(
        prog="morph-config",
        description=(
            "Read, write, and reset the Sensel Morph's on-device "
            "configuration via the LibSensel register-map API."
        ),
    )
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    dump_p = sub.add_parser(
        "dump",
        help="Read all configurable registers to YAML.",
    )
    dump_p.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        default=None,
        help="Write YAML to FILE instead of stdout.",
    )
    dump_p.set_defaults(func=_cmd_dump)

    load_p = sub.add_parser(
        "load",
        help="Write register values from a YAML file to the device.",
    )
    load_p.add_argument(
        "file",
        help="Path to a YAML config file (produced by `dump`).",
    )
    load_p.set_defaults(func=_cmd_load)

    reset_p = sub.add_parser(
        "reset",
        help="Soft-reset the device to factory defaults.",
    )
    reset_p.set_defaults(func=_cmd_reset)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
