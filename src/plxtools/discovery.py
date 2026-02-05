"""Auto-discovery of PLX switches in the system."""

from __future__ import annotations

import re
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
        vendor_names = {
            0x10B5: "PLX/Broadcom",
            0x1000: "Broadcom/LSI",
        }
        return vendor_names.get(self.vendor_id, f"Unknown ({self.vendor_id:#06x})")

    @property
    def device_name(self) -> str:
        """Human-readable device name based on vendor and device ID."""
        # PLX vendor 0x10B5 device names
        plx_names = {
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
            0x87D0: "PEX8749-DMA",
        }
        # Broadcom/LSI vendor 0x1000 device names (PEX880xx Gen4 family)
        broadcom_names = {
            0xC010: "PEX880xx",
            0xC012: "PEX880xx-mgmt",
        }
        if self.vendor_id == 0x10B5:
            return plx_names.get(self.device_id, f"Unknown ({self.device_id:#06x})")
        if self.vendor_id == 0x1000:
            return broadcom_names.get(self.device_id, f"Unknown ({self.device_id:#06x})")
        return f"Unknown ({self.device_id:#06x})"

    @property
    def is_switch(self) -> bool:
        """Check if this is a PCIe switch (class code 0x0604xx)."""
        return (self.class_code >> 8) == 0x0604


SYSFS_PCI_PATH = Path("/sys/bus/pci/devices")
# PLX/Broadcom vendor IDs used across different switch generations
PLX_VENDOR_ID = 0x10B5  # PLX Technology (Gen1-Gen3 switches)
BROADCOM_LSI_VENDOR_ID = 0x1000  # Broadcom/LSI (Gen4+ PEX880xx)
PLX_VENDOR_IDS = {PLX_VENDOR_ID, BROADCOM_LSI_VENDOR_ID}


def _read_sysfs_hex(path: Path) -> int | None:
    """Read a hex value from a sysfs file."""
    try:
        return int(path.read_text().strip(), 16)
    except (ValueError, OSError):
        return None


def discover_plx_devices() -> list[PlxDevice]:
    """Discover all PLX/Broadcom PCIe devices in the system.

    Scans /sys/bus/pci/devices for devices with vendor ID 0x10B5 (PLX)
    or 0x1000 (Broadcom/LSI, used by PEX880xx Gen4 switches).

    Returns:
        List of PlxDevice objects for each discovered device.
    """
    devices: list[PlxDevice] = []

    if not SYSFS_PCI_PATH.exists():
        return devices

    # Known PEX880xx device IDs (vendor 0x1000)
    pex880xx_device_ids = {0xC010, 0xC012}

    for device_dir in SYSFS_PCI_PATH.iterdir():
        vendor_id = _read_sysfs_hex(device_dir / "vendor")
        if vendor_id not in PLX_VENDOR_IDS:
            continue

        device_id = _read_sysfs_hex(device_dir / "device")
        subsys_vendor = _read_sysfs_hex(device_dir / "subsystem_vendor")
        subsys_device = _read_sysfs_hex(device_dir / "subsystem_device")
        revision = _read_sysfs_hex(device_dir / "revision")
        class_code = _read_sysfs_hex(device_dir / "class")

        if device_id is None:
            continue

        # For vendor 0x1000 (Broadcom/LSI), only include known PEX device IDs
        # to avoid matching unrelated Broadcom devices (SAS HBAs, NICs, etc.)
        if vendor_id == BROADCOM_LSI_VENDOR_ID and device_id not in pex880xx_device_ids:
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


# --- Serial device discovery ---

# Known USB vendor/product IDs for PLX serial management interfaces
# Hitachi is the USB vendor for Serial Cables ATLAS HOST CARD
SERIAL_USB_VENDOR_HITACHI = 0x045B
SERIAL_USB_PRODUCT_ATLAS = 0x5300


@dataclass
class SerialPlxDevice:
    """Information about a PLX switch accessible via serial interface."""

    device_path: str
    usb_vendor_id: int
    usb_product_id: int
    serial_number: str | None
    model: str | None

    @property
    def is_atlas(self) -> bool:
        """Check if this is a Serial Cables ATLAS HOST CARD."""
        return (
            self.usb_vendor_id == SERIAL_USB_VENDOR_HITACHI
            and self.usb_product_id == SERIAL_USB_PRODUCT_ATLAS
        )


