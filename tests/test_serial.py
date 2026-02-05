"""Tests for serial backend."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from plxtools.backends.base import RegisterAccess

if TYPE_CHECKING:
    from collections.abc import Callable


class MockSerial:
    """Mock serial port for testing SerialBackend.

    Simulates pyserial's Serial class with configurable responses.
    """

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        *,
        default_response: str = "Cmd>",
    ) -> None:
        """Initialize mock serial port.

        Args:
            responses: Dict mapping command patterns (regex) to responses.
            default_response: Response when no pattern matches.
        """
        self.responses = responses or {}
        self.default_response = default_response
        self.written: list[bytes] = []
        self.is_open = True
        self.timeout: float | None = 2.0  # Match pyserial's timeout attribute
        self._read_buffer = b""
        self._response_handler: Callable[[str], str] | None = None

    def write(self, data: bytes) -> int:
        """Record written data and prepare response."""
        self.written.append(data)
        cmd = data.decode("ascii", errors="replace").strip()

        # Find matching response
        response = self.default_response
        for pattern, resp in self.responses.items():
            if re.match(pattern, cmd):
                response = resp
                break

        # Custom handler takes precedence
        if self._response_handler:
            response = self._response_handler(cmd)

        # Add response to read buffer (with trailing prompt)
        if not response.endswith("Cmd>"):
            response = response + "\nCmd>"
        self._read_buffer += response.encode("ascii")

        return len(data)

    def read(self, size: int = 1) -> bytes:
        """Read from buffer."""
        data = self._read_buffer[:size]
        self._read_buffer = self._read_buffer[size:]
        return data

    def read_until(self, expected: bytes = b"\n", size: int | None = None) -> bytes:
        """Read until expected bytes found."""
        if expected in self._read_buffer:
            idx = self._read_buffer.index(expected) + len(expected)
            data = self._read_buffer[:idx]
            self._read_buffer = self._read_buffer[idx:]
            return data
        # Return all if not found
        data = self._read_buffer
        self._read_buffer = b""
        return data

    @property
    def in_waiting(self) -> int:
        """Return number of bytes in read buffer."""
        return len(self._read_buffer)

    def flush(self) -> None:
        """Flush output buffer (no-op for mock)."""
        pass

    def close(self) -> None:
        """Close the port."""
        self.is_open = False

    def set_response_handler(self, handler: Callable[[str], str]) -> None:
        """Set a custom response handler for dynamic responses."""
        self._response_handler = handler


class TestSerialBackendProtocol:
    """Test that SerialBackend implements RegisterAccess protocol."""

    def test_implements_register_access_protocol(self) -> None:
        """SerialBackend should implement the RegisterAccess protocol."""
        from plxtools.backends.serial import SerialBackend

        # Create a mock that won't actually connect
        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial_class.return_value = MockSerial()
            backend = SerialBackend("/dev/ttyACM0")

            # Check protocol compliance
            assert isinstance(backend, RegisterAccess)
            assert hasattr(backend, "read32")
            assert hasattr(backend, "write32")
            assert hasattr(backend, "close")
            assert callable(backend.read32)
            assert callable(backend.write32)
            assert callable(backend.close)

            backend.close()


class TestSerialBackendInit:
    """Test SerialBackend initialization."""

    def test_init_with_defaults(self) -> None:
        """Initialize with default parameters."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_instance = MockSerial()
            mock_serial_class.return_value = mock_instance

            backend = SerialBackend("/dev/ttyACM0")

            mock_serial_class.assert_called_once_with(
                "/dev/ttyACM0",
                baudrate=9600,
                timeout=2.0,
            )
            assert backend._device_path == "/dev/ttyACM0"
            backend.close()

    def test_init_with_custom_params(self) -> None:
        """Initialize with custom baudrate and timeout."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_instance = MockSerial()
            mock_serial_class.return_value = mock_instance

            backend = SerialBackend("/dev/ttyUSB0", baudrate=115200, timeout=5.0)

            mock_serial_class.assert_called_once_with(
                "/dev/ttyUSB0",
                baudrate=115200,
                timeout=5.0,
            )
            backend.close()


class TestSerialBackendRead32:
    """Test SerialBackend.read32() method."""

    def test_read32_sends_dr_command(self) -> None:
        """read32 should send 'dr <offset> 4' command (count is in bytes)."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial = MockSerial(
                responses={
                    r"dr\s+60800000\s+4": "60800000:c0101000\nCmd>",
                }
            )
            mock_serial_class.return_value = mock_serial

            backend = SerialBackend("/dev/ttyACM0")
            value = backend.read32(0x60800000)

            assert value == 0xC0101000
            # Verify command was sent with count=4 (bytes)
            assert any(b"dr 60800000 4" in w for w in mock_serial.written)
            backend.close()

    def test_read32_parses_dr_output_single_value(self) -> None:
        """read32 should parse single-value dr output correctly."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            # Response format: address:value
            mock_serial = MockSerial(
                responses={
                    r"dr\s+0\s+4": "00000000:10b50001\nCmd>",
                }
            )
            mock_serial_class.return_value = mock_serial

            backend = SerialBackend("/dev/ttyACM0")
            value = backend.read32(0)

            assert value == 0x10B50001
            backend.close()

    def test_read32_parses_dr_output_multi_value(self) -> None:
        """read32 should handle multi-value dr output (only use first)."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            # Response format when device returns multiple values on one line
            mock_serial = MockSerial(
                responses={
                    r"dr\s+0\s+4": "00000000:c0101000 00100007 060400b0 00010000\nCmd>",
                }
            )
            mock_serial_class.return_value = mock_serial

            backend = SerialBackend("/dev/ttyACM0")
            value = backend.read32(0)

            # Should return first value only
            assert value == 0xC0101000
            backend.close()

    def test_read32_validates_alignment(self) -> None:
        """read32 should reject non-4-byte-aligned offsets."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial_class.return_value = MockSerial()

            backend = SerialBackend("/dev/ttyACM0")

            with pytest.raises(ValueError, match="4-byte aligned"):
                backend.read32(1)

            with pytest.raises(ValueError, match="4-byte aligned"):
                backend.read32(0x60800003)

            backend.close()

    def test_read32_validates_negative_offset(self) -> None:
        """read32 should reject negative offsets."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial_class.return_value = MockSerial()

            backend = SerialBackend("/dev/ttyACM0")

            with pytest.raises(ValueError, match="non-negative"):
                backend.read32(-4)

            backend.close()


