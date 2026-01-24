"""Load device definitions from YAML files."""

from pathlib import Path
from typing import Any

import yaml

from plxtools.devices.base import (
    DeviceDefinition,
    DeviceInfo,
    EepromConfig,
    Register,
    RegisterField,
)

# Default path for device definitions (relative to package)
DEVICES_PATH = Path(__file__).parent.parent.parent.parent / "devices"


def _parse_field(name: str, data: dict[str, Any]) -> RegisterField:
    """Parse a register field definition."""
    bit = data.get("bit")
    bits = data.get("bits")
    if bits is not None:
        bits = tuple(bits)  # Convert list to tuple

    return RegisterField(
        name=name,
        description=data.get("description", ""),
        bit=bit,
        bits=bits,
    )


def _parse_register(name: str, data: dict[str, Any]) -> Register:
    """Parse a register definition."""
    fields_data = data.get("fields", {})
    fields = {fname: _parse_field(fname, fdata) for fname, fdata in fields_data.items()}

    return Register(
        name=name,
        offset=data["offset"],
        size=data.get("size", 4),
        access=data.get("access", "ro"),
        description=data.get("description", ""),
        fields=fields,
        per_port=data.get("per_port", False),
        port_stride=data.get("port_stride", 0),
    )


def _parse_device_info(data: dict[str, Any]) -> DeviceInfo:
    """Parse device information section."""
    return DeviceInfo(
        vendor_id=data["vendor_id"],
        device_id=data["device_id"],
        name=data["name"],
        description=data.get("description", ""),
        ports=data.get("ports", 0),
        lanes=data.get("lanes", 0),
        pcie_gen=data.get("pcie_gen", 3),
    )


def _parse_eeprom_config(data: dict[str, Any]) -> EepromConfig:
    """Parse EEPROM configuration section."""
    return EepromConfig(
        ctrl_offset=data["ctrl_offset"],
        data_offset=data["data_offset"],
        read_cmd=data["read_cmd"],
        addr_mask=data["addr_mask"],
        signature=data["signature"],
        max_size=data.get("max_size", 8192),
    )


def load_device_definition(path: Path) -> DeviceDefinition:
    """Load a device definition from a YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        DeviceDefinition object.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        yaml.YAMLError: If the file is not valid YAML.
        KeyError: If required fields are missing.
    """
    with path.open() as f:
        data = yaml.safe_load(f)

    device_info = _parse_device_info(data["device"])

    registers_data = data.get("registers", {})
    registers = {rname: _parse_register(rname, rdata) for rname, rdata in registers_data.items()}

    eeprom_config = _parse_eeprom_config(data["eeprom"])

    return DeviceDefinition(
        info=device_info,
        registers=registers,
        eeprom=eeprom_config,
    )


def load_device_by_id(vendor_id: int, device_id: int) -> DeviceDefinition | None:
    """Load a device definition by vendor and device ID.

    Searches the devices directory for a matching definition.

    Args:
        vendor_id: PCI vendor ID.
        device_id: PCI device ID.

    Returns:
        DeviceDefinition if found, None otherwise.
    """
    if not DEVICES_PATH.exists():
        return None

    for yaml_file in DEVICES_PATH.glob("*.yaml"):
        try:
            definition = load_device_definition(yaml_file)
            if (
                definition.info.vendor_id == vendor_id
                and definition.info.device_id == device_id
            ):
                return definition
        except (yaml.YAMLError, KeyError, OSError):
            continue

    return None


def load_device_by_name(name: str) -> DeviceDefinition | None:
    """Load a device definition by device name.

    Args:
        name: Device name (e.g., "PEX8733").

    Returns:
        DeviceDefinition if found, None otherwise.
    """
    # Try direct file lookup first
    yaml_file = DEVICES_PATH / f"{name.lower()}.yaml"
    if yaml_file.exists():
        try:
            return load_device_definition(yaml_file)
        except (yaml.YAMLError, KeyError):
            pass

    # Fall back to searching all files
    if not DEVICES_PATH.exists():
        return None

    for yaml_file in DEVICES_PATH.glob("*.yaml"):
        try:
            definition = load_device_definition(yaml_file)
            if definition.info.name.upper() == name.upper():
                return definition
        except (yaml.YAMLError, KeyError, OSError):
            continue

    return None


def list_available_devices() -> list[str]:
    """List all available device definitions.

    Returns:
        List of device names.
    """
    devices: list[str] = []

    if not DEVICES_PATH.exists():
        return devices

    for yaml_file in DEVICES_PATH.glob("*.yaml"):
        try:
            definition = load_device_definition(yaml_file)
            devices.append(definition.info.name)
        except (yaml.YAMLError, KeyError, OSError):
            continue

    return sorted(devices)
