"""Tests for hardware access backends."""

import pytest

from plxtools.backends import MockBackend, MockEepromBackend, RegisterAccess


class TestMockBackend:
    """Tests for MockBackend."""

    def test_implements_protocol(self) -> None:
        """MockBackend implements RegisterAccess protocol."""
        backend = MockBackend()
        assert isinstance(backend, RegisterAccess)

    def test_read_unset_register_returns_zero(self) -> None:
        """Reading an unset register returns 0."""
        backend = MockBackend()
        assert backend.read32(0x00) == 0
        assert backend.read32(0x100) == 0

    def test_write_then_read(self) -> None:
        """Written values can be read back."""
        backend = MockBackend()
        backend.write32(0x100, 0xDEADBEEF)
        assert backend.read32(0x100) == 0xDEADBEEF

    def test_prepopulated_registers(self) -> None:
        """Registers can be pre-populated at initialization."""
        backend = MockBackend(registers={0x00: 0x12345678, 0x04: 0xABCDEF00})
        assert backend.read32(0x00) == 0x12345678
        assert backend.read32(0x04) == 0xABCDEF00

    def test_read_log(self) -> None:
        """Read operations are logged."""
        backend = MockBackend()
        backend.read32(0x00)
        backend.read32(0x04)
        backend.read32(0x00)
        assert backend.read_log == [(0x00,), (0x04,), (0x00,)]

    def test_write_log(self) -> None:
        """Write operations are logged."""
        backend = MockBackend()
        backend.write32(0x00, 0x1234)
        backend.write32(0x04, 0x5678)
        assert backend.write_log == [(0x00, 0x1234), (0x04, 0x5678)]

    def test_reset_logs(self) -> None:
        """reset_logs() clears read and write logs."""
        backend = MockBackend()
        backend.read32(0x00)
        backend.write32(0x04, 0x1234)
        backend.reset_logs()
        assert backend.read_log == []
        assert backend.write_log == []

    def test_set_register_no_log(self) -> None:
        """set_register() does not log."""
        backend = MockBackend()
        backend.set_register(0x100, 0xABCD)
        assert backend.write_log == []
        assert backend.read32(0x100) == 0xABCD

    def test_get_register_no_log(self) -> None:
        """get_register() does not log."""
        backend = MockBackend(registers={0x100: 0xABCD})
        assert backend.get_register(0x100) == 0xABCD
        assert backend.read_log == []

    def test_context_manager(self) -> None:
        """Backend can be used as context manager."""
        with MockBackend() as backend:
            backend.write32(0x00, 0x1234)
            assert backend.read32(0x00) == 0x1234

    def test_invalid_offset_negative(self) -> None:
        """Negative offset raises ValueError."""
        backend = MockBackend()
        with pytest.raises(ValueError, match="non-negative"):
            backend.read32(-4)

    def test_invalid_offset_unaligned(self) -> None:
        """Unaligned offset raises ValueError."""
        backend = MockBackend()
        with pytest.raises(ValueError, match="4-byte aligned"):
            backend.read32(0x03)

    def test_invalid_value_negative(self) -> None:
        """Negative value raises ValueError."""
        backend = MockBackend()
        with pytest.raises(ValueError, match="0-0xFFFFFFFF"):
            backend.write32(0x00, -1)

    def test_invalid_value_too_large(self) -> None:
        """Value > 32 bits raises ValueError."""
        backend = MockBackend()
        with pytest.raises(ValueError, match="0-0xFFFFFFFF"):
            backend.write32(0x00, 0x100000000)


class TestMockEepromBackend:
    """Tests for MockEepromBackend."""

    def test_eeprom_read_sequence(self) -> None:
        """EEPROM read command sequence returns correct data."""
        # Set up EEPROM with test data
        eeprom_data = bytes([0x5A, 0x00, 0x12, 0x34])  # Signature + data
        backend = MockEepromBackend(eeprom_data=eeprom_data)

        # Write read command for address 0
        cmd = 0x00A06000 | 0  # Read command + address
        backend.write32(0x260, cmd)

        # Read data
        result = backend.read32(0x264)
        assert result == 0x3412005A  # Little-endian: 5A 00 12 34

    def test_eeprom_read_different_addresses(self) -> None:
        """EEPROM reads at different addresses work correctly."""
        eeprom_data = bytes(range(256))  # 0x00, 0x01, ..., 0xFF
        backend = MockEepromBackend(eeprom_data=eeprom_data)

        # Read at address 4
        backend.write32(0x260, 0x00A06000 | 4)
        result = backend.read32(0x264)
        assert result == 0x07060504  # Bytes 4, 5, 6, 7 in little-endian

        # Read at address 100
        backend.write32(0x260, 0x00A06000 | 100)
        result = backend.read32(0x264)
        assert result == 0x67666564  # Bytes 100, 101, 102, 103

    def test_eeprom_control_register_not_busy(self) -> None:
        """Control register never shows busy bit in mock."""
        backend = MockEepromBackend()
        backend.write32(0x260, 0x80000000)  # Set busy bit
        status = backend.read32(0x260)
        assert (status & 0x80000000) == 0  # Busy bit should be cleared

    def test_set_eeprom_byte(self) -> None:
        """set_eeprom_byte() updates individual bytes."""
        backend = MockEepromBackend()
        backend.set_eeprom_byte(0, 0x5A)
        backend.set_eeprom_byte(1, 0xAB)

        backend.write32(0x260, 0x00A06000 | 0)
        result = backend.read32(0x264)
        assert (result & 0xFF) == 0x5A
        assert ((result >> 8) & 0xFF) == 0xAB

    def test_set_eeprom_data(self) -> None:
        """set_eeprom_data() updates byte ranges."""
        backend = MockEepromBackend()
        backend.set_eeprom_data(b"\x5A\x00\x06\x00", start_addr=0)

        backend.write32(0x260, 0x00A06000 | 0)
        result = backend.read32(0x264)
        assert result == 0x0006005A

    def test_eeprom_address_validation(self) -> None:
        """Invalid EEPROM addresses raise ValueError."""
        backend = MockEepromBackend()
        with pytest.raises(ValueError, match="out of range"):
            backend.set_eeprom_byte(10000, 0x00)

    def test_inherits_mock_backend_features(self) -> None:
        """MockEepromBackend inherits MockBackend features."""
        backend = MockEepromBackend(registers={0x100: 0xABCD})
        assert backend.read32(0x100) == 0xABCD
        backend.write32(0x200, 0x1234)
        assert backend.read32(0x200) == 0x1234
