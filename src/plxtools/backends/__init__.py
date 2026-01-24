"""Hardware access backends for PLX switches."""

from plxtools.backends.base import BaseBackend, RegisterAccess
from plxtools.backends.mock import MockBackend, MockEepromBackend

# PCIe backends are imported on-demand to avoid errors on systems without sysfs
# from plxtools.backends.pcie_sysfs import PcieSysfsBackend
# from plxtools.backends.pcie_mmap import PcieMmapBackend

__all__ = [
    "BaseBackend",
    "MockBackend",
    "MockEepromBackend",
    "RegisterAccess",
    # Available via explicit import:
    # "PcieSysfsBackend",
    # "PcieMmapBackend",
]
