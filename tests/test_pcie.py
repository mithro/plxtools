"""Tests for PCIe backends and discovery."""

import struct
from pathlib import Path
from unittest.mock import patch

import pytest

from plxtools.backends.pcie_mmap import PcieMmapBackend
from plxtools.backends.pcie_sysfs import PcieSysfsBackend, validate_bdf
from plxtools.discovery import PlxDevice, discover_plx_devices, discover_plx_switches


class TestBdfValidation:
    """Tests for BDF format validation (security)."""

    def test_valid_bdf(self) -> None:
        """Valid BDF formats are accepted."""
        # Should not raise
        validate_bdf("0000:03:00.0")
        validate_bdf("0000:00:00.0")
        validate_bdf("ffff:ff:ff.f")
        validate_bdf("ABCD:EF:12.3")

    def test_invalid_bdf_path_traversal(self) -> None:
        """Path traversal attempts are rejected."""
        with pytest.raises(ValueError, match="Invalid BDF format"):
            validate_bdf("../../../etc")

    def test_invalid_bdf_missing_parts(self) -> None:
        """Incomplete BDF strings are rejected."""
        with pytest.raises(ValueError, match="Invalid BDF format"):
            validate_bdf("0000:03:00")
        with pytest.raises(ValueError, match="Invalid BDF format"):
            validate_bdf("03:00.0")

    def test_invalid_bdf_wrong_separators(self) -> None:
        """Wrong separator characters are rejected."""
        with pytest.raises(ValueError, match="Invalid BDF format"):
            validate_bdf("0000-03-00.0")
        with pytest.raises(ValueError, match="Invalid BDF format"):
            validate_bdf("0000:03:00:0")

    def test_invalid_bdf_non_hex(self) -> None:
        """Non-hex characters are rejected."""
        with pytest.raises(ValueError, match="Invalid BDF format"):
            validate_bdf("ZZZZ:03:00.0")
        with pytest.raises(ValueError, match="Invalid BDF format"):
            validate_bdf("0000:GG:00.0")


class TestPlxDevice:
    """Tests for PlxDevice dataclass."""

    def test_vendor_name_plx(self) -> None:
        """PLX vendor ID returns correct name."""
        device = PlxDevice(
            bdf="0000:03:00.0",
            vendor_id=0x10B5,
            device_id=0x8733,
            subsys_vendor=0,
            subsys_device=0,
            revision=0,
            class_code=0x060400,
        )
        assert device.vendor_name == "PLX/Broadcom"

    def test_vendor_name_unknown(self) -> None:
        """Unknown vendor ID shows hex value."""
        device = PlxDevice(
            bdf="0000:03:00.0",
            vendor_id=0x1234,
            device_id=0x5678,
            subsys_vendor=0,
            subsys_device=0,
            revision=0,
            class_code=0x060400,
        )
        assert "0x1234" in device.vendor_name

    def test_device_name_known(self) -> None:
        """Known device IDs return correct names."""
        device = PlxDevice(
            bdf="0000:03:00.0",
            vendor_id=0x10B5,
            device_id=0x8733,
            subsys_vendor=0,
            subsys_device=0,
            revision=0,
            class_code=0x060400,
        )
        assert device.device_name == "PEX8733"

    def test_device_name_pex8696(self) -> None:
        """PEX8696 device ID returns correct name."""
        device = PlxDevice(
            bdf="0000:03:00.0",
            vendor_id=0x10B5,
            device_id=0x8696,
            subsys_vendor=0,
            subsys_device=0,
            revision=0,
            class_code=0x060400,
        )
        assert device.device_name == "PEX8696"

    def test_is_switch_true(self) -> None:
        """PCIe bridge class code identifies as switch."""
        device = PlxDevice(
            bdf="0000:03:00.0",
            vendor_id=0x10B5,
            device_id=0x8733,
            subsys_vendor=0,
            subsys_device=0,
            revision=0,
            class_code=0x060400,  # PCI-to-PCI bridge
        )
        assert device.is_switch is True

    def test_is_switch_false(self) -> None:
        """Non-bridge class code is not a switch."""
        device = PlxDevice(
            bdf="0000:03:00.0",
            vendor_id=0x10B5,
            device_id=0x8733,
            subsys_vendor=0,
            subsys_device=0,
            revision=0,
            class_code=0x020000,  # Network controller
        )
        assert device.is_switch is False