class TestSerialBackendWrite32:
    """Test SerialBackend.write32() method."""

    def test_write32_sends_mw_command(self) -> None:
        """write32 should send 'mw <offset> <value>' command."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial = MockSerial(
                responses={
                    r"mw\s+100\s+deadbeef": "Cmd>",
                }
            )
            mock_serial_class.return_value = mock_serial

            backend = SerialBackend("/dev/ttyACM0")
            backend.write32(0x100, 0xDEADBEEF)

            # Verify command was sent (case-insensitive hex)
            assert any(b"mw 100 deadbeef" in w.lower() for w in mock_serial.written)
            backend.close()

    def test_write32_validates_alignment(self) -> None:
        """write32 should reject non-4-byte-aligned offsets."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial_class.return_value = MockSerial()

            backend = SerialBackend("/dev/ttyACM0")

            with pytest.raises(ValueError, match="4-byte aligned"):
                backend.write32(1, 0)

            backend.close()

    def test_write32_validates_value_range(self) -> None:
        """write32 should reject values outside 32-bit range."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial_class.return_value = MockSerial()

            backend = SerialBackend("/dev/ttyACM0")

            with pytest.raises(ValueError, match="0-0xFFFFFFFF"):
                backend.write32(0, 0x100000000)

            with pytest.raises(ValueError, match="0-0xFFFFFFFF"):
                backend.write32(0, -1)

            backend.close()


class TestSerialBackendContextManager:
    """Test SerialBackend context manager support."""

    def test_context_manager_closes_on_exit(self) -> None:
        """Context manager should close serial port on exit."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial = MockSerial()
            mock_serial_class.return_value = mock_serial

            with SerialBackend("/dev/ttyACM0") as backend:
                assert mock_serial.is_open
                assert backend is not None

            assert not mock_serial.is_open

    def test_context_manager_closes_on_exception(self) -> None:
        """Context manager should close serial port even on exception."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial = MockSerial()
            mock_serial_class.return_value = mock_serial

            with pytest.raises(RuntimeError):
                with SerialBackend("/dev/ttyACM0"):
                    raise RuntimeError("test error")

            assert not mock_serial.is_open


class TestSerialBackendSendCommand:
    """Test SerialBackend.send_command() raw interface."""

    def test_send_command_returns_response(self) -> None:
        """send_command should return the command response."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial = MockSerial(
                responses={
                    r"ver": "Serial Number  : SN123456\nCompany        : Broadcom\nCmd>",
                }
            )
            mock_serial_class.return_value = mock_serial

            backend = SerialBackend("/dev/ttyACM0")
            response = backend.send_command("ver")

            assert "Serial Number" in response
            assert "SN123456" in response
            backend.close()

    def test_send_command_strips_prompt(self) -> None:
        """send_command should strip the Cmd> prompt from response."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial = MockSerial(
                responses={
                    r"ver": "Version: 1.0\nCmd>",
                }
            )
            mock_serial_class.return_value = mock_serial

            backend = SerialBackend("/dev/ttyACM0")
            response = backend.send_command("ver")

            assert "Cmd>" not in response
            assert "Version: 1.0" in response
            backend.close()


class TestSerialBackendTimeout:
    """Test SerialBackend timeout handling."""

    def test_timeout_raises_oserror(self) -> None:
        """Timeout should raise OSError."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial = MagicMock()
            mock_serial.is_open = True
            mock_serial.read_until.return_value = b""  # Simulate timeout (no data)
            mock_serial.in_waiting = 0
            mock_serial_class.return_value = mock_serial

            backend = SerialBackend("/dev/ttyACM0", timeout=0.1)

            with pytest.raises(OSError, match="[Tt]imeout"):
                backend.read32(0)

            mock_serial.close()


