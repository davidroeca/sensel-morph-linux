"""Pygame contact visualizer for the Sensel Morph.

Opens a window scaled to the device's aspect ratio. Each active contact is
drawn as a circle whose radius reflects *area* and whose colour reflects
*force*. Trails (the last N positions per contact id) can be toggled with
the T key. Press Escape or close the window to quit.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict, deque

import pygame

from sensel_morph import (
    CONTACT_END,
    Device,
    DeviceError,
)

_DEFAULT_SCALE = 4
_TRAIL_LENGTH = 120
_BG_COLOR = (18, 18, 24)
_GRID_COLOR = (36, 36, 48)


def _force_to_color(force: float, max_force: float) -> tuple[int, int, int]:
    t = min(force / max(max_force, 1.0), 1.0)
    if t < 0.5:
        r = int(60 + 390 * t)
        g = int(120 * t)
        b = int(255 * (1.0 - 2.0 * t))
    else:
        r = 255
        g = int(255 * (2.0 * t - 1.0))
        b = 0
    return (min(r, 255), min(g, 255), min(b, 255))


def _draw_grid(
    surface: pygame.Surface,
    width_mm: float,
    height_mm: float,
    scale: float,
    spacing_mm: float = 10.0,
) -> None:
    x = 0.0
    while x <= width_mm:
        px = int(x * scale)
        pygame.draw.line(
            surface, _GRID_COLOR, (px, 0), (px, surface.get_height())
        )
        x += spacing_mm
    y = 0.0
    while y <= height_mm:
        py = int(y * scale)
        pygame.draw.line(
            surface, _GRID_COLOR, (0, py), (surface.get_width(), py)
        )
        y += spacing_mm


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pygame contact visualizer for the Sensel Morph."
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=_DEFAULT_SCALE,
        help=f"pixels per mm (default: {_DEFAULT_SCALE})",
    )
    parser.add_argument(
        "--max-force",
        type=float,
        default=500.0,
        help="force in grams that maps to full red (default: 500)",
    )
    parser.add_argument(
        "--fps-cap",
        type=int,
        default=125,
        help="max frames per second to render (default: 125)",
    )
    args = parser.parse_args(argv)

    pygame.init()

    try:
        with Device() as dev:
            info = dev.sensor_info()
            win_w = int(info.width_mm * args.scale)
            win_h = int(info.height_mm * args.scale)
            screen = pygame.display.set_mode((win_w, win_h))
            pygame.display.set_caption("Sensel Morph Visualizer")
            clock = pygame.time.Clock()
            font = pygame.font.SysFont("monospace", 14)

            trails: dict[int, deque[tuple[int, int]]] = defaultdict(
                lambda: deque(maxlen=_TRAIL_LENGTH)
            )
            show_trails = False
            for frame_count, frame in enumerate(dev.frames()):
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        return 0
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            pygame.quit()
                            return 0
                        if event.key == pygame.K_t:
                            show_trails = not show_trails
                            if not show_trails:
                                trails.clear()

                screen.fill(_BG_COLOR)
                _draw_grid(screen, info.width_mm, info.height_mm, args.scale)

                active_ids: set[int] = set()
                for c in frame.contacts:
                    active_ids.add(c.id)
                    px = int(c.x * args.scale)
                    py = int(c.y * args.scale)
                    radius_mm = math.sqrt(max(c.area, 0.0) / math.pi)
                    radius_px = max(int(radius_mm * args.scale), 3)

                    trails[c.id].append((px, py))

                    color = _force_to_color(c.force, args.max_force)

                    if show_trails:
                        pts = trails[c.id]
                        if len(pts) >= 2:
                            trail_list = list(pts)
                            for i in range(1, len(trail_list)):
                                alpha = i / len(trail_list)
                                trail_color = (
                                    int(color[0] * alpha * 0.4),
                                    int(color[1] * alpha * 0.4),
                                    int(color[2] * alpha * 0.4),
                                )
                                pygame.draw.line(
                                    screen,
                                    trail_color,
                                    trail_list[i - 1],
                                    trail_list[i],
                                    2,
                                )

                    if c.state == CONTACT_END:
                        pygame.draw.circle(
                            screen, (80, 80, 80), (px, py), radius_px, 1
                        )
                    else:
                        pygame.draw.circle(screen, color, (px, py), radius_px)
                        highlight = (
                            min(color[0] + 60, 255),
                            min(color[1] + 60, 255),
                            min(color[2] + 60, 255),
                        )
                        inner = max(radius_px // 3, 1)
                        pygame.draw.circle(screen, highlight, (px, py), inner)

                ended_ids = [cid for cid in trails if cid not in active_ids]
                for cid in ended_ids:
                    if not show_trails:
                        del trails[cid]

                hud = font.render(
                    f"frame {frame_count}  contacts {len(frame.contacts)}"
                    f"  trails {'ON' if show_trails else 'OFF'} (T)"
                    f"  FPS {clock.get_fps():.0f}",
                    True,
                    (160, 160, 180),
                )
                screen.blit(hud, (6, 4))

                pygame.display.flip()
                clock.tick(args.fps_cap)

    except DeviceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        pygame.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
