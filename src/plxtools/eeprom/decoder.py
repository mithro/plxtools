"""EEPROM content decoder for PLX switches."""

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plxtools.devices import DeviceDefinition


@dataclass
class RegisterWrite:
    """A single register write entry from EEPROM."""

    raw_address: int  # Raw 16-bit address field from EEPROM
    register_offset: int  # Actual register offset (raw_address << 2)
    port: int  # Port number (extracted from address)
    value: int  # 32-bit value to write
    register_name: str | None = None  # Resolved register name (if known)


@dataclass
class EepromContents:
    """Decoded EEPROM contents."""

    valid: bool
    signature: int
    payload_length: int
    register_writes: list[RegisterWrite] = field(default_factory=list)
    raw_data: bytes = field(default=b"", repr=False)

    @property
    def num_writes(self) -> int:
        """Number of register write entries."""
        return len(self.register_writes)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "valid": self.valid,
            "signature": f"0x{self.signature:02X}",
            "payload_length": self.payload_length,
            "num_writes": self.num_writes,
            "register_writes": [
                {
                    "raw_address": f"0x{w.raw_address:04X}",
                    "register_offset": f"0x{w.register_offset:03X}",
                    "port": w.port,
                    "value": f"0x{w.value:08X}",
                    "register_name": w.register_name,
                }
                for w in self.register_writes
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


class EepromDecoder:
    """Decoder for PLX EEPROM contents.

    EEPROM format:
    - Byte 0: Signature (0x5A for valid EEPROM)
    - Byte 1: Reserved (0x00)
    - Bytes 2-3: Payload length (16-bit LE, num_writes * 6)
    - Bytes 4+: Register write entries (6 bytes each)

    Each register write entry:
    - Bytes 0-1: Address (16-bit LE): (reg_offset >> 2) | (port << 10)
    - Bytes 2-5: Value (32-bit LE)
    """

    SIGNATURE = 0x5A
    HEADER_SIZE = 4
    ENTRY_SIZE = 6

    def __init__(self, device_def: DeviceDefinition | None = None) -> None:
        """Initialize decoder.

        Args:
            device_def: Optional device definition for register name lookup.
        """
        self.device_def = device_def

    def decode(self, data: bytes) -> EepromContents:
        """Decode EEPROM contents from raw bytes.

        Args:
            data: Raw EEPROM data.

        Returns:
            EepromContents with decoded information.
        """
        if len(data) < self.HEADER_SIZE:
            return EepromContents(
                valid=False,
                signature=data[0] if data else 0,
                payload_length=0,
                raw_data=data,
            )

        # Parse header
        signature = data[0]
        reserved = data[1]
        payload_length = struct.unpack("<H", data[2:4])[0]

        valid = signature == self.SIGNATURE and reserved == 0x00

        if not valid:
            return EepromContents(
                valid=False,
                signature=signature,
                payload_length=payload_length,
                raw_data=data,
            )

        # Parse register writes
        register_writes: list[RegisterWrite] = []
        num_entries = payload_length // self.ENTRY_SIZE

        for i in range(num_entries):
            offset = self.HEADER_SIZE + (i * self.ENTRY_SIZE)
            if offset + self.ENTRY_SIZE > len(data):
                break

            entry_data = data[offset : offset + self.ENTRY_SIZE]
            raw_addr = struct.unpack("<H", entry_data[0:2])[0]
            value = struct.unpack("<I", entry_data[2:6])[0]

            # Decode address: lower 10 bits are register offset >> 2
            # Upper 6 bits are port number
            reg_offset = (raw_addr & 0x3FF) << 2
            port = (raw_addr >> 10) & 0x3F

            # Try to resolve register name
            reg_name = self._resolve_register_name(reg_offset, port)

            register_writes.append(
                RegisterWrite(
                    raw_address=raw_addr,
                    register_offset=reg_offset,
                    port=port,
                    value=value,
                    register_name=reg_name,
                )
            )

        return EepromContents(
            valid=True,
            signature=signature,
            payload_length=payload_length,
            register_writes=register_writes,
            raw_data=data,
        )

    def _resolve_register_name(self, offset: int, port: int) -> str | None:
        """Try to resolve a register name from device definition.

        Args:
            offset: Register offset.
            port: Port number.

        Returns:
            Register name if found, None otherwise.
        """
        if self.device_def is None:
            return None

        for name, reg in self.device_def.registers.items():
            if reg.per_port:
                # Check if offset matches this port's register
                if reg.port_offset(port) == offset:
                    return f"{name}[port{port}]"
            elif reg.offset == offset:
                return name

        return None

    def decode_file(self, path: str | Path) -> EepromContents:
        """Decode EEPROM contents from a file.

        Args:
            path: Path to EEPROM binary file.

        Returns:
            EepromContents with decoded information.
        """
        data = Path(path).read_bytes()
        return self.decode(data)

    def format_human_readable(self, contents: EepromContents) -> str:
        """Format decoded EEPROM contents as human-readable text.

        Args:
            contents: Decoded EEPROM contents.

        Returns:
            Formatted string.
        """
        lines: list[str] = []

        # Header
        lines.append("EEPROM Contents")
        lines.append("=" * 60)
        lines.append(f"Valid:          {'Yes' if contents.valid else 'No'}")
        lines.append(f"Signature:      0x{contents.signature:02X}")
        lines.append(f"Payload length: {contents.payload_length} bytes")
        lines.append(f"Register writes: {contents.num_writes}")
        lines.append("")

        if not contents.valid:
            lines.append("EEPROM is invalid or empty.")
            return "\n".join(lines)

        # Register writes
        lines.append("Register Writes:")
        lines.append("-" * 60)
        lines.append(f"{'#':>3}  {'Port':>4}  {'Offset':>8}  {'Value':>10}  Name")
        lines.append("-" * 60)

        for i, write in enumerate(contents.register_writes):
            name = write.register_name or "(unknown)"
            lines.append(
                f"{i:>3}  {write.port:>4}  0x{write.register_offset:04X}    "
                f"0x{write.value:08X}  {name}"
            )

        return "\n".join(lines)


def decode_eeprom(
    data: bytes,
    device_def: DeviceDefinition | None = None,
) -> EepromContents:
    """Convenience function to decode EEPROM contents.

    Args:
        data: Raw EEPROM data.
        device_def: Optional device definition for register name lookup.

    Returns:
        EepromContents with decoded information.
    """
    decoder = EepromDecoder(device_def)
    return decoder.decode(data)


def decode_eeprom_file(
    path: str | Path,
    device_def: DeviceDefinition | None = None,
) -> EepromContents:
    """Convenience function to decode EEPROM from file.

    Args:
        path: Path to EEPROM binary file.
        device_def: Optional device definition for register name lookup.

    Returns:
        EepromContents with decoded information.
    """
    decoder = EepromDecoder(device_def)
    return decoder.decode_file(path)
