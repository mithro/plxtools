"""Tests for I2C backend."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestI2cBackend:
    """Tests for I2cBackend."""

    def test_smbus_not_installed(self) -> None:
        """Raises ImportError when smbus2 is not available."""
        with patch.dict("sys.modules", {"smbus2": None}):
            # Need to reimport to pick up the patched module
            import importlib

            import plxtools.backends.i2c

            importlib.reload(plxtools.backends.i2c)

            with pytest.raises(ImportError, match="smbus2"):
                plxtools.backends.i2c.I2cBackend(0, 0x38)

            # Restore the module
            importlib.reload(plxtools.backends.i2c)

    def test_list_i2c_buses(self, tmp_path: Path) -> None:
        """list_i2c_buses finds I2C devices."""
        from plxtools.backends.i2c import I2cBackend

        # Just verify the method returns a list (actual /dev may or may not have i2c)
        buses = I2cBackend.list_i2c_buses()
        assert isinstance(buses, list)
        # All entries should be integers
        for bus in buses:
            assert isinstance(bus, int)

    def test_context_manager(self) -> None:
        """Backend can be used as context manager."""
        from plxtools.backends.i2c import I2cBackend

        mock_smbus = MagicMock()
        mock_smbus.read_i2c_block_data.return_value = [0, 0, 0, 0]

        with patch("plxtools.backends.i2c.SMBus", return_value=mock_smbus):
            with I2cBackend(0, 0x38) as backend:
                # Need to actually use the backend to open the SMBus
                backend.read32(0x00)

            # close() should have been called
            mock_smbus.close.assert_called_once()

    def test_read32_with_mock_smbus(self) -> None:
        """read32 correctly reads via I2C."""
        from plxtools.backends.i2c import I2cBackend

        mock_smbus = MagicMock()
        # Return bytes for a 32-bit value 0xDEADBEEF (little-endian)
        mock_smbus.read_i2c_block_data.return_value = [0xEF, 0xBE, 0xAD, 0xDE]

        with patch("plxtools.backends.i2c.SMBus", return_value=mock_smbus):
            backend = I2cBackend(0, 0x38)
            result = backend.read32(0x100)
            backend.close()

        assert result == 0xDEADBEEF
        mock_smbus.write_i2c_block_data.assert_called_once()
        mock_smbus.read_i2c_block_data.assert_called_once()

    def test_write32_with_mock_smbus(self) -> None:
        """write32 correctly writes via I2C."""
        from plxtools.backends.i2c import I2cBackend

        mock_smbus = MagicMock()

        with patch("plxtools.backends.i2c.SMBus", return_value=mock_smbus):
            backend = I2cBackend(0, 0x38)
            backend.write32(0x260, 0xDEADBEEF)
            backend.close()

        # Check the write call
        call_args = mock_smbus.write_i2c_block_data.call_args
        assert call_args is not None
        addr, high_byte, data = call_args[0]
        assert addr == 0x38  # I2C address
        assert high_byte == 0x02  # High byte of register address 0x260
        assert data[0] == 0x60  # Low byte of register address
        # Data bytes (little-endian 0xDEADBEEF)
        assert data[1:5] == [0xEF, 0xBE, 0xAD, 0xDE]

    def test_invalid_offset(self) -> None:
        """Invalid offset raises ValueError."""
        from plxtools.backends.i2c import I2cBackend

        mock_smbus = MagicMock()

        with patch("plxtools.backends.i2c.SMBus", return_value=mock_smbus):
            backend = I2cBackend(0, 0x38)
            with pytest.raises(ValueError, match="4-byte aligned"):
                backend.read32(0x03)
            backend.close()

    def test_scan_bus_with_mock(self) -> None:
        """scan_bus finds devices that respond."""
        from plxtools.backends.i2c import I2cBackend

        mock_smbus = MagicMock()

        # Simulate devices at 0x38 and 0x50 responding
        def mock_read_byte(addr: int) -> int:
            if addr in [0x38, 0x50]:
                return 0
            raise OSError("No device")

        mock_smbus.read_byte.side_effect = mock_read_byte

        with patch("plxtools.backends.i2c.SMBus", return_value=mock_smbus):
            found = I2cBackend.scan_bus(0, start=0x30, end=0x60)

        assert 0x38 in found
        assert 0x50 in found
        assert len(found) == 2

    def test_find_plx_devices_with_mock(self) -> None:
        """find_plx_devices identifies PLX switches."""
        from plxtools.backends.i2c import I2cBackend

        mock_smbus = MagicMock()

        # Simulate PLX switch at 0x38 returning vendor ID 0x10B5
        def mock_read_block(addr: int, reg: int, length: int) -> list[int]:
            if addr == 0x38:
                # Return vendor/device ID: 0x873310B5 (little-endian)
                return [0xB5, 0x10, 0x33, 0x87]
            raise OSError("No device")

        mock_smbus.read_i2c_block_data.side_effect = mock_read_block

        with patch("plxtools.backends.i2c.SMBus", return_value=mock_smbus):
            plx_devices = I2cBackend.find_plx_devices(0)

        assert 0x38 in plx_devices
