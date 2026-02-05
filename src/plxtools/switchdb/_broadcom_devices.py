"""Broadcom/LSI (0x1000) PCIe switch IC definitions.

This vendor ID is shared with Broadcom storage controllers (MegaRAID, SAS HBAs),
so we only include device IDs known to be PCIe switches.

The PEX880xx (Gen4) and PEX890xx (Gen5) families use vendor ID 0x1000 instead
of the traditional PLX 0x10B5.
"""

from plxtools.switchdb._vendors import BROADCOM_LSI_VENDOR_ID
from plxtools.switchdb.models import PCIeGen, SwitchIC

# =============================================================================
# PEX880xx Family - Gen4 (16.0 GT/s)
# =============================================================================

PEX880XX_FAMILY: list[SwitchIC] = [
    SwitchIC(
        vendor_id=BROADCOM_LSI_VENDOR_ID,
        device_id=0xC010,
        part_number="PEX880xx",
        description="Broadcom PEX880xx Gen4 PCIe switch",
        pcie_gen=PCIeGen.GEN4,
        family="PEX880xx",
        has_dma=True,
        notes="Gen4 switch family, visible on sm-pcie-1 hardware",
    ),
    SwitchIC(
        vendor_id=BROADCOM_LSI_VENDOR_ID,
        device_id=0xC012,
        part_number="PEX880xx-mgmt",
        description="Broadcom PEX880xx Gen4 PCIe switch management endpoint",
        pcie_gen=PCIeGen.GEN4,
        family="PEX880xx",
        notes="Management endpoint for PEX880xx switches",
    ),
]

# =============================================================================
# PEX890xx Family - Gen5 (32.0 GT/s)
# =============================================================================

PEX890XX_FAMILY: list[SwitchIC] = [
    SwitchIC(
        vendor_id=BROADCOM_LSI_VENDOR_ID,
        device_id=0xC030,
        part_number="PEX890xx",
        description="Broadcom PEX890xx Gen5 PCIe switch",
        pcie_gen=PCIeGen.GEN5,
        family="PEX890xx",
        has_dma=True,
        notes="Gen5 switch family",
    ),
    SwitchIC(
        vendor_id=BROADCOM_LSI_VENDOR_ID,
        device_id=0xC034,
        part_number="PEX890xx-v2",
        description="Broadcom PEX890xx Gen5 PCIe switch variant",
        pcie_gen=PCIeGen.GEN5,
        family="PEX890xx",
        has_dma=True,
    ),
]

# =============================================================================
# Virtual/Management Endpoints
# =============================================================================

BROADCOM_MGMT_DEVICES: list[SwitchIC] = [
    SwitchIC(
        vendor_id=BROADCOM_LSI_VENDOR_ID,
        device_id=0x00B2,
        part_number="PCIe-Switch-Mgmt",
        description="PCIe Switch management endpoint",
        family="Management",
        notes="Management endpoint visible on some Broadcom switches",
    ),
    SwitchIC(
        vendor_id=BROADCOM_LSI_VENDOR_ID,
        device_id=0x02B0,
        part_number="PCIe-Switch-VEP",
        description="Virtual Endpoint on PCIe Switch",
        family="Management",
        notes="Virtual endpoint for multi-host configurations",
    ),
    SwitchIC(
        vendor_id=BROADCOM_LSI_VENDOR_ID,
        device_id=0x02B1,
        part_number="PCIe-Switch-VEP-9749",
        description="Virtual Endpoint on PCIe Switch (PEX9749)",
        family="Management",
        notes="Virtual endpoint specific to PEX9749",
    ),
]

# =============================================================================
# Combined list of all Broadcom devices
# =============================================================================

BROADCOM_DEVICES: list[SwitchIC] = (
    PEX880XX_FAMILY
    + PEX890XX_FAMILY
    + BROADCOM_MGMT_DEVICES
)