def _read_sysfs_text(path: Path) -> str | None:
    """Read text from a sysfs file."""
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _get_usb_ids_for_tty(device_path: str) -> tuple[int, int] | None:
    """Get USB vendor/product IDs for a tty device.

    Follows the sysfs symlinks to find the parent USB device.

    Args:
        device_path: Path like "/dev/ttyACM0"

    Returns:
        Tuple of (vendor_id, product_id) or None if not found.
    """
    # Get the device name (e.g., "ttyACM0")
    device_name = Path(device_path).name

    # Find the sysfs path for this device
    sysfs_tty = Path(f"/sys/class/tty/{device_name}")
    if not sysfs_tty.exists():
        return None

    # Follow "device" symlink to get to the USB interface
    device_link = sysfs_tty / "device"
    if not device_link.exists():
        return None

    # Walk up the directory tree looking for idVendor/idProduct
    current = device_link.resolve()
    while current != Path("/"):
        vendor_file = current / "idVendor"
        product_file = current / "idProduct"

        if vendor_file.exists() and product_file.exists():
            vendor_str = _read_sysfs_text(vendor_file)
            product_str = _read_sysfs_text(product_file)

            if vendor_str and product_str:
                try:
                    return (int(vendor_str, 16), int(product_str, 16))
                except ValueError:
                    return None

        current = current.parent

    return None


def _get_usb_serial_number(device_path: str) -> str | None:
    """Get USB serial number for a tty device."""
    device_name = Path(device_path).name
    sysfs_tty = Path(f"/sys/class/tty/{device_name}")

    if not sysfs_tty.exists():
        return None

    device_link = sysfs_tty / "device"
    if not device_link.exists():
        return None

    # Walk up looking for serial file
    current = device_link.resolve()
    while current != Path("/"):
        serial_file = current / "serial"
        if serial_file.exists():
            return _read_sysfs_text(serial_file)
        current = current.parent

    return None


def discover_serial_devices(
    *,
    probe: bool = False,
) -> list[SerialPlxDevice]:
    """Discover PLX switches accessible via USB serial interfaces.

    Scans /dev/ttyACM* for devices with known USB vendor/product IDs
    that correspond to PLX switch management interfaces.

    Args:
        probe: If True, attempt to probe each device with "ver" command
               to confirm it's a PLX switch and get model info.
               This opens the serial port and may take time.

    Returns:
        List of SerialPlxDevice objects for each discovered device.
    """
    devices: list[SerialPlxDevice] = []

    # Scan /dev/ttyACM* devices
    dev_path = Path("/dev")
    if not dev_path.exists():
        return devices

    tty_pattern = re.compile(r"^ttyACM\d+$")

    for entry in sorted(dev_path.iterdir()):
        if not tty_pattern.match(entry.name):
            continue

        device_path = str(entry)

        # Get USB IDs
        usb_ids = _get_usb_ids_for_tty(device_path)
        if usb_ids is None:
            continue

        vendor_id, product_id = usb_ids

        # Filter by known PLX management interface USB IDs
        if vendor_id != SERIAL_USB_VENDOR_HITACHI:
            continue
        if product_id != SERIAL_USB_PRODUCT_ATLAS:
            continue

        serial_number = _get_usb_serial_number(device_path)
        model: str | None = None

        # Optionally probe to get model info
        if probe:
            model = _probe_serial_device_model(device_path)

        devices.append(
            SerialPlxDevice(
                device_path=device_path,
                usb_vendor_id=vendor_id,
                usb_product_id=product_id,
                serial_number=serial_number,
                model=model,
            )
        )

    return devices


def _probe_serial_device_model(device_path: str) -> str | None:
    """Probe a serial device to get the PLX switch model.

    Args:
        device_path: Path to serial device (e.g., "/dev/ttyACM0")

    Returns:
        Model string (e.g., "PEX88096") or None if probe fails.
    """
    try:
        from plxtools.backends.serial import SerialBackend

        with SerialBackend(device_path, timeout=1.0) as backend:
            info = backend.get_version()
            return info.model or None
    except Exception:
        return None
