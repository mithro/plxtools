"""Tests for the switchdb package."""

import pytest

from plxtools.switchdb import (
    PCIeGen,
    SwitchIC,
    Vendor,
    get_db,
    is_known_switch,
    is_known_vendor,
    lookup_by_part,
    lookup_ic,
    lookup_vendor,
)
from plxtools.switchdb._vendors import BROADCOM_LSI_VENDOR_ID, PLX_VENDOR_ID


class TestModels:
    """Tests for data model classes."""

    def test_pcie_gen_str(self) -> None:
        """Test PCIeGen string representation."""
        assert str(PCIeGen.GEN1) == "Gen1"
        assert str(PCIeGen.GEN3) == "Gen3"
        assert str(PCIeGen.GEN5) == "Gen5"

    def test_vendor_matches_name(self) -> None:
        """Test vendor name matching."""
        vendor = Vendor(
            vendor_id=0x10B5,
            name="PLX Technology",
            aliases=("PLX", "Broadcom/PLX"),
        )
        assert vendor.matches_name("PLX")
        assert vendor.matches_name("plx")  # Case-insensitive
        assert vendor.matches_name("Technology")
        assert vendor.matches_name("broadcom")
        assert not vendor.matches_name("Intel")

    def test_switch_ic_pci_id_str(self) -> None:
        """Test SwitchIC PCI ID string formatting."""
        ic = SwitchIC(
            vendor_id=0x10B5,
            device_id=0x8733,
            part_number="PEX8733",
            description="Test switch",
        )
        assert ic.pci_id_str == "10B5:8733"

    def test_switch_ic_format_specs_full(self) -> None:
        """Test format_specs with all fields populated."""
        ic = SwitchIC(
            vendor_id=0x10B5,
            device_id=0x8733,
            part_number="PEX8733",
            description="Test switch",
            pcie_gen=PCIeGen.GEN3,
            total_lanes=32,
            max_ports=18,
        )
        assert ic.format_specs() == "[Gen3 32L 18P]"

    def test_switch_ic_format_specs_partial(self) -> None:
        """Test format_specs with only some fields."""
        ic = SwitchIC(
            vendor_id=0x10B5,
            device_id=0x8733,
            part_number="PEX8733",
            description="Test switch",
            pcie_gen=PCIeGen.GEN3,
        )
        assert ic.format_specs() == "[Gen3]"

    def test_switch_ic_format_specs_empty(self) -> None:
        """Test format_specs with no spec fields."""
        ic = SwitchIC(
            vendor_id=0x10B5,
            device_id=0x8733,
            part_number="PEX8733",
            description="Test switch",
        )
        assert ic.format_specs() == ""


class TestLookupFunctions:
    """Tests for top-level lookup functions."""

    def test_lookup_vendor_plx(self) -> None:
        """Test looking up PLX vendor."""
        vendor = lookup_vendor(PLX_VENDOR_ID)
        assert vendor is not None
        assert vendor.vendor_id == PLX_VENDOR_ID
        assert "PLX" in vendor.name

    def test_lookup_vendor_broadcom(self) -> None:
        """Test looking up Broadcom/LSI vendor."""
        vendor = lookup_vendor(BROADCOM_LSI_VENDOR_ID)
        assert vendor is not None
        assert vendor.vendor_id == BROADCOM_LSI_VENDOR_ID

    def test_lookup_vendor_unknown(self) -> None:
        """Test looking up unknown vendor."""
        vendor = lookup_vendor(0xFFFF)
        assert vendor is None

    def test_lookup_ic_pex8733(self) -> None:
        """Test looking up PEX8733."""
        ic = lookup_ic(PLX_VENDOR_ID, 0x8733)
        assert ic is not None
        assert ic.part_number == "PEX8733"
        assert ic.pcie_gen == PCIeGen.GEN3
        assert ic.total_lanes == 32
        assert ic.max_ports == 18

    def test_lookup_ic_pex8749(self) -> None:
        """Test looking up PEX8749."""
        ic = lookup_ic(PLX_VENDOR_ID, 0x8749)
        assert ic is not None
        assert ic.part_number == "PEX8749"
        assert ic.has_dma is True
        assert ic.has_nt is True

    def test_lookup_ic_broadcom_gen4(self) -> None:
        """Test looking up Broadcom Gen4 switch."""
        ic = lookup_ic(BROADCOM_LSI_VENDOR_ID, 0xC010)
        assert ic is not None
        assert ic.pcie_gen == PCIeGen.GEN4
        assert "PEX880" in ic.part_number

    def test_lookup_ic_unknown(self) -> None:
        """Test looking up unknown device."""
        ic = lookup_ic(PLX_VENDOR_ID, 0xFFFF)
        assert ic is None

    def test_lookup_by_part_case_insensitive(self) -> None:
        """Test part number lookup is case-insensitive."""
        ic1 = lookup_by_part("PEX8733")
        ic2 = lookup_by_part("pex8733")
        ic3 = lookup_by_part("Pex8733")
        assert ic1 is not None
        assert ic1 == ic2 == ic3

    def test_lookup_by_part_unknown(self) -> None:
        """Test looking up unknown part number."""
        ic = lookup_by_part("UNKNOWN123")
        assert ic is None

    def test_is_known_switch(self) -> None:
        """Test is_known_switch function."""
        assert is_known_switch(PLX_VENDOR_ID, 0x8733) is True
        assert is_known_switch(PLX_VENDOR_ID, 0xFFFF) is False
        assert is_known_switch(0xFFFF, 0x8733) is False

    def test_is_known_vendor(self) -> None:
        """Test is_known_vendor function."""
        assert is_known_vendor(PLX_VENDOR_ID) is True
        assert is_known_vendor(BROADCOM_LSI_VENDOR_ID) is True
        assert is_known_vendor(0xFFFF) is False


