"""Auto-discovery of PLX switches in the system."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plxtools.switchdb import SwitchIC


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
    def domain(self) -> int:
        """PCI domain number from BDF."""
        return int(self.bdf.split(":")[0], 16)

    @property
    def bus(self) -> int:
        """PCI bus number from BDF."""
        return int(self.bdf.split(":")[1], 16)

    @property
    def device_func(self) -> tuple[int, int]:
        """PCI device and function numbers from BDF."""
        dev_func = self.bdf.split(":")[2]
        dev, func = dev_func.split(".")
        return int(dev, 16), int(func, 16)

    @property
    def vendor_name(self) -> str:
        """Human-readable vendor name."""
        from plxtools.switchdb import lookup_vendor

        vendor = lookup_vendor(self.vendor_id)
        if vendor is not None:
            return vendor.name
        return f"Unknown ({self.vendor_id:#06x})"

    @property
    def device_name(self) -> str:
        """Human-readable device name based on vendor and device ID."""
        from plxtools.switchdb import lookup_ic

        ic = lookup_ic(self.vendor_id, self.device_id)
        if ic is not None:
            return ic.part_number
        return f"Unknown ({self.device_id:#06x})"

    @cached_property
    def switch_info(self) -> SwitchIC | None:
        """Get full switch IC information from the database.

        Returns:
            SwitchIC object with detailed specs, or None if device not in database.
        """
        from plxtools.switchdb import lookup_ic

        return lookup_ic(self.vendor_id, self.device_id)

    @property
    def is_switch(self) -> bool:
        """Check if this is a PCIe switch (class code 0x0604xx)."""
        return (self.class_code >> 8) == 0x0604

    def format_display_name(self) -> str:
        """Format device name with specs for display.

        Returns a string like "PEX8733 [Gen3 32L 18P]" if specs are available,
        or just the device name if not.
        """
        name = self.device_name
        if self.switch_info is not None:
            specs = self.switch_info.format_specs()
            if specs:
                return f"{name} {specs}"
        return name


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
    from plxtools.switchdb import is_known_switch, is_known_vendor

    devices: list[PlxDevice] = []

    if not SYSFS_PCI_PATH.exists():
        return devices

    for device_dir in SYSFS_PCI_PATH.iterdir():
        vendor_id = _read_sysfs_hex(device_dir / "vendor")
        if vendor_id is None or not is_known_vendor(vendor_id):
            continue

        device_id = _read_sysfs_hex(device_dir / "device")
        if device_id is None:
            continue

        # For non-PLX vendors (like 0x1000), only include known switch device IDs
        # to avoid matching unrelated devices (SAS HBAs, NICs, etc.)
        if vendor_id != PLX_VENDOR_ID and not is_known_switch(vendor_id, device_id):
            continue

        subsys_vendor = _read_sysfs_hex(device_dir / "subsystem_vendor")
        subsys_device = _read_sysfs_hex(device_dir / "subsystem_device")
        revision = _read_sysfs_hex(device_dir / "revision")
        class_code = _read_sysfs_hex(device_dir / "class")

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


@dataclass
class PlxSwitch:
    """A physical PCIe switch with its upstream port and port count.

    In PCIe topology, a switch has one upstream port (connecting to the host)
    and multiple downstream ports. This class represents the physical switch
    by its upstream port, along with a count of downstream ports.
    """

    upstream_port: PlxDevice
    downstream_port_count: int

    @property
    def device_name(self) -> str:
        """Human-readable device name."""
        return self.upstream_port.device_name

    @property
    def switch_info(self) -> SwitchIC | None:
        """Get full switch IC information from the database."""
        return self.upstream_port.switch_info

    def format_display_name(self) -> str:
        """Format device name with specs for display."""
        return self.upstream_port.format_display_name()


def discover_unique_switches() -> list[PlxSwitch]:
    """Discover unique physical PCIe switches (not individual ports).

    Groups switch ports by topology to identify unique physical switches.
    The upstream port of each switch is identified by finding ports that
    are alone on their bus segment (downstream ports share a bus).

    Returns:
        List of PlxSwitch objects, one per physical switch.
    """
    switches = discover_plx_switches()
    if not switches:
        return []

    # Group switches by (domain, bus) to find ports sharing the same bus
    from collections import defaultdict

    by_bus: dict[tuple[int, int], list[PlxDevice]] = defaultdict(list)
    for sw in switches:
        by_bus[(sw.domain, sw.bus)].append(sw)

    # Identify upstream ports: ports that are alone on their bus segment
    # (or with only different device types), and whose bus has downstream ports
    # pointing back to it.
    #
    # Heuristic: if a bus has only one PLX switch port, it's likely the upstream.
    # If a bus has many PLX switch ports, they're downstream ports.
    result: list[PlxSwitch] = []
    processed_buses: set[tuple[int, int]] = set()

    for (domain, bus), ports in sorted(by_bus.items()):
        if (domain, bus) in processed_buses:
            continue

        if len(ports) == 1:
            # Single port on this bus - likely an upstream port
            upstream = ports[0]

            # Look for downstream ports on a secondary bus
            # The secondary bus is typically bus+1, but we check all buses
            # to find ports of the same device type
            downstream_count = 0
            for (d2, b2), ports2 in by_bus.items():
                if d2 == domain and b2 != bus:
                    # Check if these are downstream ports of the same switch type
                    matching = [
                        p for p in ports2
                        if p.vendor_id == upstream.vendor_id
                        and p.device_id == upstream.device_id
                    ]
                    if matching and len(matching) == len(ports2):
                        # All ports on this bus are the same type - downstream ports
                        downstream_count += len(matching)
                        processed_buses.add((d2, b2))

            result.append(PlxSwitch(upstream, downstream_count))
            processed_buses.add((domain, bus))
        else:
            # Multiple ports on this bus - these are downstream ports
            # They should be associated with an upstream port we already found
            # or will find. Skip for now.
            pass

    # Handle any remaining buses with multiple ports that weren't associated
    # with an upstream port (shouldn't happen in normal topology)
    for (domain, bus), ports in sorted(by_bus.items()):
        if (domain, bus) in processed_buses:
            continue
        # Take the first port as representative
        result.append(PlxSwitch(ports[0], len(ports) - 1))
        processed_buses.add((domain, bus))

    return sorted(result, key=lambda s: s.upstream_port.bdf)


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
