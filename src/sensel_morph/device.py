"""Context-managed device handle.

Wraps the LibSensel open/scan lifecycle so callers can write::

    with Device() as dev:
        info = dev.sensor_info()
        for frame in dev.frames():
            ...

and have scanning stopped and the device closed even on exceptions.
"""

from __future__ import annotations

import signal
from collections.abc import Iterator
from dataclasses import dataclass

from ._libsensel import sensel
from .frames import Frame, contact_from_struct
from .registers import (
    CONFIG_FIELDS,
    DeviceConfig,
    RegDef,
)


class DeviceError(RuntimeError):
    """Raised when a LibSensel call returns a non-zero error code."""


def _check(error: int, op: str) -> None:
    if error != 0:
        raise DeviceError(f"{op} failed (sensel error code {error})")


@dataclass(frozen=True, slots=True)
class SensorInfo:
    """Static device geometry reported by the sensor."""

    max_contacts: int
    num_rows: int
    num_cols: int
    width_mm: float
    height_mm: float


@dataclass(frozen=True, slots=True)
class FirmwareInfo:
    """Firmware version triple plus device identification."""

    protocol: int
    major: int
    minor: int
    build: int
    release: int
    device_id: int
    device_revision: int

    @property
    def version(self) -> str:
        return f"{self.major}.{self.minor}.{self.build}.{self.release}"


@dataclass(frozen=True, slots=True)
class DeviceIdent:
    """Identifying info for an enumerated device."""

    index: int
    serial: str
    com_port: str


def list_devices() -> list[DeviceIdent]:
    """Enumerate connected Morph devices."""
    error, dl = sensel.getDeviceList()
    _check(error, "senselGetDeviceList")
    out: list[DeviceIdent] = []
    for i in range(int(dl.num_devices)):
        d = dl.devices[i]
        serial = (
            bytes(d.serial_num).split(b"\x00", 1)[0].decode("utf-8", "replace")
        )
        com = bytes(d.com_port).split(b"\x00", 1)[0].decode("utf-8", "replace")
        out.append(DeviceIdent(index=int(d.idx), serial=serial, com_port=com))
    return out


class Device:
    """Context manager around a single opened Morph."""

    def __init__(self, index: int | None = None) -> None:
        self._index = index
        self._handle = None
        self._frame = None
        self._scanning = False

    def __enter__(self) -> Device:
        if self._index is None:
            devs = list_devices()
            if not devs:
                raise DeviceError("no Sensel Morph devices found")
            self._index = devs[0].index
        error, handle = sensel.openDeviceByID(self._index)
        _check(error, "senselOpenDeviceByID")
        self._handle = handle
        error, frame = sensel.allocateFrameData(self._handle)
        _check(error, "senselAllocateFrameData")
        self._frame = frame
        error = sensel.setFrameContent(
            self._handle, sensel.FRAME_CONTENT_CONTACTS_MASK
        )
        _check(error, "senselSetFrameContent")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Block SIGINT during cleanup so the serial stop/close
        # sequence is not interrupted by EINTR.
        old_mask = signal.pthread_sigmask(
            signal.SIG_BLOCK, {signal.SIGINT}
        )
        try:
            if self._scanning and self._handle is not None:
                sensel.stopScanning(self._handle)
                self._scanning = False
            if self._frame is not None and self._handle is not None:
                sensel.freeFrameData(self._handle, self._frame)
                self._frame = None
            if self._handle is not None:
                sensel.close(self._handle)
                self._handle = None
        except Exception:
            # Never let cleanup swallow the original exception or raise
            # on exit.
            pass
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)

    def firmware_info(self) -> FirmwareInfo:
        """Return firmware version and device identification."""
        assert self._handle is not None, "device not open"
        error, info = sensel.getFirmwareInfo(self._handle)
        _check(error, "senselGetFirmwareInfo")
        return FirmwareInfo(
            protocol=int(info.fw_protocol_version),
            major=int(info.fw_version_major),
            minor=int(info.fw_version_minor),
            build=int(info.fw_version_build),
            release=int(info.fw_version_release),
            device_id=int(info.device_id),
            device_revision=int(info.device_revision),
        )

    def sensor_info(self) -> SensorInfo:
        """Return static device geometry."""
        assert self._handle is not None, "device not open"
        error, info = sensel.getSensorInfo(self._handle)
        _check(error, "senselGetSensorInfo")
        return SensorInfo(
            max_contacts=int(info.max_contacts),
            num_rows=int(info.num_rows),
            num_cols=int(info.num_cols),
            width_mm=float(info.width),
            height_mm=float(info.height),
        )

    def read_reg(self, reg: RegDef) -> int:
        """Read a single register and return its decoded integer value."""
        assert self._handle is not None, "device not open"
        error, buf = sensel.readReg(self._handle, reg.addr, reg.size)
        _check(error, f"senselReadReg(0x{reg.addr:02x})")
        return reg.decode(buf)

    def write_reg(self, reg: RegDef, value: int) -> None:
        """Write a single register with an encoded integer value."""
        assert self._handle is not None, "device not open"
        if not reg.writable:
            raise DeviceError(f"register 0x{reg.addr:02x} is read-only")
        data = reg.encode(value)
        error = sensel.writeReg(self._handle, reg.addr, reg.size, data)
        _check(error, f"senselWriteReg(0x{reg.addr:02x})")

    def read_config(self) -> DeviceConfig:
        """Read all configurable registers into a DeviceConfig."""
        values: dict[str, int] = {}
        for name, reg in CONFIG_FIELDS.items():
            values[name] = self.read_reg(reg)
        return DeviceConfig(**values)

    def write_config(self, cfg: DeviceConfig) -> None:
        """Write a DeviceConfig to the device registers."""
        for name, reg in CONFIG_FIELDS.items():
            self.write_reg(reg, getattr(cfg, name))

    def soft_reset(self) -> None:
        """Issue a soft reset to the device."""
        assert self._handle is not None, "device not open"
        error = sensel.softReset(self._handle)
        _check(error, "senselSoftReset")

    def frames(self) -> Iterator[Frame]:
        """Yield Frame snapshots indefinitely. Starts scanning lazily.

        SIGINT is blocked while C library calls are in flight so that
        ``select()``/``read()`` on the serial fd are not interrupted by
        EINTR, which would corrupt the protocol state and leave the
        device firmware stuck in scanning mode.  The pending signal is
        checked between frames; when detected the generator returns and
        the signal mask is restored, allowing Python to deliver the
        KeyboardInterrupt for normal cleanup.
        """
        assert self._handle is not None and self._frame is not None
        if not self._scanning:
            _check(sensel.startScanning(self._handle), "senselStartScanning")
            self._scanning = True
        old_mask = signal.pthread_sigmask(
            signal.SIG_BLOCK, {signal.SIGINT}
        )
        try:
            while True:
                if signal.SIGINT in signal.sigpending():
                    return
                _check(
                    sensel.readSensor(self._handle), "senselReadSensor"
                )
                error, n = sensel.getNumAvailableFrames(self._handle)
                _check(error, "senselGetNumAvailableFrames")
                for _ in range(n):
                    _check(
                        sensel.getFrame(self._handle, self._frame),
                        "senselGetFrame",
                    )
                    contacts = tuple(
                        contact_from_struct(self._frame.contacts[i])
                        for i in range(int(self._frame.n_contacts))
                    )
                    yield Frame(
                        lost_frame_count=int(self._frame.lost_frame_count),
                        contacts=contacts,
                    )
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
