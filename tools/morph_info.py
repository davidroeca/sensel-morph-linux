"""Thin delegator so `python tools/morph_info.py` works from a checkout."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sensel_morph.cli.morph_info import main

if __name__ == "__main__":
    raise SystemExit(main())
