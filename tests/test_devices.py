"""Tests for device definitions and loader."""

from pathlib import Path

import pytest

from plxtools.devices import (
    DeviceDefinition,
    Register,
    RegisterField,
    list_available_devices,
    load_device_by_id,
    load_device_by_name,
    load_device_definition,
)
from plxtools.devices.loader import DEVICES_PATH


class TestRegisterField:
    """Tests for RegisterField."""

    def test_single_bit_mask(self) -> None:
        """Single bit field has correct mask."""
        field = RegisterField(name="enable", description="", bit=0)
        assert field.mask == 0x1
        assert field.shift == 0

    def test_single_bit_high(self) -> None:
        """High single bit has correct mask."""
        field = RegisterField(name="busy", description="", bit=31)
        assert field.mask == 0x80000000
        assert field.shift == 31

    def test_bit_range_mask(self) -> None:
        """Bit range has correct mask."""
        field = RegisterField(name="address", description="", bits=(0, 12))
        assert field.mask == 0x1FFF  # 13 bits
        assert field.shift == 0

    def test_bit_range_offset(self) -> None:
        """Bit range with offset has correct mask."""
        field = RegisterField(name="device_id", description="", bits=(16, 31))
        assert field.mask == 0xFFFF0000
        assert field.shift == 16

    def test_extract_single_bit(self) -> None:
        """Extract single bit value."""
        field = RegisterField(name="busy", description="", bit=31)
        assert field.extract(0x80000000) == 1
        assert field.extract(0x7FFFFFFF) == 0

    def test_extract_bit_range(self) -> None:
        """Extract bit range value."""
        field = RegisterField(name="device_id", description="", bits=(16, 31))
        assert field.extract(0x87330000) == 0x8733

    def test_insert_single_bit(self) -> None:
        """Insert single bit value."""
        field = RegisterField(name="enable", description="", bit=0)
        assert field.insert(0x00, 1) == 0x01
        assert field.insert(0xFF, 0) == 0xFE

    def test_insert_bit_range(self) -> None:
        """Insert bit range value."""
        field = RegisterField(name="address", description="", bits=(0, 12))
        assert field.insert(0x00A06000, 0x100) == 0x00A06100


class TestRegister:
    """Tests for Register."""

    def test_port_offset_not_per_port(self) -> None:
        """Non-per-port register has same offset for all ports."""
        reg = Register(
            name="eeprom_ctrl",
            offset=0x260,
            size=4,
            access="rw",
            description="",
            per_port=False,
        )
        assert reg.port_offset(0) == 0x260
        assert reg.port_offset(1) == 0x260
        assert reg.port_offset(7) == 0x260

    def test_port_offset_per_port(self) -> None:
        """Per-port register calculates offset correctly."""
        reg = Register(
            name="port_control",
            offset=0x208,
            size=4,
            access="rw",
            description="",
            per_port=True,
            port_stride=0x1000,
        )
        assert reg.port_offset(0) == 0x208
        assert reg.port_offset(1) == 0x1208
        assert reg.port_offset(7) == 0x7208


class TestDeviceLoader:
    """Tests for device definition loader."""

    def test_devices_path_exists(self) -> None:
        """The devices directory exists."""
        assert DEVICES_PATH.exists()
        assert DEVICES_PATH.is_dir()

    def test_load_pex8733(self) -> None:
        """Load PEX8733 device definition."""
        definition = load_device_by_name("PEX8733")
        assert definition is not None
        assert definition.info.vendor_id == 0x10B5
        assert definition.info.device_id == 0x8733
        assert definition.info.name == "PEX8733"
        assert definition.info.ports == 8
        assert definition.info.lanes == 32

    def test_load_pex8696(self) -> None:
        """Load PEX8696 device definition."""
        definition = load_device_by_name("PEX8696")
        assert definition is not None
        assert definition.info.vendor_id == 0x10B5
        assert definition.info.device_id == 0x8696
        assert definition.info.name == "PEX8696"
        assert definition.info.ports == 24
        assert definition.info.lanes == 96

    def test_load_by_id(self) -> None:
        """Load device by vendor/device ID."""
        definition = load_device_by_id(0x10B5, 0x8733)
        assert definition is not None
        assert definition.info.name == "PEX8733"

    def test_load_nonexistent_device(self) -> None:
        """Loading nonexistent device returns None."""
        definition = load_device_by_name("NONEXISTENT")
        assert definition is None

    def test_load_nonexistent_id(self) -> None:
        """Loading nonexistent ID returns None."""
        definition = load_device_by_id(0x9999, 0x9999)
        assert definition is None

    def test_list_available_devices(self) -> None:
        """List available devices returns expected devices."""
        devices = list_available_devices()
        assert "PEX8733" in devices
        assert "PEX8696" in devices

    def test_eeprom_config(self) -> None:
        """EEPROM configuration is loaded correctly."""
        definition = load_device_by_name("PEX8733")
        assert definition is not None
        assert definition.eeprom.ctrl_offset == 0x260
        assert definition.eeprom.data_offset == 0x264
        assert definition.eeprom.read_cmd == 0x00A06000
        assert definition.eeprom.addr_mask == 0x1FFF
        assert definition.eeprom.signature == 0x5A

    def test_registers_loaded(self) -> None:
        """Registers are loaded from definition."""
        definition = load_device_by_name("PEX8733")
        assert definition is not None
        assert "eeprom_ctrl" in definition.registers
        assert "eeprom_data" in definition.registers

        ctrl = definition.registers["eeprom_ctrl"]
        assert ctrl.offset == 0x260
        assert ctrl.access == "rw"
        assert "address" in ctrl.fields
        assert "busy" in ctrl.fields

    def test_get_register_by_offset(self) -> None:
        """Get register by offset works."""
        definition = load_device_by_name("PEX8733")
        assert definition is not None

        reg = definition.get_register_by_offset(0x260)
        assert reg is not None
        assert reg.name == "eeprom_ctrl"

    def test_case_insensitive_name_lookup(self) -> None:
        """Device name lookup is case-insensitive."""
        assert load_device_by_name("pex8733") is not None
        assert load_device_by_name("PEX8733") is not None
        assert load_device_by_name("Pex8733") is not None
