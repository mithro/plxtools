"""Switch database registry with indexed lookups."""

from __future__ import annotations

from collections.abc import Iterator

from plxtools.switchdb.models import SwitchIC, Vendor


class SwitchDatabase:
    """Database of PCIe switch ICs with efficient lookup methods.

    The database is populated at construction time and provides O(1) lookups
    by vendor/device ID and O(n) lookup by part number.
    """

    def __init__(
        self,
        vendors: list[Vendor],
        switches: list[SwitchIC],
    ) -> None:
        """Initialize database with vendor and switch data.

        Args:
            vendors: List of vendor definitions.
            switches: List of switch IC definitions.
        """
        # Index vendors by ID
        self._vendors_by_id: dict[int, Vendor] = {v.vendor_id: v for v in vendors}

        # Index switches by (vendor_id, device_id) tuple
        self._switches_by_id: dict[tuple[int, int], SwitchIC] = {
            (s.vendor_id, s.device_id): s for s in switches
        }

        # Index switches by uppercase part number for case-insensitive lookup
        self._switches_by_part: dict[str, SwitchIC] = {
            s.part_number.upper(): s for s in switches
        }

        # Keep original lists for iteration
        self._vendors = list(vendors)
        self._switches = list(switches)

    def lookup_vendor(self, vendor_id: int) -> Vendor | None:
        """Look up vendor by ID.

        Args:
            vendor_id: PCI vendor ID (e.g., 0x10B5).

        Returns:
            Vendor object or None if not found.
        """
        return self._vendors_by_id.get(vendor_id)

    def lookup_ic(self, vendor_id: int, device_id: int) -> SwitchIC | None:
        """Look up switch IC by vendor and device ID.

        Args:
            vendor_id: PCI vendor ID (e.g., 0x10B5).
            device_id: PCI device ID (e.g., 0x8733).

        Returns:
            SwitchIC object or None if not found.
        """
        return self._switches_by_id.get((vendor_id, device_id))

    def lookup_by_part(self, part_number: str) -> SwitchIC | None:
        """Look up switch IC by part number (case-insensitive).

        Args:
            part_number: Part number like "PEX8733" or "pex8733".

        Returns:
            SwitchIC object or None if not found.
        """
        return self._switches_by_part.get(part_number.upper())

    def is_known_switch(self, vendor_id: int, device_id: int) -> bool:
        """Check if a vendor/device ID combination is a known switch.

        Args:
            vendor_id: PCI vendor ID.
            device_id: PCI device ID.

        Returns:
            True if this is a known PCIe switch IC.
        """
        return (vendor_id, device_id) in self._switches_by_id

    def is_known_vendor(self, vendor_id: int) -> bool:
        """Check if a vendor ID is in the database.

        Args:
            vendor_id: PCI vendor ID.

        Returns:
            True if this is a known PCIe switch vendor.
        """
        return vendor_id in self._vendors_by_id

    @property
    def vendors(self) -> list[Vendor]:
        """Return all vendors in the database."""
        return list(self._vendors)

    @property
    def switches(self) -> list[SwitchIC]:
        """Return all switch ICs in the database."""
        return list(self._switches)

    def iter_by_vendor(self, vendor_id: int) -> Iterator[SwitchIC]:
        """Iterate over all switches from a specific vendor.

        Args:
            vendor_id: PCI vendor ID.

        Yields:
            SwitchIC objects for that vendor.
        """
        for switch in self._switches:
            if switch.vendor_id == vendor_id:
                yield switch

    def iter_by_generation(self, gen: int) -> Iterator[SwitchIC]:
        """Iterate over all switches of a specific PCIe generation.

        Args:
            gen: PCIe generation number (1-5).

        Yields:
            SwitchIC objects of that generation.
        """
        from plxtools.switchdb.models import PCIeGen

        target_gen = PCIeGen(gen)
        for switch in self._switches:
            if switch.pcie_gen == target_gen:
                yield switch

    def __len__(self) -> int:
        """Return total number of switch ICs in database."""
        return len(self._switches)
