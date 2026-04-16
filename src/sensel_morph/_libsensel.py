"""Internal shim that makes the vendored lib/sensel.py importable.

The ctypes wrapper lives outside the package at ``lib/sensel.py`` (next to
the vendored C source). This module adjusts sys.path once and re-exports it
so the rest of the package can ``from sensel_morph._libsensel import sensel``
without caring where it lives.
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import sensel  # noqa: E402  (sys.path mutation above)  # ty: ignore[unresolved-import]

__all__ = ["sensel"]
