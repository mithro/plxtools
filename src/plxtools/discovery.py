"""Auto-discovery of PLX switches in the system."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PlxDevice:
    """Information about a discovered PLX switch."""

    bdf: str
    vendor_id: int
    device_id: int
    subsys_vendor: int
    subsys_device: int
    revision: int
    class_code: int

    @property
    def vendor_name(self) -> str:
        """Human-readable vendor name."""
        if self.vendor_id == 0x10B5:
            return "PLX/Broadcom"
        return f"Unknown ({self.vendor_id:#06x})"

    @property
    def device_name(self) -> str:
        """Human-readable device name based on device ID."""
        names = {
            0x8733: "PEX8733",
            0x8696: "PEX8696",
            0x8748: "PEX8748",
            0x8749: "PEX8749",
            0x8764: "PEX8764",
            0x8780: "PEX8780",
            0x8796: "PEX8796",
            0x8747: "PEX8747",
            0x8732: "PEX8732",
            0x8724: "PEX8724",
            0x8716: "PEX8716",
            0x8708: "PEX8708",
            0x8648: "PEX8648",
            0x8632: "PEX8632",
            0x8624: "PEX8624",
            0x8616: "PEX8616",
            0x8608: "PEX8608",
            0x8604: "PEX8604",
            0x8532: "PEX8532",
            0x8524: "PEX8524",
            0x8518: "PEX8518",
            0x8517: "PEX8517",
            0x8516: "PEX8516",
            0x8512: "PEX8512",
            0x8508: "PEX8508",
        }
        return names.get(self.device_id, f"Unknown ({self.device_id:#06x})")

    @property
    def is_switch(self) -> bool:
        """Check if this is a PCIe switch (class code 0x0604xx)."""
        return (self.class_code >> 8) == 0x0604


SYSFS_PCI_PATH = Path("/sys/bus/pci/devices")
PLX_VENDOR_ID = 0x10B5


def _read_sysfs_hex(path: Path) -> int | None:
    """Read a hex value from a sysfs file."""
    try:
        return int(path.read_text().strip(), 16)
    except (ValueError, OSError):
        return None


def discover_plx_devices() -> list[PlxDevice]:
    """Discover all PLX/Broadcom PCIe devices in the system.

    Scans /sys/bus/pci/devices for devices with vendor ID 0x10B5.

    Returns:
        List of PlxDevice objects for each discovered device.
    """
    devices: list[PlxDevice] = []

    if not SYSFS_PCI_PATH.exists():
        return devices

    for device_dir in SYSFS_PCI_PATH.iterdir():
        vendor_id = _read_sysfs_hex(device_dir / "vendor")
        if vendor_id != PLX_VENDOR_ID:
            continue

        device_id = _read_sysfs_hex(device_dir / "device")
        subsys_vendor = _read_sysfs_hex(device_dir / "subsystem_vendor")
        subsys_device = _read_sysfs_hex(device_dir / "subsystem_device")
        revision = _read_sysfs_hex(device_dir / "revision")
        class_code = _read_sysfs_hex(device_dir / "class")

        if device_id is None:
            continue

        devices.append(
            PlxDevice(
                bdf=device_dir.name,
                vendor_id=vendor_id,
                device_id=device_id,
                subsys_vendor=subsys_vendor or 0,
                subsys_device=subsys_device or 0,
                revision=revision or 0,
                class_code=class_code or 0,
            )
        )

    return sorted(devices, key=lambda d: d.bdf)


def discover_plx_switches() -> list[PlxDevice]:
    """Discover only PLX PCIe switches (not endpoints).

    Returns:
        List of PlxDevice objects for PCIe switches only.
    """
    return [d for d in discover_plx_devices() if d.is_switch]