class TestResponseParsing:
    """Test parsing of various serial command responses."""

    def test_parse_version_output(self) -> None:
        """Parse 'ver' command output matching actual hardware format."""
        from plxtools.backends.serial import SerialBackend

        # Actual format from Serial Cables ATLAS HOST CARD
        ver_response = """S/N     : 400012002070309
Company : Serial Cables
Model   : ATLAS HOST CARD
Version : 0.1.9     Date : Mar  4 2020 13:01:18
Cmd>"""

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial = MockSerial(responses={r"ver": ver_response})
            mock_serial_class.return_value = mock_serial

            backend = SerialBackend("/dev/ttyACM0")
            info = backend.get_version()

            assert info.serial_number == "400012002070309"
            assert info.company == "Serial Cables"
            assert info.model == "ATLAS HOST CARD"
            assert info.version == "0.1.9"
            assert info.build_date == "Mar  4 2020 13:01:18"
            backend.close()

    def test_parse_environment_output(self) -> None:
        """Parse 'lsd' command output into EnvironmentInfo."""
        from plxtools.backends.serial import SerialBackend

        lsd_response = """Switch Temperature: 45 C
Fan Speed: 2500 RPM
12V Rail: 12100 mV
1.8V Rail: 1810 mV
0.9V Rail: 905 mV
Cmd>"""

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial = MockSerial(responses={r"lsd": lsd_response})
            mock_serial_class.return_value = mock_serial

            backend = SerialBackend("/dev/ttyACM0")
            env = backend.get_environment()

            assert env.switch_temp_c == 45
            assert env.fan_rpm == 2500
            assert env.voltage_12v_mv == 12100
            assert env.voltage_1v8_mv == 1810
            assert env.voltage_0v9_mv == 905
            backend.close()

    def test_parse_port_status_output(self) -> None:
        """Parse 'showport' command output matching actual hardware format."""
        from plxtools.backends.serial import SerialBackend

        # Actual format from Serial Cables ATLAS HOST CARD
        sep = "=" * 76
        showport_response = (
            "Atals chip ver: B0\r\n"
            + sep + "\r\n"
            + "                              Upstream\r\n"
            + sep + "\r\n"
            + "Port  0: speed = Gen3, width = 8, max_speed = Gen4, max_width = 16\r\n"
            + sep + "\r\n"
            + "                              Downstream\r\n"
            + sep + "\r\n"
            + "Port 16: speed = Gen1, width = 0, max_speed = Gen4, max_width = 1\r\n"
            + "Port 17: speed = Gen1, width = 0, max_speed = Gen4, max_width = 1\r\n"
            + "Cmd>"
        )

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial = MockSerial(responses={r"showport": showport_response})
            mock_serial_class.return_value = mock_serial

            backend = SerialBackend("/dev/ttyACM0")
            ports = backend.get_port_status()

            assert len(ports) == 3

            assert ports[0].port == 0
            assert ports[0].port_type == "Upstream"
            assert ports[0].speed == "Gen3"
            assert ports[0].width == 8
            assert ports[0].max_speed == "Gen4"
            assert ports[0].max_width == 16

            assert ports[1].port == 16
            assert ports[1].port_type == "Downstream"
            assert ports[1].speed == "Gen1"
            assert ports[1].width == 0

            assert ports[2].port == 17
            assert ports[2].port_type == "Downstream"
            assert ports[2].speed == "Gen1"
            assert ports[2].max_width == 1

            backend.close()

    def test_parse_i2c_scan_output(self) -> None:
        """Parse 'scan' command output matching actual hardware format."""
        from plxtools.backends.serial import SerialBackend

        # Actual format from Serial Cables ATLAS HOST CARD
        scan_response = """Scan I2C channel 0 devices ....
Device address:0x40 found
Device address:0x42 found
Device address:0xa2 found
Device address:0xd2 found
Cmd>"""

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial = MockSerial(responses={r"scan": scan_response})
            mock_serial_class.return_value = mock_serial

            backend = SerialBackend("/dev/ttyACM0")
            addresses = backend.i2c_scan()

            assert addresses == [0x40, 0x42, 0xA2, 0xD2]
            backend.close()


