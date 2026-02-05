"""PCIe switch IC database.

Provides lookup functions for PLX/Broadcom PCIe switch ICs by vendor/device ID
or part number. The database is lazy-initialized on first access.

Example usage:
    >>> from plxtools.switchdb import lookup_ic, lookup_vendor
    >>> ic = lookup_ic(0x10B5, 0x8733)
    >>> ic.part_number
    'PEX8733'
    >>> ic.format_specs()
    '[Gen3 32L 18P]'
    >>> vendor = lookup_vendor(0x10B5)
    >>> vendor.name
    'PLX Technology'
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Re-export models for convenience
from plxtools.switchdb.models import PCIeGen, SwitchIC, Vendor

if TYPE_CHECKING:
    from plxtools.switchdb._registry import SwitchDatabase

__all__ = [
    # Models
    "PCIeGen",
    "SwitchIC",
    "Vendor",
    # Lookup functions
    "lookup_ic",
    "lookup_vendor",
    "lookup_by_part",
    "is_known_switch",
    "is_known_vendor",
    "get_db",
]

# Lazy-initialized singleton database
_db: SwitchDatabase | None = None


def _build_database() -> SwitchDatabase:
    """Build the switch database from vendor and device data.

    This is called once on first access to any lookup function.
    """
    from plxtools.switchdb._broadcom_devices import BROADCOM_DEVICES
    from plxtools.switchdb._plx_devices import PLX_DEVICES
    from plxtools.switchdb._registry import SwitchDatabase
    from plxtools.switchdb._vendors import VENDORS

    return SwitchDatabase(
        vendors=VENDORS,
        switches=PLX_DEVICES + BROADCOM_DEVICES,
    )


def get_db() -> SwitchDatabase:
    """Get the switch database singleton.

    The database is lazy-initialized on first call.

    Returns:
        The SwitchDatabase instance containing all known PCIe switch ICs.
    """
    global _db
    if _db is None:
        _db = _build_database()
    return _db


def lookup_ic(vendor_id: int, device_id: int) -> SwitchIC | None:
    """Look up a switch IC by vendor and device ID.

    Args:
        vendor_id: PCI vendor ID (e.g., 0x10B5 for PLX).
        device_id: PCI device ID (e.g., 0x8733).

    Returns:
        SwitchIC object or None if not found in database.

    Example:
        >>> ic = lookup_ic(0x10B5, 0x8733)
        >>> ic.part_number
        'PEX8733'
    """
    return get_db().lookup_ic(vendor_id, device_id)


def lookup_vendor(vendor_id: int) -> Vendor | None:
    """Look up a vendor by ID.

    Args:
        vendor_id: PCI vendor ID (e.g., 0x10B5 for PLX).

    Returns:
        Vendor object or None if not found in database.

    Example:
        >>> vendor = lookup_vendor(0x10B5)
        >>> vendor.name
        'PLX Technology'
    """
    return get_db().lookup_vendor(vendor_id)


def lookup_by_part(part_number: str) -> SwitchIC | None:
    """Look up a switch IC by part number (case-insensitive).

    Args:
        part_number: Part number like "PEX8733" or "pex8733".

    Returns:
        SwitchIC object or None if not found in database.

    Example:
        >>> ic = lookup_by_part("pex8733")
        >>> ic.device_id
        0x8733
    """
    return get_db().lookup_by_part(part_number)


def is_known_switch(vendor_id: int, device_id: int) -> bool:
    """Check if a vendor/device ID combination is a known switch.

    This is useful for filtering discovered PCI devices to only those
    that are known PCIe switches.

    Args:
        vendor_id: PCI vendor ID.
        device_id: PCI device ID.

    Returns:
        True if this is a known PCIe switch IC.

    Example:
        >>> is_known_switch(0x10B5, 0x8733)
        True
        >>> is_known_switch(0x10B5, 0xFFFF)
        False
    """
    return get_db().is_known_switch(vendor_id, device_id)


def is_known_vendor(vendor_id: int) -> bool:
    """Check if a vendor ID is in the database.

    Args:
        vendor_id: PCI vendor ID.

    Returns:
        True if this is a known PCIe switch vendor.

    Example:
        >>> is_known_vendor(0x10B5)
        True
    """
    return get_db().is_known_vendor(vendor_id)
