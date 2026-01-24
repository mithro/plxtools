"""Tests for EEPROM controller."""

import struct
import tempfile
from pathlib import Path

import pytest

from plxtools.backends import MockEepromBackend
from plxtools.eeprom import EepromController, EepromInfo, read_eeprom


def create_valid_eeprom(payload: bytes | None = None) -> bytes:
    """Create a valid EEPROM image with header."""
    if payload is None:
        # Default: one register write (port 0, reg 0x100, value 0x12345678)
        # Format: 2-byte addr + 4-byte value = 6 bytes
        payload = struct.pack("<HI", 0x0040, 0x12345678)  # addr = (0x100 >> 2) | (0 << 10)

    # Header: signature (0x5A), reserved (0x00), payload length (16-bit LE)
    header = struct.pack("<BBH", 0x5A, 0x00, len(payload))
    return header + payload


class TestEepromController:
    """Tests for EepromController."""

    def test_detect_valid_eeprom(self) -> None:
        """Detect valid EEPROM with correct signature."""
        eeprom_data = create_valid_eeprom()
        backend = MockEepromBackend(eeprom_data=eeprom_data)
        controller = EepromController(backend)

        info = controller.detect_eeprom()

        assert info.valid is True
        assert info.signature == 0x5A
        assert info.payload_length == 6
        assert info.total_size == 10  # 4 byte header + 6 byte payload

    def test_detect_invalid_eeprom(self) -> None:
        """Detect invalid EEPROM (wrong signature)."""
        eeprom_data = bytes([0xFF, 0x00, 0x00, 0x00])  # Invalid signature
        backend = MockEepromBackend(eeprom_data=eeprom_data)
        controller = EepromController(backend)

        info = controller.detect_eeprom()

        assert info.valid is False
        assert info.signature == 0xFF

    def test_detect_empty_eeprom(self) -> None:
        """Detect empty EEPROM (all zeros)."""
        backend = MockEepromBackend()  # Default is all zeros
        controller = EepromController(backend)

        info = controller.detect_eeprom()

        assert info.valid is False
        assert info.signature == 0x00

    def test_read_byte(self) -> None:
        """Read individual bytes from EEPROM."""
        eeprom_data = bytes(range(16))  # 0x00, 0x01, ..., 0x0F
        backend = MockEepromBackend(eeprom_data=eeprom_data)
        controller = EepromController(backend)

        assert controller.read_byte(0) == 0x00
        assert controller.read_byte(1) == 0x01
        assert controller.read_byte(4) == 0x04
        assert controller.read_byte(15) == 0x0F

    def test_read_word(self) -> None:
        """Read 16-bit words from EEPROM."""
        eeprom_data = bytes([0x34, 0x12, 0x78, 0x56])
        backend = MockEepromBackend(eeprom_data=eeprom_data)
        controller = EepromController(backend)

        assert controller.read_word(0) == 0x1234
        assert controller.read_word(2) == 0x5678

    def test_read_bytes(self) -> None:
        """Read byte sequences from EEPROM."""
        eeprom_data = bytes(range(32))
        backend = MockEepromBackend(eeprom_data=eeprom_data)
        controller = EepromController(backend)

        # Read aligned sequence
        data = controller.read_bytes(0, 8)
        assert data == bytes(range(8))

        # Read unaligned sequence
        data = controller.read_bytes(3, 5)
        assert data == bytes(range(3, 8))

    def test_read_bytes_optimized_dword(self) -> None:
        """Read bytes uses optimized dword reads when aligned."""
        eeprom_data = bytes(range(16))
        backend = MockEepromBackend(eeprom_data=eeprom_data)
        controller = EepromController(backend)

        # Read 8 aligned bytes - should use 2 dword reads
        data = controller.read_bytes(0, 8)
        assert data == bytes(range(8))

        # Check that reads were made (we can't easily verify optimization,
        # but we verify correctness)
        assert len(backend.read_log) > 0

    def test_read_all_valid_eeprom(self) -> None:
        """Read all contents of a valid EEPROM."""
        payload = bytes(range(12))  # 12 bytes = 2 register writes
        eeprom_data = create_valid_eeprom(payload)
        backend = MockEepromBackend(eeprom_data=eeprom_data)
        controller = EepromController(backend)

        data = controller.read_all()

        # Should read header + payload
        assert data[:4] == bytes([0x5A, 0x00, 12, 0])  # Header
        assert data[4:16] == payload

    def test_read_all_respects_max_size(self) -> None:
        """read_all respects max_size parameter."""
        eeprom_data = bytes(range(256))
        backend = MockEepromBackend(eeprom_data=eeprom_data)
        controller = EepromController(backend)

        data = controller.read_all(max_size=32)

        assert len(data) == 32
        assert data == bytes(range(32))

    def test_dump_to_file(self, tmp_path: Path) -> None:
        """Dump EEPROM to file."""
        eeprom_data = create_valid_eeprom()
        backend = MockEepromBackend(eeprom_data=eeprom_data)
        controller = EepromController(backend)

        output_file = tmp_path / "eeprom.bin"
        bytes_written = controller.dump_to_file(str(output_file))

        assert output_file.exists()
        assert bytes_written == 10  # 4 byte header + 6 byte payload
        assert output_file.read_bytes() == eeprom_data[:10]

    def test_controller_with_device_definition(self) -> None:
        """Controller uses device definition parameters."""
        from plxtools.devices import load_device_by_name

        eeprom_data = create_valid_eeprom()
        backend = MockEepromBackend(eeprom_data=eeprom_data)
        device_def = load_device_by_name("PEX8733")

        controller = EepromController(backend, device_def)

        # Verify it uses device-specific parameters
        assert controller._ctrl_offset == 0x260
        assert controller._signature == 0x5A

        info = controller.detect_eeprom()
        assert info.valid is True


class TestReadEepromConvenience:
    """Tests for read_eeprom convenience function."""

    def test_read_eeprom_without_device_id(self) -> None:
        """read_eeprom works without device ID."""
        eeprom_data = create_valid_eeprom()
        backend = MockEepromBackend(eeprom_data=eeprom_data)

        data = read_eeprom(backend)

        assert data[:4] == bytes([0x5A, 0x00, 6, 0])

    def test_read_eeprom_with_device_id(self) -> None:
        """read_eeprom works with device ID."""
        eeprom_data = create_valid_eeprom()
        backend = MockEepromBackend(eeprom_data=eeprom_data)

        data = read_eeprom(backend, vendor_id=0x10B5, device_id=0x8733)

        assert data[:4] == bytes([0x5A, 0x00, 6, 0])


class TestEepromInfo:
    """Tests for EepromInfo dataclass."""

    def test_eeprom_info_fields(self) -> None:
        """EepromInfo has expected fields."""
        info = EepromInfo(
            valid=True,
            signature=0x5A,
            payload_length=100,
            address_width=2,
            total_size=104,
        )

        assert info.valid is True
        assert info.signature == 0x5A
        assert info.payload_length == 100
        assert info.address_width == 2
        assert info.total_size == 104
