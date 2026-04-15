"""Build driver for the vendored LibSensel C source.

Runs `make` inside lib/sensel-lib/ and places the resulting libsensel.so
alongside lib/sensel.py so the ctypes wrapper can locate it.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB_DIR = ROOT / "lib"
C_DIR = LIB_DIR / "sensel-lib"
BUILD_ARTIFACT = C_DIR / "build" / "release" / "nopressure" / "libsensel.so"
DEST = LIB_DIR / "libsensel.so"


def _require(tool: str) -> None:
    """Exit with a clear message if `tool` is not on PATH."""
    if shutil.which(tool) is None:
        sys.stderr.write(
            f"error: `{tool}` not found on PATH. "
            f"Install build tools (e.g. `sudo apt install build-essential`) "
            f"and retry.\n"
        )
        sys.exit(1)


def main() -> int:
    """Compile libsensel.so and copy it next to lib/sensel.py."""
    _require("make")
    _require("gcc")

    if not C_DIR.is_dir():
        sys.stderr.write(f"error: vendored source directory missing: {C_DIR}\n")
        return 1

    try:
        subprocess.run(["make"], cwd=C_DIR, check=True)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"error: `make` failed with exit code {exc.returncode}\n")
        return exc.returncode

    if not BUILD_ARTIFACT.is_file():
        sys.stderr.write(
            f"error: expected build artifact missing: {BUILD_ARTIFACT}\n"
        )
        return 1

    shutil.copy2(BUILD_ARTIFACT, DEST)
    print(f"built {DEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
