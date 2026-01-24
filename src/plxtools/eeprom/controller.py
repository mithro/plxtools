"""EEPROM controller for reading PLX switch EEPROM contents."""

import time
from dataclasses import dataclass
from pathlib import Path

from plxtools.backends.base import RegisterAccess
from plxtools.devices import DeviceDefinition, load_device_by_id


@dataclass
class EepromInfo:
    """Information about the EEPROM detected on a PLX switch."""

    valid: bool
    signature: int
    payload_length: int
    address_width: int  # 1 or 2 bytes
    total_size: int  # Estimated total size including header


# Default EEPROM parameters (used if no device definition available)
DEFAULT_CTRL_OFFSET = 0x260
DEFAULT_DATA_OFFSET = 0x264
DEFAULT_READ_CMD = 0x00A06000
DEFAULT_ADDR_MASK = 0x1FFF
DEFAULT_SIGNATURE = 0x5A
DEFAULT_MAX_SIZE = 8192


class EepromController:
    """Controller for reading EEPROM contents from PLX switches.

    Uses the EEPROM controller registers (typically at 0x260/0x264) to
    read EEPROM contents byte-by-byte.

    The EEPROM format is:
    - Byte 0: Signature (0x5A for valid EEPROM)
    - Byte 1: Reserved (0x00)
    - Bytes 2-3: Payload length (16-bit little-endian, num_writes * 6)
    - Bytes 4+: Register write entries (6 bytes each)
    """

    def __init__(
        self,
        backend: RegisterAccess,
        device_def: DeviceDefinition | None = None,
    ) -> None:
        """Initialize EEPROM controller.

        Args:
            backend: Backend for register access (must support BAR0 offsets).
            device_def: Optional device definition for device-specific parameters.
        """
        self.backend = backend
        self.device_def = device_def

        # Get EEPROM parameters from device definition or use defaults
        if device_def:
            eeprom = device_def.eeprom
            self._ctrl_offset = eeprom.ctrl_offset
            self._data_offset = eeprom.data_offset
            self._read_cmd = eeprom.read_cmd
            self._addr_mask = eeprom.addr_mask
            self._signature = eeprom.signature
            self._max_size = eeprom.max_size
        else:
            self._ctrl_offset = DEFAULT_CTRL_OFFSET
            self._data_offset = DEFAULT_DATA_OFFSET
            self._read_cmd = DEFAULT_READ_CMD
            self._addr_mask = DEFAULT_ADDR_MASK
            self._signature = DEFAULT_SIGNATURE
            self._max_size = DEFAULT_MAX_SIZE

    def _read_eeprom_dword(self, addr: int) -> int:
        """Read a 32-bit value from EEPROM at the given byte address.

        Args:
            addr: Byte address in EEPROM (will be masked to valid range).

        Returns:
            32-bit value read from EEPROM (little-endian).

        Raises:
            TimeoutError: If the EEPROM read does not complete within timeout.
        """
        # Mask address to valid range
        addr = addr & self._addr_mask

        # Write read command with address
        cmd = self._read_cmd | addr
        self.backend.write32(self._ctrl_offset, cmd)

        # Wait for completion (busy bit should clear)
        # In practice, PLX EEPROM reads are fast, but we poll to be safe
        for _ in range(100):
            status = self.backend.read32(self._ctrl_offset)
            if (status & 0x80000000) == 0:  # Busy bit clear
                break
            time.sleep(0.001)
        else:
            raise TimeoutError(
                f"EEPROM read timeout at address {addr:#x}: busy bit did not clear"
            )

        # Read data
        return self.backend.read32(self._data_offset)

    def read_byte(self, addr: int) -> int:
        """Read a single byte from EEPROM.

        Args:
            addr: Byte address in EEPROM.

        Returns:
            Byte value (0-255).
        """
        # Align to 4-byte boundary and extract the correct byte
        aligned_addr = addr & ~0x3
        offset = addr & 0x3
        dword = self._read_eeprom_dword(aligned_addr)
        return (dword >> (offset * 8)) & 0xFF

    def read_word(self, addr: int) -> int:
        """Read a 16-bit word from EEPROM (little-endian).

        Args:
            addr: Byte address in EEPROM.

        Returns:
            16-bit value.
        """
        low = self.read_byte(addr)
        high = self.read_byte(addr + 1)
        return low | (high << 8)

    def read_bytes(self, addr: int, length: int) -> bytes:
        """Read a sequence of bytes from EEPROM.

        Args:
            addr: Starting byte address.
            length: Number of bytes to read.

        Returns:
            Bytes read from EEPROM.
        """
        result = bytearray(length)

        # Optimize by reading aligned dwords where possible
        i = 0
        while i < length:
            current_addr = addr + i

            # If aligned and at least 4 bytes left, read a dword
            if (current_addr & 0x3) == 0 and (length - i) >= 4:
                dword = self._read_eeprom_dword(current_addr)
                result[i] = dword & 0xFF
                result[i + 1] = (dword >> 8) & 0xFF
                result[i + 2] = (dword >> 16) & 0xFF
                result[i + 3] = (dword >> 24) & 0xFF
                i += 4
            else:
                result[i] = self.read_byte(current_addr)
                i += 1

        return bytes(result)

    def detect_eeprom(self) -> EepromInfo:
        """Detect and validate EEPROM presence.

        Reads the EEPROM header to check for valid signature and
        determine payload length.

        Returns:
            EepromInfo with detection results.
        """
        # Read first 4 bytes
        header = self._read_eeprom_dword(0)

        signature = header & 0xFF
        reserved = (header >> 8) & 0xFF
        payload_length = (header >> 16) & 0xFFFF

        valid = signature == self._signature and reserved == 0x00

        # Determine address width (1 or 2 bytes)
        # If signature is at offset 0, it's likely 2-byte addressing
        # This is a simplification - real detection would check EEPROM type
        address_width = 2 if valid else 1

        # Calculate total size
        total_size = 4 + payload_length if valid else 0

        return EepromInfo(
            valid=valid,
            signature=signature,
            payload_length=payload_length,
            address_width=address_width,
            total_size=total_size,
        )

    def read_all(self, max_size: int | None = None) -> bytes:
        """Read entire EEPROM contents.

        Args:
            max_size: Maximum bytes to read (defaults to device max).

        Returns:
            EEPROM contents as bytes.
        """
        if max_size is None:
            max_size = self._max_size

        # First detect EEPROM to get actual size
        info = self.detect_eeprom()

        if info.valid and info.total_size > 0:
            # Read only the valid portion
            size = min(info.total_size, max_size)
        else:
            # EEPROM might be empty or invalid, read max
            size = max_size

        return self.read_bytes(0, size)

    def dump_to_file(self, path: str | Path, max_size: int | None = None) -> int:
        """Dump EEPROM contents to a binary file.

        Args:
            path: Path to output file.
            max_size: Maximum bytes to read.

        Returns:
            Number of bytes written.
        """
        data = self.read_all(max_size)
        Path(path).write_bytes(data)
        return len(data)


def read_eeprom(
    backend: RegisterAccess,
    vendor_id: int | None = None,
    device_id: int | None = None,
) -> bytes:
    """Convenience function to read EEPROM from a PLX switch.

    Args:
        backend: Backend for register access.
        vendor_id: Optional vendor ID for device-specific parameters.
        device_id: Optional device ID for device-specific parameters.

    Returns:
        EEPROM contents as bytes.
    """
    device_def = None
    if vendor_id is not None and device_id is not None:
        device_def = load_device_by_id(vendor_id, device_id)

    controller = EepromController(backend, device_def)
    return controller.read_all()
