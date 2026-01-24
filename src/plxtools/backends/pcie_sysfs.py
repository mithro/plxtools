"""PCIe sysfs backend for config space access."""

import struct
from pathlib import Path
from typing import BinaryIO

from plxtools.backends.base import BaseBackend


class PcieSysfsBackend(BaseBackend):
    """Access PLX switch registers via PCIe config space sysfs interface.

    Reads and writes to /sys/bus/pci/devices/<bdf>/config for standard
    PCIe configuration space access (first 256 bytes) and extended
    config space (up to 4096 bytes if supported).

    Note: Config space access is limited to 4KB. For extended registers
    (like EEPROM controller at 0x260), use PcieMmapBackend instead.
    """

    SYSFS_PCI_PATH = Path("/sys/bus/pci/devices")

    def __init__(self, bdf: str) -> None:
        """Initialize sysfs backend for a specific device.

        Args:
            bdf: PCI Bus:Device.Function address (e.g., "0000:03:00.0")
        """
        self.bdf = bdf
        self._config_path = self.SYSFS_PCI_PATH / bdf / "config"
        self._file: BinaryIO | None = None

        if not self._config_path.exists():
            raise FileNotFoundError(f"PCI device not found: {bdf}")

    def _ensure_open(self) -> BinaryIO:
        """Ensure config file is open, opening if necessary."""
        if self._file is None or self._file.closed:
            self._file = self._config_path.open("r+b", buffering=0)
        return self._file

    def read32(self, offset: int) -> int:
        """Read a 32-bit register from config space."""
        self._validate_offset(offset)
        f = self._ensure_open()
        f.seek(offset)
        data = f.read(4)
        if len(data) != 4:
            raise OSError(f"Short read at offset {offset:#x}: got {len(data)} bytes")
        result: int = struct.unpack("<I", data)[0]
        return result

    def write32(self, offset: int, value: int) -> None:
        """Write a 32-bit value to config space."""
        self._validate_offset(offset)
        self._validate_value(value)
        f = self._ensure_open()
        f.seek(offset)
        data = struct.pack("<I", value)
        written = f.write(data)
        if written != 4:
            raise OSError(f"Short write at offset {offset:#x}: wrote {written} bytes")

    def close(self) -> None:
        """Close the config space file."""
        if self._file is not None and not self._file.closed:
            self._file.close()
            self._file = None

    @property
    def vendor_id(self) -> int:
        """Read the PCI vendor ID (offset 0x00, lower 16 bits)."""
        return self.read32(0x00) & 0xFFFF

    @property
    def device_id(self) -> int:
        """Read the PCI device ID (offset 0x00, upper 16 bits)."""
        return (self.read32(0x00) >> 16) & 0xFFFF

    @classmethod
    def find_plx_devices(cls) -> list[str]:
        """Find all PLX/Broadcom PCIe switches in the system.

        Returns:
            List of BDF addresses for PLX switches (vendor ID 0x10b5).
        """
        plx_vendor_id = 0x10B5
        devices: list[str] = []

        if not cls.SYSFS_PCI_PATH.exists():
            return devices

        for device_dir in cls.SYSFS_PCI_PATH.iterdir():
            vendor_path = device_dir / "vendor"
            if vendor_path.exists():
                try:
                    vendor = int(vendor_path.read_text().strip(), 16)
                    if vendor == plx_vendor_id:
                        devices.append(device_dir.name)
                except (ValueError, OSError):
                    continue

        return sorted(devices)
