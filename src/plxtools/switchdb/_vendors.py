"""Vendor definitions for PCIe switch database.

This module defines the vendors that manufacture PCIe switch ICs supported
by plxtools. Currently limited to PLX Technology and Broadcom/LSI.
"""

from plxtools.switchdb.models import Vendor

# PLX Technology (0x10B5) - Gen1/Gen2/Gen3 switches
# Acquired by Avago (2014), now part of Broadcom.
PLX_VENDOR = Vendor(
    vendor_id=0x10B5,
    name="PLX Technology",
    aliases=("PLX", "Broadcom/PLX", "PLX/Broadcom"),
)

# Broadcom/LSI (0x1000) - Gen4/Gen5 switches (PEX880xx, PEX890xx)
# This vendor ID is shared with LSI Logic/Broadcom storage controllers,
# so device ID filtering is required.
BROADCOM_LSI_VENDOR = Vendor(
    vendor_id=0x1000,
    name="Broadcom/LSI",
    aliases=("Broadcom", "LSI", "LSI Logic"),
)

# All vendors supported by plxtools
VENDORS: list[Vendor] = [
    PLX_VENDOR,
    BROADCOM_LSI_VENDOR,
]

# Vendor ID constants for use in other modules
PLX_VENDOR_ID = 0x10B5
BROADCOM_LSI_VENDOR_ID = 0x1000
