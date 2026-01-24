"""PCIe mmap backend for BAR0 register access."""

import mmap
import struct
from pathlib import Path
from typing import BinaryIO

from plxtools.backends.base import BaseBackend
from plxtools.backends.pcie_sysfs import validate_bdf


class PcieMmapBackend(BaseBackend):
    """Access PLX switch registers via memory-mapped BAR0.

    Maps the device's BAR0 into process memory for direct register access.
    This is required for accessing extended registers like the EEPROM
    controller (0x260/0x264) which are not in PCIe config space.

    Uses /sys/bus/pci/devices/<bdf>/resource0 for the mapping.
    """

    SYSFS_PCI_PATH = Path("/sys/bus/pci/devices")

    def __init__(self, bdf: str, size: int = 0x1000) -> None:
        """Initialize mmap backend for a specific device.

        Args:
            bdf: PCI Bus:Device.Function address (e.g., "0000:03:00.0")
            size: Size of the region to map (default 4KB, enough for EEPROM regs)

        Raises:
            ValueError: If BDF format is invalid.
            FileNotFoundError: If the device doesn't exist.
        """
        validate_bdf(bdf)
        self.bdf = bdf
        self._size = size
        self._resource_path = self.SYSFS_PCI_PATH / bdf / "resource0"
        self._file: BinaryIO | None = None
        self._mmap: mmap.mmap | None = None

        if not self._resource_path.exists():
            raise FileNotFoundError(f"BAR0 resource not found: {bdf}")

        # Check resource properties
        resource_info = self._read_resource_info(bdf)
        if resource_info:
            # Verify BAR0 is memory-mapped (not I/O)
            if not resource_info.get("is_memory", True):
                raise ValueError(f"BAR0 is I/O space, not memory: {bdf}")
            # Validate requested size against actual BAR0 size
            actual_size = resource_info.get("size", 0)
            if actual_size > 0 and size > actual_size:
                raise ValueError(
                    f"Requested map size {size:#x} exceeds BAR0 size {actual_size:#x}"
                )

    def _read_resource_info(self, bdf: str) -> dict[str, int | bool] | None:
        """Read BAR0 resource information from sysfs."""
        resource_file = self.SYSFS_PCI_PATH / bdf / "resource"
        if not resource_file.exists():
            return None

        try:
            lines = resource_file.read_text().strip().split("\n")
            if lines:
                # First line is BAR0: start end flags
                parts = lines[0].split()
                if len(parts) >= 3:
                    start = int(parts[0], 16)
                    end = int(parts[1], 16)
                    flags = int(parts[2], 16)
                    return {
                        "start": start,
                        "end": end,
                        "size": end - start + 1 if end > start else 0,
                        "flags": flags,
                        "is_memory": (flags & 0x1) == 0,  # Bit 0: 0=memory, 1=I/O
                    }
        except (ValueError, OSError):
            pass
        return None

    def _ensure_mapped(self) -> mmap.mmap:
        """Ensure BAR0 is memory-mapped, mapping if necessary."""
        if self._mmap is None or self._mmap.closed:
            self._file = self._resource_path.open("r+b", buffering=0)
            self._mmap = mmap.mmap(
                self._file.fileno(),
                self._size,
                mmap.MAP_SHARED,
                mmap.PROT_READ | mmap.PROT_WRITE,
            )
        return self._mmap

    def read32(self, offset: int) -> int:
        """Read a 32-bit register from BAR0."""
        self._validate_offset(offset)
        if offset + 4 > self._size:
            raise ValueError(f"Offset {offset:#x} exceeds mapped size {self._size:#x}")

        m = self._ensure_mapped()
        data = m[offset : offset + 4]
        result: int = struct.unpack("<I", data)[0]
        return result

    def write32(self, offset: int, value: int) -> None:
        """Write a 32-bit value to BAR0."""
        self._validate_offset(offset)
        self._validate_value(value)
        if offset + 4 > self._size:
            raise ValueError(f"Offset {offset:#x} exceeds mapped size {self._size:#x}")

        m = self._ensure_mapped()
        data = struct.pack("<I", value)
        m[offset : offset + 4] = data

    def close(self) -> None:
        """Unmap BAR0 and close the resource file."""
        if self._mmap is not None and not self._mmap.closed:
            self._mmap.close()
            self._mmap = None
        if self._file is not None and not self._file.closed:
            self._file.close()
            self._file = None

    @property
    def mapped_size(self) -> int:
        """Return the size of the mapped region."""
        return self._size
