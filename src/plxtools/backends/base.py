"""Abstract base classes for hardware access backends."""

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from typing_extensions import Self


@runtime_checkable
class RegisterAccess(Protocol):
    """Protocol for register-level access to PLX switches.

    All backends must implement this protocol to provide a unified interface
    for reading and writing 32-bit registers regardless of the underlying
    access method (PCIe config space, BAR0 mmap, I2C, etc.).

    This is a structural typing Protocol - classes don't need to explicitly
    inherit from it, they just need to implement the methods.
    """

    def read32(self, offset: int) -> int:
        """Read a 32-bit register at the given offset.

        Args:
            offset: Register offset in bytes (must be 4-byte aligned).

        Returns:
            The 32-bit register value.

        Raises:
            OSError: If the read operation fails.
            ValueError: If offset is not 4-byte aligned.
        """
        ...

    def write32(self, offset: int, value: int) -> None:
        """Write a 32-bit value to the register at the given offset.

        Args:
            offset: Register offset in bytes (must be 4-byte aligned).
            value: The 32-bit value to write.

        Raises:
            OSError: If the write operation fails.
            ValueError: If offset is not 4-byte aligned or value > 0xFFFFFFFF.
        """
        ...

    def close(self) -> None:
        """Release any resources held by the backend."""
        ...


class BaseBackend(ABC):
    """Abstract base class for hardware access backends.

    Provides common functionality and enforces the RegisterAccess protocol.
    Subclasses must implement read32() and write32().
    """

    def _validate_offset(self, offset: int) -> None:
        """Validate that offset is a valid 4-byte aligned address."""
        if offset < 0:
            raise ValueError(f"Offset must be non-negative, got {offset}")
        if offset % 4 != 0:
            raise ValueError(f"Offset must be 4-byte aligned, got {offset:#x}")

    def _validate_value(self, value: int) -> None:
        """Validate that value fits in 32 bits."""
        if value < 0 or value > 0xFFFFFFFF:
            raise ValueError(f"Value must be 0-0xFFFFFFFF, got {value:#x}")

    @abstractmethod
    def read32(self, offset: int) -> int:
        """Read a 32-bit register at the given offset."""
        ...

    @abstractmethod
    def write32(self, offset: int, value: int) -> None:
        """Write a 32-bit value to the register at the given offset."""
        ...

    def close(self) -> None:  # noqa: B027
        """Release any resources held by the backend.

        Intentionally not abstract - close() is optional and defaults to no-op.
        Subclasses with resources to release should override this.
        """

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> None:
        self.close()
