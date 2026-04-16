"""Register encoding/decoding and device config tests (no hardware)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from sensel_morph.registers import (
    CONFIG_FIELDS,
    CONTACTS_MIN_FORCE,
    DEVICE_ID,
    DeviceConfig,
    LED_BRIGHTNESS,
    RegDef,
    SCAN_FRAME_RATE,
    SENSOR_ACTIVE_AREA_WIDTH_UM,
    config_from_dict,
    config_to_dict,
)


class TestRegDefEncode:
    def test_encode_1byte(self) -> None:
        reg = RegDef(addr=0x80, size=1, writable=True)
        assert reg.encode(42) == [42]

    def test_encode_2byte_little_endian(self) -> None:
        reg = RegDef(addr=0x20, size=2, writable=True)
        # 0x0104 = 260 -> [0x04, 0x01] in LE
        assert reg.encode(260) == [0x04, 0x01]

    def test_encode_4byte_little_endian(self) -> None:
        reg = RegDef(addr=0x14, size=4)
        # 230000 = 0x00038270 -> [0x70, 0x82, 0x03, 0x00]
        assert reg.encode(230000) == [0x70, 0x82, 0x03, 0x00]

    def test_encode_signed_1byte(self) -> None:
        reg = RegDef(addr=0x00, size=1, signed=True)
        assert reg.encode(-1) == [0xFF]

    def test_encode_signed_2byte(self) -> None:
        reg = RegDef(addr=0x00, size=2, signed=True)
        assert reg.encode(-256) == [0x00, 0xFF]

    def test_unsupported_size_raises(self) -> None:
        reg = RegDef(addr=0x00, size=3)
        with pytest.raises(ValueError, match="unsupported register size"):
            reg.encode(0)


class TestRegDefDecode:
    def test_decode_1byte(self) -> None:
        reg = RegDef(addr=0x80, size=1)
        assert reg.decode([42]) == 42

    def test_decode_2byte_little_endian(self) -> None:
        reg = RegDef(addr=0x20, size=2)
        assert reg.decode([0x04, 0x01]) == 260

    def test_decode_4byte_little_endian(self) -> None:
        reg = RegDef(addr=0x14, size=4)
        assert reg.decode([0x70, 0x82, 0x03, 0x00]) == 230000

    def test_decode_signed_negative(self) -> None:
        reg = RegDef(addr=0x00, size=1, signed=True)
        assert reg.decode([0xFF]) == -1

    def test_decode_signed_2byte_negative(self) -> None:
        reg = RegDef(addr=0x00, size=2, signed=True)
        assert reg.decode([0x00, 0xFF]) == -256

    def test_unsupported_size_raises(self) -> None:
        reg = RegDef(addr=0x00, size=5)
        with pytest.raises(ValueError, match="unsupported register size"):
            reg.decode([0] * 5)

    def test_decode_masks_to_unsigned_bytes(self) -> None:
        """Negative c_byte values from ctypes are masked to [0, 255]."""
        reg = RegDef(addr=0x80, size=1)
        # ctypes readReg returns c_byte which can be -128..127;
        # -1 should decode as 255 unsigned
        assert reg.decode([-1]) == 255


class TestEncodeDecodeRoundtrip:
    @pytest.mark.parametrize("size", [1, 2, 4])
    def test_roundtrip_unsigned(self, size: int) -> None:
        reg = RegDef(addr=0x00, size=size)
        for val in [0, 1, (1 << (8 * size)) - 1]:
            assert reg.decode(reg.encode(val)) == val

    @pytest.mark.parametrize("size", [1, 2, 4])
    def test_roundtrip_signed(self, size: int) -> None:
        reg = RegDef(addr=0x00, size=size, signed=True)
        hi = (1 << (8 * size - 1)) - 1
        lo = -(1 << (8 * size - 1))
        for val in [0, 1, -1, hi, lo]:
            assert reg.decode(reg.encode(val)) == val


class TestDeviceConfig:
    def test_defaults_are_zero(self) -> None:
        cfg = DeviceConfig()
        d = config_to_dict(cfg)
        assert all(v == 0 for v in d.values())

    def test_to_dict_has_all_fields(self) -> None:
        cfg = DeviceConfig()
        d = config_to_dict(cfg)
        assert set(d.keys()) == set(CONFIG_FIELDS.keys())

    def test_from_dict_roundtrip(self) -> None:
        cfg = DeviceConfig(
            scan_frame_rate=125,
            contacts_min_force=50,
            led_brightness=200,
            baseline_enabled=1,
        )
        d = config_to_dict(cfg)
        cfg2 = config_from_dict(d)
        assert config_to_dict(cfg2) == d

    def test_from_dict_ignores_unknown_keys(self) -> None:
        data = {
            "scan_frame_rate": 100,
            "future_register": 42,
        }
        cfg = config_from_dict(data)
        assert cfg.scan_frame_rate == 100

    def test_from_dict_coerces_to_int(self) -> None:
        data = {"scan_frame_rate": "125"}
        cfg = config_from_dict(data)
        assert cfg.scan_frame_rate == 125
        assert isinstance(cfg.scan_frame_rate, int)


class TestConfigYamlSerialization:
    def test_dump_and_load_yaml(self) -> None:
        cfg = DeviceConfig(
            scan_frame_rate=125,
            scan_detail_control=2,
            contacts_min_force=30,
            contacts_mask=0x0F,
            baseline_enabled=1,
            baseline_increase_rate=100,
            baseline_decrease_rate=50,
            baseline_dynamic_enabled=1,
            led_brightness=180,
        )
        output = {
            "firmware_version": "1.2.3.0",
            "device_id": "0x0001",
            "config": config_to_dict(cfg),
        }
        text = yaml.safe_dump(output, default_flow_style=False)
        loaded = yaml.safe_load(text)
        cfg2 = config_from_dict(loaded["config"])
        assert config_to_dict(cfg2) == config_to_dict(cfg)

    def test_yaml_file_roundtrip(self, tmp_path: Path) -> None:
        cfg = DeviceConfig(
            scan_frame_rate=60,
            led_brightness=100,
        )
        output = {
            "firmware_version": "0.1.0.0",
            "device_id": "0xbeef",
            "config": config_to_dict(cfg),
        }
        path = tmp_path / "morph_config.yaml"
        path.write_text(yaml.safe_dump(output, default_flow_style=False))

        loaded = yaml.safe_load(path.read_text())
        cfg2 = config_from_dict(loaded["config"])
        assert cfg2.scan_frame_rate == 60
        assert cfg2.led_brightness == 100


class TestKnownRegisters:
    """Verify that known register definitions match the C header values."""

    def test_scan_frame_rate(self) -> None:
        assert SCAN_FRAME_RATE.addr == 0x20
        assert SCAN_FRAME_RATE.size == 2
        assert SCAN_FRAME_RATE.writable is True

    def test_contacts_min_force(self) -> None:
        assert CONTACTS_MIN_FORCE.addr == 0x47
        assert CONTACTS_MIN_FORCE.size == 2
        assert CONTACTS_MIN_FORCE.writable is True

    def test_led_brightness(self) -> None:
        assert LED_BRIGHTNESS.addr == 0x80
        assert LED_BRIGHTNESS.size == 1
        assert LED_BRIGHTNESS.writable is True

    def test_device_id_is_readonly(self) -> None:
        assert DEVICE_ID.addr == 0x0C
        assert DEVICE_ID.size == 2
        assert DEVICE_ID.writable is False

    def test_sensor_area_width(self) -> None:
        assert SENSOR_ACTIVE_AREA_WIDTH_UM.addr == 0x14
        assert SENSOR_ACTIVE_AREA_WIDTH_UM.size == 4
        assert SENSOR_ACTIVE_AREA_WIDTH_UM.writable is False

    def test_all_config_fields_are_writable(self) -> None:
        for name, reg in CONFIG_FIELDS.items():
            assert reg.writable, f"{name} should be writable"


class TestDeviceRegMethods:
    """Test Device.read_reg/write_reg/read_config/write_config with mocks."""

    def _mock_device(self) -> MagicMock:
        """Create a mock that stands in for the sensel module."""
        mock = MagicMock()
        mock.getDeviceList.return_value = (0, MagicMock(num_devices=1))
        dev_id = MagicMock()
        dev_id.idx = 0
        dev_id.serial_num = (0,) * 64
        dev_id.com_port = (0,) * 64
        mock.getDeviceList.return_value[1].devices = [dev_id]
        mock.openDeviceByID.return_value = (0, MagicMock())
        mock.allocateFrameData.return_value = (0, MagicMock())
        mock.setFrameContent.return_value = 0
        mock.FRAME_CONTENT_CONTACTS_MASK = 0x04
        mock.close.return_value = 0
        mock.freeFrameData.return_value = 0
        mock.stopScanning.return_value = 0
        return mock

    @patch("sensel_morph.device.sensel")
    def test_read_reg(self, mock_sensel: MagicMock) -> None:
        mock_sensel.__dict__.update(self._mock_device().__dict__)
        mock_sensel.getDeviceList = self._mock_device().getDeviceList
        mock_sensel.openDeviceByID = self._mock_device().openDeviceByID
        mock_sensel.allocateFrameData = self._mock_device().allocateFrameData
        mock_sensel.setFrameContent = self._mock_device().setFrameContent
        mock_sensel.FRAME_CONTENT_CONTACTS_MASK = 0x04
        mock_sensel.close = self._mock_device().close
        mock_sensel.freeFrameData = self._mock_device().freeFrameData
        # readReg returns (error, buf) where buf is a ctypes-like array
        mock_sensel.readReg.return_value = (0, [0x7D, 0x00])

        from sensel_morph.device import Device

        with Device() as dev:
            val = dev.read_reg(SCAN_FRAME_RATE)
        assert val == 125  # 0x007D LE

    @patch("sensel_morph.device.sensel")
    def test_write_reg_readonly_raises(self, mock_sensel: MagicMock) -> None:
        m = self._mock_device()
        mock_sensel.getDeviceList = m.getDeviceList
        mock_sensel.openDeviceByID = m.openDeviceByID
        mock_sensel.allocateFrameData = m.allocateFrameData
        mock_sensel.setFrameContent = m.setFrameContent
        mock_sensel.FRAME_CONTENT_CONTACTS_MASK = 0x04
        mock_sensel.close = m.close
        mock_sensel.freeFrameData = m.freeFrameData

        from sensel_morph.device import Device, DeviceError

        with Device() as dev:
            with pytest.raises(DeviceError, match="read-only"):
                dev.write_reg(DEVICE_ID, 0x1234)

    @patch("sensel_morph.device.sensel")
    def test_read_config_returns_device_config(
        self, mock_sensel: MagicMock
    ) -> None:
        m = self._mock_device()
        mock_sensel.getDeviceList = m.getDeviceList
        mock_sensel.openDeviceByID = m.openDeviceByID
        mock_sensel.allocateFrameData = m.allocateFrameData
        mock_sensel.setFrameContent = m.setFrameContent
        mock_sensel.FRAME_CONTENT_CONTACTS_MASK = 0x04
        mock_sensel.close = m.close
        mock_sensel.freeFrameData = m.freeFrameData

        def fake_read(handle, addr, size):
            return (0, [0] * size)

        mock_sensel.readReg.side_effect = fake_read

        from sensel_morph.device import Device

        with Device() as dev:
            cfg = dev.read_config()
        assert isinstance(cfg, DeviceConfig)
        assert cfg.scan_frame_rate == 0

    @patch("sensel_morph.device.sensel")
    def test_write_config_calls_write_reg(
        self, mock_sensel: MagicMock
    ) -> None:
        m = self._mock_device()
        mock_sensel.getDeviceList = m.getDeviceList
        mock_sensel.openDeviceByID = m.openDeviceByID
        mock_sensel.allocateFrameData = m.allocateFrameData
        mock_sensel.setFrameContent = m.setFrameContent
        mock_sensel.FRAME_CONTENT_CONTACTS_MASK = 0x04
        mock_sensel.close = m.close
        mock_sensel.freeFrameData = m.freeFrameData
        mock_sensel.writeReg.return_value = 0

        from sensel_morph.device import Device

        cfg = DeviceConfig(scan_frame_rate=60, led_brightness=200)
        with Device() as dev:
            dev.write_config(cfg)

        assert mock_sensel.writeReg.call_count == len(CONFIG_FIELDS)
