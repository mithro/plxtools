"""I2C/SMBus backend for PLX switch access."""

from pathlib import Path

from plxtools.backends.base import BaseBackend

try:
    from smbus2 import SMBus
except ImportError:
    SMBus = None  # type: ignore[misc, assignment]


class I2cBackend(BaseBackend):
    """Access PLX switch registers via I2C/SMBus interface.

    PLX switches expose an I2C slave interface that allows register access
    when the PCIe bus is not available (e.g., corrupted EEPROM preventing
    enumeration).

    The I2C protocol uses:
    - 7-bit slave address (typically 0x38-0x3F for PLX switches)
    - 16-bit register addresses
    - 32-bit register values (little-endian)
    """

    def __init__(self, bus: int, address: int) -> None:
        """Initialize I2C backend.

        Args:
            bus: I2C bus number (e.g., 0 for /dev/i2c-0)
            address: 7-bit I2C slave address of the PLX switch

        Raises:
            ImportError: If smbus2 is not installed.
            ValueError: If bus number or address is invalid.
        """
        if SMBus is None:
            raise ImportError("smbus2 is required for I2C access")

        if bus < 0:
            raise ValueError(f"I2C bus number must be non-negative, got {bus}")
        # Valid 7-bit I2C addresses are 0x08-0x77 (0x00-0x07 and 0x78-0x7F reserved)
        if address < 0x08 or address > 0x77:
            raise ValueError(f"I2C address must be 0x08-0x77, got {address:#04x}")

        self.bus_number = bus
        self.address = address
        self._smbus: SMBus | None = None

    def _ensure_open(self) -> "SMBus":
        """Ensure SMBus is open, opening if necessary."""
        if self._smbus is None:
            self._smbus = SMBus(self.bus_number)
        return self._smbus

    def read32(self, offset: int) -> int:
        """Read a 32-bit register via I2C.

        Uses SMBus block read with 16-bit register address.
        """
        self._validate_offset(offset)
        bus = self._ensure_open()

        # Write 16-bit register address (big-endian)
        addr_high = (offset >> 8) & 0xFF
        addr_low = offset & 0xFF

        # Write address, then read 4 bytes
        bus.write_i2c_block_data(self.address, addr_high, [addr_low])
        data = bus.read_i2c_block_data(self.address, addr_high, 4)

        # Convert from little-endian bytes to int
        result = data[0] | (data[1] << 8) | (data[2] << 16) | (data[3] << 24)
        return result

    def write32(self, offset: int, value: int) -> None:
        """Write a 32-bit value via I2C.

        Uses SMBus block write with 16-bit register address.
        """
        self._validate_offset(offset)
        self._validate_value(value)
        bus = self._ensure_open()

        # 16-bit register address (big-endian)
        addr_high = (offset >> 8) & 0xFF
        addr_low = offset & 0xFF

        # 32-bit value (little-endian)
        data = [
            addr_low,
            value & 0xFF,
            (value >> 8) & 0xFF,
            (value >> 16) & 0xFF,
            (value >> 24) & 0xFF,
        ]

        bus.write_i2c_block_data(self.address, addr_high, data)

    def close(self) -> None:
        """Close the SMBus connection."""
        if self._smbus is not None:
            self._smbus.close()
            self._smbus = None

    @staticmethod
    def list_i2c_buses() -> list[int]:
        """List available I2C bus numbers.

        Returns:
            List of bus numbers (e.g., [0, 1, 2] for /dev/i2c-0, etc.)
        """
        buses: list[int] = []
        dev_path = Path("/dev")

        for device in dev_path.glob("i2c-*"):
            try:
                bus_num = int(device.name.split("-")[1])
                buses.append(bus_num)
            except (ValueError, IndexError):
                continue

        return sorted(buses)

    @classmethod
    def scan_bus(cls, bus: int, start: int = 0x08, end: int = 0x77) -> list[int]:
        """Scan an I2C bus for responding devices.

        Args:
            bus: I2C bus number
            start: First address to scan (default 0x08)
            end: Last address to scan (default 0x77)

        Returns:
            List of responding I2C addresses.
        """
        if SMBus is None:
            return []

        found: list[int] = []

        try:
            smbus = SMBus(bus)
            try:
                for addr in range(start, end + 1):
                    try:
                        # Try a quick read to detect presence
                        smbus.read_byte(addr)
                        found.append(addr)
                    except OSError:
                        # No device at this address
                        pass
            finally:
                smbus.close()
        except OSError:
            # Bus not available
            pass

        return found

    @classmethod
    def find_plx_devices(cls, bus: int) -> list[int]:
        """Find PLX switches on an I2C bus.

        Scans common PLX I2C addresses (0x38-0x3F) and checks for
        valid vendor ID response.

        Args:
            bus: I2C bus number to scan

        Returns:
            List of I2C addresses with PLX switches.
        """
        plx_addresses: list[int] = []

        # PLX switches typically use addresses 0x38-0x3F
        for addr in range(0x38, 0x40):
            try:
                backend = cls(bus, addr)
                try:
                    # Try to read vendor ID
                    vendor_device = backend.read32(0x00)
                    vendor_id = vendor_device & 0xFFFF
                    if vendor_id == 0x10B5:  # PLX vendor ID
                        plx_addresses.append(addr)
                except OSError:
                    pass
                finally:
                    backend.close()
            except OSError:
                pass

        return plx_addresses
