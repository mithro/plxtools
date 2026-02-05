"""Data models for PCIe switch IC database."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PCIeGen(Enum):
    """PCIe generation (link speed)."""

    GEN1 = 1  # 2.5 GT/s
    GEN2 = 2  # 5.0 GT/s
    GEN3 = 3  # 8.0 GT/s
    GEN4 = 4  # 16.0 GT/s
    GEN5 = 5  # 32.0 GT/s

    def __str__(self) -> str:
        return f"Gen{self.value}"


@dataclass(frozen=True)
class Vendor:
    """PCIe vendor information."""

    vendor_id: int
    name: str
    aliases: tuple[str, ...] = ()

    def matches_name(self, query: str) -> bool:
        """Check if query matches vendor name or aliases (case-insensitive)."""
        query_lower = query.lower()
        if query_lower in self.name.lower():
            return True
        return any(query_lower in alias.lower() for alias in self.aliases)


@dataclass(frozen=True)
class SwitchIC:
    """PCIe switch IC definition.

    Contains both identification info (vendor/device ID) and technical specs
    (lanes, ports, generation, etc.).
    """

    vendor_id: int
    device_id: int
    part_number: str  # e.g., "PEX8733"
    description: str

    # Technical specifications (None = unknown/not applicable)
    pcie_gen: PCIeGen | None = None
    total_lanes: int | None = None
    max_ports: int | None = None
    max_port_width: int | None = None

    # Classification
    family: str | None = None  # e.g., "PEX8700", "PEX8600"
    has_dma: bool | None = None
    has_nt: bool | None = None  # Non-transparent bridging

    # Additional metadata
    package: str | None = None  # e.g., "27x27mm FCBGA"
    product_url: str | None = None
    notes: str | None = None

    @property
    def pci_id_str(self) -> str:
        """Return PCI ID in standard format (e.g., '10B5:8733')."""
        return f"{self.vendor_id:04X}:{self.device_id:04X}"

    def format_specs(self) -> str:
        """Return a compact specs string like '[Gen3 32L 8P]'."""
        parts: list[str] = []
        if self.pcie_gen is not None:
            parts.append(str(self.pcie_gen))
        if self.total_lanes is not None:
            parts.append(f"{self.total_lanes}L")
        if self.max_ports is not None:
            parts.append(f"{self.max_ports}P")
        if not parts:
            return ""
        return f"[{' '.join(parts)}]"
