"""Base classes for PLX device definitions."""

from dataclasses import dataclass, field


@dataclass
class RegisterField:
    """A field within a register."""

    name: str
    description: str
    bit: int | None = None  # Single bit
    bits: tuple[int, int] | None = None  # Bit range [low, high]

    def __post_init__(self) -> None:
        """Validate that exactly one of bit or bits is specified."""
        if self.bit is None and self.bits is None:
            raise ValueError(
                f"RegisterField '{self.name}' must specify either 'bit' or 'bits'"
            )
        if self.bit is not None and self.bits is not None:
            raise ValueError(
                f"RegisterField '{self.name}' cannot specify both 'bit' and 'bits'"
            )

    @property
    def mask(self) -> int:
        """Calculate the bitmask for this field."""
        if self.bit is not None:
            return 1 << self.bit
        if self.bits is not None:
            low, high = self.bits
            return ((1 << (high - low + 1)) - 1) << low
        return 0

    @property
    def shift(self) -> int:
        """Get the bit position to shift for this field."""
        if self.bit is not None:
            return self.bit
        if self.bits is not None:
            return self.bits[0]
        return 0

    def extract(self, value: int) -> int:
        """Extract this field's value from a register value."""
        return (value & self.mask) >> self.shift

    def insert(self, reg_value: int, field_value: int) -> int:
        """Insert a field value into a register value."""
        return (reg_value & ~self.mask) | ((field_value << self.shift) & self.mask)


@dataclass
class Register:
    """A register definition."""

    name: str
    offset: int
    size: int
    access: str  # "ro", "rw", "wo"
    description: str
    fields: dict[str, RegisterField] = field(default_factory=dict)
    per_port: bool = False
    port_stride: int = 0

    def port_offset(self, port: int) -> int:
        """Calculate the register offset for a specific port."""
        if not self.per_port:
            return self.offset
        return self.offset + (port * self.port_stride)


@dataclass
class EepromConfig:
    """EEPROM access configuration."""

    ctrl_offset: int
    data_offset: int
    read_cmd: int
    addr_mask: int
    signature: int
    max_size: int


@dataclass
class DeviceInfo:
    """Device identification and capabilities."""

    vendor_id: int
    device_id: int
    name: str
    description: str
    ports: int
    lanes: int
    pcie_gen: int


@dataclass
class DeviceDefinition:
    """Complete device definition loaded from YAML."""

    info: DeviceInfo
    registers: dict[str, Register]
    eeprom: EepromConfig

    def get_register(self, name: str) -> Register | None:
        """Get a register by name."""
        return self.registers.get(name)

    def get_register_by_offset(self, offset: int) -> Register | None:
        """Find a register by its offset."""
        for reg in self.registers.values():
            if reg.offset == offset:
                return reg
        return None
