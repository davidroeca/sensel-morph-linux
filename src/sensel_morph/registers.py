"""Register definitions for the Sensel Morph.

Maps register addresses and sizes from sensel_register_map.h into typed
Python objects. Provides encoding/decoding helpers for reading and writing
device configuration as structured data.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True, slots=True)
class RegDef:
    """A single register definition: address, byte size, and signedness."""

    addr: int
    size: int
    signed: bool = False
    writable: bool = False

    def decode(self, buf: bytes | list[int]) -> int:
        """Decode a register value from raw bytes (little-endian)."""
        raw = bytes(b & 0xFF for b in buf[: self.size])
        if self.size == 1:
            fmt = "b" if self.signed else "B"
        elif self.size == 2:
            fmt = "<h" if self.signed else "<H"
        elif self.size == 4:
            fmt = "<i" if self.signed else "<I"
        else:
            raise ValueError(f"unsupported register size {self.size}")
        return struct.unpack(fmt, raw)[0]

    def encode(self, value: int) -> list[int]:
        """Encode an integer value into register bytes (little-endian)."""
        if self.size == 1:
            fmt = "b" if self.signed else "B"
        elif self.size == 2:
            fmt = "<h" if self.signed else "<H"
        elif self.size == 4:
            fmt = "<i" if self.signed else "<I"
        else:
            raise ValueError(f"unsupported register size {self.size}")
        return list(struct.pack(fmt, value))


# ---------------------------------------------------------------------------
# Read-only info registers
# ---------------------------------------------------------------------------

FW_VERSION_PROTOCOL = RegDef(addr=0x06, size=1)
FW_VERSION_MAJOR = RegDef(addr=0x07, size=1)
FW_VERSION_MINOR = RegDef(addr=0x08, size=1)
FW_VERSION_BUILD = RegDef(addr=0x09, size=2)
FW_VERSION_RELEASE = RegDef(addr=0x0B, size=1)
DEVICE_ID = RegDef(addr=0x0C, size=2)
DEVICE_REVISION = RegDef(addr=0x0E, size=1)
DEVICE_SERIAL_NUMBER = RegDef(addr=0x0F, size=1)
SENSOR_NUM_COLS = RegDef(addr=0x10, size=2)
SENSOR_NUM_ROWS = RegDef(addr=0x12, size=2)
SENSOR_ACTIVE_AREA_WIDTH_UM = RegDef(addr=0x14, size=4)
SENSOR_ACTIVE_AREA_HEIGHT_UM = RegDef(addr=0x18, size=4)
CONTACTS_MAX_COUNT = RegDef(addr=0x40, size=1)
FRAME_CONTENT_SUPPORTED = RegDef(addr=0x28, size=1)
LED_BRIGHTNESS_SIZE = RegDef(addr=0x81, size=1)
LED_BRIGHTNESS_MAX = RegDef(addr=0x82, size=2)
LED_COUNT = RegDef(addr=0x84, size=1)
UNIT_SHIFT_DIMS = RegDef(addr=0xA0, size=1)
UNIT_SHIFT_FORCE = RegDef(addr=0xA1, size=1)
UNIT_SHIFT_AREA = RegDef(addr=0xA2, size=1)
UNIT_SHIFT_ANGLE = RegDef(addr=0xA3, size=1)
UNIT_SHIFT_TIME = RegDef(addr=0xA4, size=1)
BATTERY_STATUS = RegDef(addr=0x70, size=1)
BATTERY_PERCENTAGE = RegDef(addr=0x71, size=1)
ERROR_CODE = RegDef(addr=0xEC, size=1)

# ---------------------------------------------------------------------------
# Writable configuration registers
# ---------------------------------------------------------------------------

SCAN_FRAME_RATE = RegDef(addr=0x20, size=2, writable=True)
SCAN_BUFFER_CONTROL = RegDef(addr=0x22, size=1, writable=True)
SCAN_DETAIL_CONTROL = RegDef(addr=0x23, size=1, writable=True)
FRAME_CONTENT_CONTROL = RegDef(addr=0x24, size=1, writable=True)
CONTACTS_ENABLE_BLOB_MERGE = RegDef(addr=0x41, size=1, writable=True)
CONTACTS_MIN_FORCE = RegDef(addr=0x47, size=2, writable=True)
CONTACTS_MASK = RegDef(addr=0x4B, size=1, writable=True)
BASELINE_ENABLED = RegDef(addr=0x50, size=1, writable=True)
BASELINE_INCREASE_RATE = RegDef(addr=0x51, size=2, writable=True)
BASELINE_DECREASE_RATE = RegDef(addr=0x53, size=2, writable=True)
BASELINE_DYNAMIC_ENABLED = RegDef(addr=0x57, size=1, writable=True)
LED_BRIGHTNESS = RegDef(addr=0x80, size=1, writable=True)


@dataclass(slots=True)
class DeviceConfig:
    """Configurable device register state.

    Each field corresponds to a writable register on the Morph. Values
    are plain Python ints; encoding/decoding is handled by the RegDef
    objects in CONFIG_FIELDS.
    """

    scan_frame_rate: int = 0
    scan_buffer_control: int = 0
    scan_detail_control: int = 0
    frame_content_control: int = 0
    contacts_enable_blob_merge: int = 0
    contacts_min_force: int = 0
    contacts_mask: int = 0
    baseline_enabled: int = 0
    baseline_increase_rate: int = 0
    baseline_decrease_rate: int = 0
    baseline_dynamic_enabled: int = 0
    led_brightness: int = 0


# Maps DeviceConfig field names to their register definitions.
CONFIG_FIELDS: dict[str, RegDef] = {
    "scan_frame_rate": SCAN_FRAME_RATE,
    "scan_buffer_control": SCAN_BUFFER_CONTROL,
    "scan_detail_control": SCAN_DETAIL_CONTROL,
    "frame_content_control": FRAME_CONTENT_CONTROL,
    "contacts_enable_blob_merge": CONTACTS_ENABLE_BLOB_MERGE,
    "contacts_min_force": CONTACTS_MIN_FORCE,
    "contacts_mask": CONTACTS_MASK,
    "baseline_enabled": BASELINE_ENABLED,
    "baseline_increase_rate": BASELINE_INCREASE_RATE,
    "baseline_decrease_rate": BASELINE_DECREASE_RATE,
    "baseline_dynamic_enabled": BASELINE_DYNAMIC_ENABLED,
    "led_brightness": LED_BRIGHTNESS,
}


def config_to_dict(cfg: DeviceConfig) -> dict[str, int]:
    """Serialize a DeviceConfig to a plain dict for YAML output."""
    return {f.name: getattr(cfg, f.name) for f in fields(cfg)}


def config_from_dict(data: dict[str, Any]) -> DeviceConfig:
    """Deserialize a DeviceConfig from a plain dict (e.g. loaded YAML).

    Unknown keys are silently ignored so files dumped by a newer
    firmware version can be loaded on an older one.
    """
    valid = {f.name for f in fields(DeviceConfig)}
    filtered = {k: int(v) for k, v in data.items() if k in valid}
    return DeviceConfig(**filtered)