class TestI2CMethods:
    """Test I2C passthrough methods."""

    def test_i2c_read_sends_iicwr_command(self) -> None:
        """i2c_read should send 'iicwr' command and return bytes."""
        from plxtools.backends.serial import SerialBackend

        # iicwr <addr> <con> <read_bytes> <write_data>
        # Response is hex bytes
        iicwr_response = """Data: 01 02 03 04 05 06 07 08
Cmd>"""

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial = MockSerial(responses={r"iicwr\s+d4\s+1\s+8\s+0": iicwr_response})
            mock_serial_class.return_value = mock_serial

            backend = SerialBackend("/dev/ttyACM0")
            data = backend.i2c_read(address=0xD4, connector=1, read_len=8, write_data=b"\x00")

            assert data == bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
            backend.close()

    def test_i2c_write_sends_iicw_command(self) -> None:
        """i2c_write should send 'iicw' command."""
        from plxtools.backends.serial import SerialBackend

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial = MockSerial(responses={r"iicw\s+d4\s+1\s+ff\s+00": "OK\nCmd>"})
            mock_serial_class.return_value = mock_serial

            backend = SerialBackend("/dev/ttyACM0")
            backend.i2c_write(address=0xD4, connector=1, data=b"\xff\x00")

            # Verify command format
            assert any(b"iicw" in w for w in mock_serial.written)
            backend.close()


class TestFlashAccess:
    """Test flash read method."""

    def test_read_flash_sends_df_command(self) -> None:
        """read_flash should send 'df' command and return bytes."""
        from plxtools.backends.serial import SerialBackend

        # Actual format from hardware: 32-bit words, not individual bytes
        df_response = """00000000:efbeadde 00000b00 00000000 00000400
00000010:00000000 01000000 00000400 00000400
Cmd>"""

        with patch("plxtools.backends.serial.serial.Serial") as mock_serial_class:
            mock_serial = MockSerial(responses={r"df\s+0\s+20": df_response})
            mock_serial_class.return_value = mock_serial

            backend = SerialBackend("/dev/ttyACM0")
            data = backend.read_flash(address=0, count=0x20)

            # 8 words * 4 bytes each = 32 bytes
            assert len(data) == 32
            # First word 0xefbeadde stored as little-endian bytes
            assert data[0:4] == b"\xde\xad\xbe\xef"
            backend.close()