class TestDiscovery:
    """Tests for PLX device discovery."""

    def test_discover_with_mock_sysfs(self, tmp_path: Path) -> None:
        """Discovery finds PLX devices in mock sysfs."""
        # Create mock sysfs structure
        device_dir = tmp_path / "0000:03:00.0"
        device_dir.mkdir()
        (device_dir / "vendor").write_text("0x10b5\n")
        (device_dir / "device").write_text("0x8733\n")
        (device_dir / "subsystem_vendor").write_text("0x0000\n")
        (device_dir / "subsystem_device").write_text("0x0000\n")
        (device_dir / "revision").write_text("0xab\n")
        (device_dir / "class").write_text("0x060400\n")

        # Create a non-PLX device
        other_dir = tmp_path / "0000:00:00.0"
        other_dir.mkdir()
        (other_dir / "vendor").write_text("0x8086\n")
        (other_dir / "device").write_text("0x1234\n")

        # Patch SYSFS_PCI_PATH
        with patch("plxtools.discovery.SYSFS_PCI_PATH", tmp_path):
            devices = discover_plx_devices()

        assert len(devices) == 1
        assert devices[0].bdf == "0000:03:00.0"
        assert devices[0].vendor_id == 0x10B5
        assert devices[0].device_id == 0x8733
        assert devices[0].revision == 0xAB
        assert devices[0].class_code == 0x060400

    def test_discover_multiple_devices(self, tmp_path: Path) -> None:
        """Discovery finds multiple PLX devices."""
        for bdf in ["0000:03:00.0", "0000:04:00.0", "0000:05:00.0"]:
            device_dir = tmp_path / bdf
            device_dir.mkdir()
            (device_dir / "vendor").write_text("0x10b5\n")
            (device_dir / "device").write_text("0x8696\n")
            (device_dir / "class").write_text("0x060400\n")

        with patch("plxtools.discovery.SYSFS_PCI_PATH", tmp_path):
            devices = discover_plx_devices()

        assert len(devices) == 3
        assert [d.bdf for d in devices] == [
            "0000:03:00.0",
            "0000:04:00.0",
            "0000:05:00.0",
        ]

    def test_discover_switches_only(self, tmp_path: Path) -> None:
        """discover_plx_switches filters to switches only."""
        # Switch
        switch_dir = tmp_path / "0000:03:00.0"
        switch_dir.mkdir()
        (switch_dir / "vendor").write_text("0x10b5\n")
        (switch_dir / "device").write_text("0x8733\n")
        (switch_dir / "class").write_text("0x060400\n")

        # Non-switch (endpoint)
        endpoint_dir = tmp_path / "0000:04:00.0"
        endpoint_dir.mkdir()
        (endpoint_dir / "vendor").write_text("0x10b5\n")
        (endpoint_dir / "device").write_text("0x8733\n")
        (endpoint_dir / "class").write_text("0x020000\n")  # Network class

        with patch("plxtools.discovery.SYSFS_PCI_PATH", tmp_path):
            switches = discover_plx_switches()

        assert len(switches) == 1
        assert switches[0].bdf == "0000:03:00.0"

    def test_discover_empty_sysfs(self, tmp_path: Path) -> None:
        """Discovery returns empty list for empty sysfs."""
        with patch("plxtools.discovery.SYSFS_PCI_PATH", tmp_path):
            devices = discover_plx_devices()

        assert devices == []

    def test_discover_missing_sysfs(self, tmp_path: Path) -> None:
        """Discovery returns empty list for missing sysfs path."""
        missing_path = tmp_path / "nonexistent"
        with patch("plxtools.discovery.SYSFS_PCI_PATH", missing_path):
            devices = discover_plx_devices()

        assert devices == []


class TestPcieSysfsBackend:
    """Tests for PcieSysfsBackend."""

    def test_device_not_found(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError for missing device."""
        with patch.object(PcieSysfsBackend, "SYSFS_PCI_PATH", tmp_path):
            with pytest.raises(FileNotFoundError, match="0000:99:00.0"):
                PcieSysfsBackend("0000:99:00.0")

    def test_find_plx_devices(self, tmp_path: Path) -> None:
        """find_plx_devices returns list of PLX device BDFs."""
        # Create mock devices
        for bdf, vendor in [
            ("0000:03:00.0", "0x10b5"),
            ("0000:04:00.0", "0x8086"),
            ("0000:05:00.0", "0x10b5"),
        ]:
            device_dir = tmp_path / bdf
            device_dir.mkdir()
            (device_dir / "vendor").write_text(f"{vendor}\n")

        with patch.object(PcieSysfsBackend, "SYSFS_PCI_PATH", tmp_path):
            devices = PcieSysfsBackend.find_plx_devices()

        assert devices == ["0000:03:00.0", "0000:05:00.0"]

    def test_read_write_with_mock_file(self, tmp_path: Path) -> None:
        """Read and write work with mock config file."""
        device_dir = tmp_path / "0000:03:00.0"
        device_dir.mkdir()

        # Create a 256-byte config file with some test data
        config_path = device_dir / "config"
        config_data = bytearray(256)
        # Write vendor/device ID at offset 0
        struct.pack_into("<I", config_data, 0, 0x873310B5)
        config_path.write_bytes(config_data)

        with patch.object(PcieSysfsBackend, "SYSFS_PCI_PATH", tmp_path):
            backend = PcieSysfsBackend("0000:03:00.0")
            try:
                # Read vendor/device
                value = backend.read32(0x00)
                assert value == 0x873310B5
                assert backend.vendor_id == 0x10B5
                assert backend.device_id == 0x8733

                # Write and read back
                backend.write32(0x10, 0xDEADBEEF)
                assert backend.read32(0x10) == 0xDEADBEEF
            finally:
                backend.close()


class TestPcieMmapBackend:
    """Tests for PcieMmapBackend."""

    def test_device_not_found(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError for missing device."""
        with patch.object(PcieMmapBackend, "SYSFS_PCI_PATH", tmp_path):
            with pytest.raises(FileNotFoundError, match="0000:99:00.0"):
                PcieMmapBackend("0000:99:00.0")

    def test_offset_exceeds_mapped_size(self, tmp_path: Path) -> None:
        """Reading beyond mapped size raises ValueError."""
        device_dir = tmp_path / "0000:03:00.0"
        device_dir.mkdir()

        # Create resource0 file
        resource_path = device_dir / "resource0"
        resource_path.write_bytes(bytes(0x1000))

        # Create resource info
        resource_info = device_dir / "resource"
        resource_info.write_text("0x00000000 0x00000fff 0x00000000\n")

        with patch.object(PcieMmapBackend, "SYSFS_PCI_PATH", tmp_path):
            backend = PcieMmapBackend("0000:03:00.0", size=0x100)
            try:
                with pytest.raises(ValueError, match="exceeds mapped size"):
                    backend.read32(0x100)
            finally:
                backend.close()
