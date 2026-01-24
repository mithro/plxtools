"""Mock backend for testing without real hardware."""

from plxtools.backends.base import BaseBackend


class MockBackend(BaseBackend):
    """Mock backend with configurable register responses.

    Simulates a PLX switch for testing purposes. Registers can be
    pre-populated with values, and all reads/writes are recorded.

    Attributes:
        registers: Dict mapping offsets to 32-bit values.
        read_log: List of (offset,) tuples for each read operation.
        write_log: List of (offset, value) tuples for each write operation.
    """

    def __init__(self, registers: dict[int, int] | None = None) -> None:
        """Initialize mock backend with optional pre-populated registers.

        Args:
            registers: Optional dict of offset -> value to pre-populate.
        """
        self.registers: dict[int, int] = dict(registers) if registers else {}
        self.read_log: list[tuple[int,]] = []
        self.write_log: list[tuple[int, int]] = []

    def read32(self, offset: int) -> int:
        """Read a 32-bit register, returning 0 for unset registers."""
        self._validate_offset(offset)
        self.read_log.append((offset,))
        return self.registers.get(offset, 0)

    def write32(self, offset: int, value: int) -> None:
        """Write a 32-bit value to a register."""
        self._validate_offset(offset)
        self._validate_value(value)
        self.write_log.append((offset, value))
        self.registers[offset] = value

    def reset_logs(self) -> None:
        """Clear read and write logs."""
        self.read_log.clear()
        self.write_log.clear()

    def set_register(self, offset: int, value: int) -> None:
        """Set a register value without logging (for test setup)."""
        self._validate_offset(offset)
        self._validate_value(value)
        self.registers[offset] = value

    def get_register(self, offset: int) -> int:
        """Get a register value without logging (for test verification)."""
        self._validate_offset(offset)
        return self.registers.get(offset, 0)


class MockEepromBackend(MockBackend):
    """Mock backend that simulates PLX EEPROM controller behavior.

    Simulates the EEPROM controller registers at offsets 0x260 (control)
    and 0x264 (data), responding to read commands with data from a
    simulated EEPROM.
    """

    EEPROM_CTRL_OFFSET = 0x260
    EEPROM_DATA_OFFSET = 0x264

    # Command bits in control register
    CMD_READ_MASK = 0xFFFFE000  # Mask for command bits (upper 19 bits)
    CMD_READ = 0x00A06000  # Read command pattern (from blog post)
    CMD_BUSY = 0x80000000  # Busy bit (never set in mock - instant completion)

    def __init__(
        self,
        eeprom_data: bytes | None = None,
        registers: dict[int, int] | None = None,
    ) -> None:
        """Initialize with optional EEPROM contents.

        Args:
            eeprom_data: Bytes representing EEPROM contents. Defaults to empty.
            registers: Optional pre-populated registers (in addition to EEPROM).
        """
        super().__init__(registers)
        self.eeprom_data = bytearray(eeprom_data) if eeprom_data else bytearray(8192)
        self._pending_read_addr: int | None = None

    def write32(self, offset: int, value: int) -> None:
        """Handle writes, simulating EEPROM controller for offset 0x260."""
        super().write32(offset, value)

        if offset == self.EEPROM_CTRL_OFFSET:
            # Check if this is a read command (upper bits match CMD_READ pattern)
            if (value & self.CMD_READ_MASK) == (self.CMD_READ & self.CMD_READ_MASK):
                addr = value & 0x1FFF
                self._pending_read_addr = addr

    def read32(self, offset: int) -> int:
        """Handle reads, returning EEPROM data for offset 0x264 after command."""
        if offset == self.EEPROM_DATA_OFFSET and self._pending_read_addr is not None:
            addr = self._pending_read_addr
            self._pending_read_addr = None
            self.read_log.append((offset,))

            # Read up to 4 bytes from EEPROM
            result = 0
            for i in range(4):
                byte_addr = addr + i
                if byte_addr < len(self.eeprom_data):
                    result |= self.eeprom_data[byte_addr] << (i * 8)
            return result

        if offset == self.EEPROM_CTRL_OFFSET:
            # Return status - never busy in mock
            self.read_log.append((offset,))
            return self.registers.get(offset, 0) & ~self.CMD_BUSY

        return super().read32(offset)

    def set_eeprom_byte(self, addr: int, value: int) -> None:
        """Set a single byte in the simulated EEPROM."""
        if addr < 0 or addr >= len(self.eeprom_data):
            raise ValueError(f"EEPROM address out of range: {addr}")
        if value < 0 or value > 255:
            raise ValueError(f"Byte value out of range: {value}")
        self.eeprom_data[addr] = value

    def set_eeprom_data(self, data: bytes, start_addr: int = 0) -> None:
        """Set a range of bytes in the simulated EEPROM."""
        end_addr = start_addr + len(data)
        if start_addr < 0 or end_addr > len(self.eeprom_data):
            raise ValueError(f"EEPROM range {start_addr}-{end_addr} out of bounds")
        self.eeprom_data[start_addr:end_addr] = data
