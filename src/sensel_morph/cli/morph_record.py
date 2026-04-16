"""Record N seconds of frames to a JSON file for use as a test fixture."""

from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import suppress
from pathlib import Path

from sensel_morph import Device, DeviceError, frame_to_dict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record frames from a connected Sensel Morph to JSON."
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="seconds of data to capture (default: 5.0)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="path to write the JSON fixture",
    )
    parser.add_argument(
        "--only-active",
        action="store_true",
        help="only record frames with at least one contact",
    )
    args = parser.parse_args(argv)

    frames: list[dict] = []
    try:
        with Device() as dev:
            info = dev.sensor_info()
            fw = dev.firmware_info()
            deadline = time.monotonic() + args.duration
            print(
                f"recording up to {args.duration:.1f}s... "
                f"(Ctrl-C to stop early)",
                file=sys.stderr,
            )
            with suppress(KeyboardInterrupt):
                for frame in dev.frames():
                    if args.only_active and not frame.contacts:
                        if time.monotonic() >= deadline:
                            break
                        continue
                    frames.append(frame_to_dict(frame))
                    if time.monotonic() >= deadline:
                        break
                print("stopped", file=sys.stderr)
    except DeviceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    payload = {
        "device": {
            "width_mm": info.width_mm,
            "height_mm": info.height_mm,
            "max_contacts": info.max_contacts,
            "num_rows": info.num_rows,
            "num_cols": info.num_cols,
            "firmware": fw.version,
        },
        "frames": frames,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2))
    print(f"wrote {len(frames)} frames to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
