"""Live terminal monitor for Sensel Morph contacts.

Renders the current contact set each frame using ANSI escapes. Exits cleanly
on Ctrl-C. Useful as a baseline debugging tool for every later milestone.
"""

from __future__ import annotations

import signal
import sys
import time
from typing import NoReturn

from sensel_morph import (
    CONTACT_END,
    CONTACT_MOVE,
    CONTACT_START,
    Device,
    DeviceError,
)

_STATE_LABELS = {
    CONTACT_START: "START",
    CONTACT_MOVE: "MOVE ",
    CONTACT_END: "END  ",
}

_CLEAR_SCREEN = "\x1b[2J"
_CURSOR_HOME = "\x1b[H"
_HIDE_CURSOR = "\x1b[?25l"
_SHOW_CURSOR = "\x1b[?25h"


def _install_sigint() -> None:
    def handler(*_: object) -> NoReturn:
        sys.stdout.write(_SHOW_CURSOR)
        sys.stdout.flush()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handler)


def main() -> int:
    _install_sigint()
    sys.stdout.write(_HIDE_CURSOR + _CLEAR_SCREEN)

    try:
        with Device() as dev:
            info = dev.sensor_info()
            last_render = 0.0
            frame_count = 0
            for frame in dev.frames():
                frame_count += 1
                # Cap redraws at ~60 Hz so the terminal stays responsive.
                now = time.monotonic()
                if now - last_render < 1.0 / 60.0:
                    continue
                last_render = now

                buf = [_CURSOR_HOME]
                buf.append(
                    f"Sensel Morph -- "
                    f"{info.width_mm:.1f}x{info.height_mm:.1f} mm, "
                    f"max {info.max_contacts} contacts  "
                    f"(frame {frame_count}, "
                    f"lost {frame.lost_frame_count})\x1b[K\n"
                )
                buf.append("-" * 72 + "\x1b[K\n")
                buf.append(
                    f"{'id':>3}  {'state':<5}  {'x_mm':>7}  {'y_mm':>7}  "
                    f"{'force_g':>8}  {'area':>6}\x1b[K\n"
                )
                if not frame.contacts:
                    buf.append("  (no active contacts)\x1b[K\n")
                else:
                    for c in frame.contacts:
                        label = _STATE_LABELS.get(c.state, f"?{c.state}")
                        buf.append(
                            f"{c.id:>3}  {label:<5}  {c.x:>7.2f}  {c.y:>7.2f}  "
                            f"{c.force:>8.2f}  {c.area:>6.1f}\x1b[K\n"
                        )
                # Clear any leftover lines from a previous larger contact set.
                buf.append("\x1b[J")
                sys.stdout.write("".join(buf))
                sys.stdout.flush()
    except DeviceError as e:
        sys.stdout.write(_SHOW_CURSOR)
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        sys.stdout.write(_SHOW_CURSOR)
        sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
