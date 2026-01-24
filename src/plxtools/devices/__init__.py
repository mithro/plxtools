"""Device definitions for PLX switches."""

from plxtools.devices.base import (
    DeviceDefinition,
    DeviceInfo,
    EepromConfig,
    Register,
    RegisterField,
)
from plxtools.devices.loader import (
    list_available_devices,
    load_device_by_id,
    load_device_by_name,
    load_device_definition,
)

__all__ = [
    "DeviceDefinition",
    "DeviceInfo",
    "EepromConfig",
    "Register",
    "RegisterField",
    "list_available_devices",
    "load_device_by_id",
    "load_device_by_name",
    "load_device_definition",
]
