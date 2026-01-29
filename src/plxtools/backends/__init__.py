"""Hardware access backends for PLX switches."""

from plxtools.backends.base import BaseBackend, RegisterAccess
from plxtools.backends.mock import MockBackend, MockEepromBackend

# PCIe backends are imported on-demand to avoid errors on systems without sysfs
# from plxtools.backends.pcie_sysfs import PcieSysfsBackend
# from plxtools.backends.pcie_mmap import PcieMmapBackend

# Serial backend is imported on-demand to avoid requiring pyserial on all systems
# from plxtools.backends.serial import SerialBackend

__all__ = [
    "BaseBackend",
    "MockBackend",
    "MockEepromBackend",
    "RegisterAccess",
    # Available via explicit import:
    # "PcieSysfsBackend",
    # "PcieMmapBackend",
    # "SerialBackend",
]