class TestDatabase:
    """Tests for the SwitchDatabase class."""

    def test_database_singleton(self) -> None:
        """Test that get_db returns the same instance."""
        db1 = get_db()
        db2 = get_db()
        assert db1 is db2

    def test_database_has_devices(self) -> None:
        """Test database contains devices."""
        db = get_db()
        # Should have at least 50 PLX devices
        assert len(db) >= 50

    def test_database_has_vendors(self) -> None:
        """Test database contains vendors."""
        db = get_db()
        assert len(db.vendors) >= 2

    def test_iter_by_vendor(self) -> None:
        """Test iterating devices by vendor."""
        db = get_db()
        plx_devices = list(db.iter_by_vendor(PLX_VENDOR_ID))
        # Should have many PLX devices
        assert len(plx_devices) >= 40
        # All should have PLX vendor ID
        for ic in plx_devices:
            assert ic.vendor_id == PLX_VENDOR_ID

    def test_iter_by_generation(self) -> None:
        """Test iterating devices by generation."""
        db = get_db()
        gen3_devices = list(db.iter_by_generation(3))
        # Should have multiple Gen3 devices
        assert len(gen3_devices) >= 10
        # All should be Gen3
        for ic in gen3_devices:
            assert ic.pcie_gen == PCIeGen.GEN3


class TestDataIntegrity:
    """Tests for data integrity and consistency."""

    def test_all_ics_have_valid_vendors(self) -> None:
        """Verify all ICs reference known vendors."""
        db = get_db()
        for ic in db.switches:
            vendor = db.lookup_vendor(ic.vendor_id)
            assert vendor is not None, f"{ic.part_number} has unknown vendor {ic.vendor_id:#06x}"

    def test_no_duplicate_device_ids(self) -> None:
        """Verify no duplicate vendor/device ID combinations."""
        db = get_db()
        seen: set[tuple[int, int]] = set()
        for ic in db.switches:
            key = (ic.vendor_id, ic.device_id)
            assert key not in seen, f"Duplicate device ID: {ic.pci_id_str} ({ic.part_number})"
            seen.add(key)

    def test_no_duplicate_part_numbers(self) -> None:
        """Verify no duplicate part numbers (case-insensitive)."""
        db = get_db()
        seen: set[str] = set()
        for ic in db.switches:
            part_upper = ic.part_number.upper()
            assert part_upper not in seen, f"Duplicate part number: {ic.part_number}"
            seen.add(part_upper)

    def test_all_ics_have_required_fields(self) -> None:
        """Verify all ICs have required fields populated."""
        db = get_db()
        for ic in db.switches:
            assert ic.vendor_id > 0
            assert ic.device_id > 0
            assert ic.part_number
            assert ic.description

    def test_plx_device_families(self) -> None:
        """Verify PLX device families are set correctly."""
        db = get_db()
        family_counts: dict[str | None, int] = {}
        for ic in db.iter_by_vendor(PLX_VENDOR_ID):
            family_counts[ic.family] = family_counts.get(ic.family, 0) + 1

        # Should have multiple families
        assert len(family_counts) >= 4  # PEX8500, PEX8600, PEX8700, PEX9700, etc.

    def test_gen3_switches_have_dma_info(self) -> None:
        """Gen3+ switches should have DMA info specified."""
        db = get_db()
        for ic in db.switches:
            if ic.pcie_gen and ic.pcie_gen.value >= 3:
                # Most Gen3+ switches should have DMA field set
                # (some auxiliary/management devices may not)
                if ic.family not in ("Auxiliary", "Management"):
                    # Skip management endpoints (part numbers ending in -mgmt)
                    if "-mgmt" in ic.part_number.lower():
                        continue
                    assert ic.has_dma is not None, (
                        f"{ic.part_number} missing has_dma field"
                    )
