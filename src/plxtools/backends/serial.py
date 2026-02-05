"""Serial backend for PEX880xx switches via USB management interface.

This backend communicates with Broadcom PEX880xx PCIe switches through their
USB serial management interface, typically exposed as /dev/ttyACM0 at 9600 baud.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import serial

from plxtools.backends.base import BaseBackend


@dataclass
class SerialDeviceInfo:
    """Information from the 'ver' command."""

    serial_number: str
    company: str
    model: str
    version: str
    build_date: str


@dataclass
class EnvironmentInfo:
    """Environmental sensor data from the 'lsd' command."""

    switch_temp_c: int
    fan_rpm: int
    voltage_12v_mv: int
    voltage_1v8_mv: int
    voltage_0v9_mv: int


@dataclass
class PortStatus:
    """PCIe port link status from the 'showport' command."""

    port: int
    port_type: str  # "Upstream" or "Downstream"
    speed: str  # "Gen1", "Gen2", "Gen3", "Gen4"
    width: int  # Lane width (1, 2, 4, 8, 16)
    max_speed: str
    max_width: int


# Prompt that indicates end of command output
PROMPT = b"Cmd>"
PROMPT_STR = "Cmd>"


class SerialBackend(BaseBackend):
    """Access PEX880xx registers via USB serial management interface.

    The Serial Cables ATLAS HOST CARD exposes a CLI on /dev/ttyACM0 at 9600 baud.
    This backend implements the RegisterAccess protocol for register read/write
    operations using the 'dr' and 'mw' serial commands.

    Example:
        with SerialBackend("/dev/ttyACM0") as backend:
            value = backend.read32(0x60800000)
            backend.write32(0x100, 0xDEADBEEF)
    """

    def __init__(
        self,
        device_path: str,
        baudrate: int = 9600,
        timeout: float = 2.0,
    ) -> None:
        """Initialize serial connection to PLX switch.

        Args:
            device_path: Path to serial device (e.g., "/dev/ttyACM0").
            baudrate: Serial baud rate (default 9600).
            timeout: Read timeout in seconds (default 2.0).
        """
        self._device_path = device_path
        self._baudrate = baudrate
        self._timeout = timeout
        self._serial = serial.Serial(
            device_path,
            baudrate=baudrate,
            timeout=timeout,
        )
        # Clear any pending data and wait for prompt
        self._clear_buffer()

    def _clear_buffer(self) -> None:
        """Clear input buffer and synchronize with device."""
        # Flush any pending input
        if self._serial.in_waiting:
            self._serial.read(self._serial.in_waiting)
        # Send empty line to get fresh prompt
        self._serial.write(b"\r\n")
        self._serial.flush()
        # Wait briefly and clear response
        time.sleep(0.05)
        if self._serial.in_waiting:
            self._serial.read(self._serial.in_waiting)

    def send_command(self, cmd: str, timeout: float | None = None) -> str:
        """Send a command and return the response.

        Args:
            cmd: Command string to send.
            timeout: Optional timeout override.

        Returns:
            Response string with prompt stripped.

        Raises:
            OSError: If communication fails or times out.
        """
        # Set timeout if specified
        old_timeout = self._serial.timeout
        if timeout is not None:
            self._serial.timeout = timeout

        try:
            # Send command with carriage return
            cmd_bytes = (cmd.strip() + "\r\n").encode("ascii")
            self._serial.write(cmd_bytes)
            self._serial.flush()

            # Read response until we see the prompt
            response = b""
            start_time = time.monotonic()
            effective_timeout = timeout if timeout is not None else self._timeout

            while True:
                # Check for timeout
                elapsed = time.monotonic() - start_time
                if elapsed > effective_timeout:
                    raise OSError(f"Timeout waiting for response to '{cmd}'")

                # Read available data
                chunk = self._serial.read_until(PROMPT)
                response += chunk

                # Check if we got the prompt
                if PROMPT in response:
                    break

                # Also check if buffer has more data
                if self._serial.in_waiting == 0 and PROMPT not in response:
                    # Small sleep to avoid busy loop
                    time.sleep(0.01)

            # Decode and clean up response
            response_str = response.decode("ascii", errors="replace")

            # Strip the command echo (first line) and prompt
            lines = response_str.split("\n")
            # Remove echo of our command if present
            if lines and cmd.strip() in lines[0]:
                lines = lines[1:]
            # Remove prompt line
            result = "\n".join(lines)
            result = result.replace(PROMPT_STR, "").strip()

            return result

        finally:
            self._serial.timeout = old_timeout

    def read32(self, offset: int) -> int:
        """Read a 32-bit register at the given offset.

        Uses the 'dr <offset> 4' command to read a single 32-bit register.
        The dr command count parameter is in bytes, so 4 bytes = one 32-bit word.

        Args:
            offset: Register offset in bytes (must be 4-byte aligned).

        Returns:
            The 32-bit register value.

        Raises:
            ValueError: If offset is not 4-byte aligned.
            OSError: If the read operation fails or times out.
        """
        self._validate_offset(offset)

        # Send dr command (offset in hex, count in bytes: 4 = one 32-bit word)
        cmd = f"dr {offset:x} 4"
        response = self.send_command(cmd)

        # Parse response: "ADDR:VALUE [VALUE ...]"
        # Example: "60800000:c0101000 00100007 060400b0"
        value = self._parse_dr_response(response, offset)
        return value

    def _parse_dr_response(self, response: str, expected_addr: int) -> int:
        """Parse 'dr' command response to extract register value.

        Args:
            response: Response string from dr command.
            expected_addr: Expected address for validation.

        Returns:
            First 32-bit value from the response.

        Raises:
            OSError: If response cannot be parsed.
        """
        # Response format: "ADDR:VALUE [VALUE ...]"
        # May have multiple lines for multi-word reads
        for line in response.split("\n"):
            line = line.strip()
            if not line or ":" not in line:
                continue

            # Parse "ADDR:VALUE VALUE VALUE ..."
            match = re.match(r"([0-9a-fA-F]+):(.+)", line)
            if not match:
                continue

            values_str = match.group(2).strip()

            # Get first value
            values = values_str.split()
            if values:
                try:
                    value = int(values[0], 16)
                    return value
                except ValueError:
                    continue

        raise OSError(f"Failed to parse dr response: {response!r}")

    def write32(self, offset: int, value: int) -> None:
        """Write a 32-bit value to a register at the given offset.

        Uses the 'mw <offset> <value>' command to write a register.

        Args:
            offset: Register offset in bytes (must be 4-byte aligned).
            value: The 32-bit value to write.

        Raises:
            ValueError: If offset is not aligned or value out of range.
            OSError: If the write operation fails.
        """
        self._validate_offset(offset)
        self._validate_value(value)

        # Send mw command (offset and value in hex)
        cmd = f"mw {offset:x} {value:x}"
        self.send_command(cmd)

    def close(self) -> None:
        """Close the serial connection."""
        if self._serial.is_open:
            self._serial.close()

    # --- Extended device info methods ---

    def get_version(self) -> SerialDeviceInfo:
        """Get device version information.

        Returns:
            SerialDeviceInfo with serial number, model, version, etc.
        """
        response = self.send_command("ver")
        return self._parse_version_response(response)

    def _parse_version_response(self, response: str) -> SerialDeviceInfo:
        """Parse 'ver' command output.

        Actual format from hardware:
            S/N     : 400012002070309
            Company : Serial Cables
            Model   : ATLAS HOST CARD
            Version : 0.1.9     Date : Mar  4 2020 13:01:18
        """
        info: dict[str, str] = {}

        for line in response.split("\n"):
            line = line.strip()
            if ":" not in line:
                continue

            # Split on first colon
            key, _, value = line.partition(":")
            key = key.strip().lower().replace(" ", "_")
            value = value.strip()

            info[key] = value

        # Handle Version line that may contain "Date : ..."
        version_str = info.get("version", "")
        build_date = info.get("build_date", "")

        # Check if version contains embedded "Date :" field
        date_match = re.search(r"Date\s*:\s*(.+)", version_str)
        if date_match:
            build_date = date_match.group(1).strip()
            # Extract just the version number (before "Date")
            version_str = re.sub(r"\s*Date\s*:.*", "", version_str).strip()

        return SerialDeviceInfo(
            serial_number=info.get("s/n", info.get("serial_number", "")),
            company=info.get("company", ""),
            model=info.get("model", ""),
            version=version_str,
            build_date=build_date,
        )

    def get_environment(self) -> EnvironmentInfo:
        """Get environmental sensor data.

        Returns:
            EnvironmentInfo with temperature, fan speed, voltages.
        """
        response = self.send_command("lsd")
        return self._parse_environment_response(response)

    def _parse_environment_response(self, response: str) -> EnvironmentInfo:
        """Parse 'lsd' command output.

        Expected format:
            Switch Temperature: 45 C
            Fan Speed: 2500 RPM
            12V Rail: 12100 mV
            1.8V Rail: 1810 mV
            0.9V Rail: 905 mV
        """
        temp = 0
        fan = 0
        v12 = 0
        v18 = 0
        v09 = 0

        for line in response.split("\n"):
            line_lower = line.strip().lower()

            # Extract numeric value after the colon (the measurement value)
            if ":" in line:
                _, _, value_part = line.partition(":")
                match = re.search(r"(\d+)", value_part)
                if not match:
                    continue
                value = int(match.group(1))
            else:
                continue

            if "temperature" in line_lower or "temp" in line_lower:
                temp = value
            elif "fan" in line_lower:
                fan = value
            elif "12v" in line_lower:
                v12 = value
            elif "1.8v" in line_lower or "1v8" in line_lower:
                v18 = value
            elif "0.9v" in line_lower or "0v9" in line_lower:
                v09 = value

        return EnvironmentInfo(
            switch_temp_c=temp,
            fan_rpm=fan,
            voltage_12v_mv=v12,
            voltage_1v8_mv=v18,
            voltage_0v9_mv=v09,
        )

    def get_port_status(self) -> list[PortStatus]:
        """Get PCIe port link status.

        Returns:
            List of PortStatus for each port.
        """
        response = self.send_command("showport")
        return self._parse_port_status_response(response)

    def _parse_port_status_response(self, response: str) -> list[PortStatus]:
        """Parse 'showport' command output.

        Actual format from hardware:
            Atals chip ver: B0
            ====...====
                                  Upstream
            ====...====
            Port  0: speed = Gen3, width = 8, max_speed = Gen4, max_width = 16
            ====...====
                                  Downstream
            ====...====
            Port 16: speed = Gen1, width = 0, max_speed = Gen4, max_width = 1
            Port 17: speed = Gen1, width = 0, max_speed = Gen4, max_width = 1
        """
        ports: list[PortStatus] = []
        current_type = "Unknown"

        # Pattern for port lines: "Port  N: speed = GenX, width = N, ..."
        port_re = re.compile(
            r"Port\s+(\d+):\s*"
            r"speed\s*=\s*(\w+),\s*"
            r"width\s*=\s*(\d+),\s*"
            r"max_speed\s*=\s*(\w+),\s*"
            r"max_width\s*=\s*(\d+)"
        )

        for line in response.split("\n"):
            line = line.strip()

            # Skip empty lines and separator lines
            if not line or line.startswith("="):
                continue

            # Detect section headers
            if line.lower() == "upstream":
                current_type = "Upstream"
                continue
            if line.lower() == "downstream":
                current_type = "Downstream"
                continue

            # Try to parse port line
            match = port_re.match(line)
            if match:
                ports.append(
                    PortStatus(
                        port=int(match.group(1)),
                        port_type=current_type,
                        speed=match.group(2),
                        width=int(match.group(3)),
                        max_speed=match.group(4),
                        max_width=int(match.group(5)),
                    )
                )

        return ports

    # --- I2C passthrough methods ---

    def i2c_scan(self, channel: int = 0) -> list[int]:
        """Scan I2C bus for devices.

        Args:
            channel: I2C channel to scan (default 0).

        Returns:
            List of responding I2C addresses.
        """
        response = self.send_command("scan")
        return self._parse_i2c_scan_response(response)

    def _parse_i2c_scan_response(self, response: str) -> list[int]:
        """Parse 'scan' command output.

        Actual format from hardware:
            Scan I2C channel 0 devices ....
            Device address:0x40 found
            Device address:0xa2 found
        """
        addresses: list[int] = []

        for line in response.split("\n"):
            line = line.strip()

            # Match "Device address:0xXX found" or "0xXX: ACK" formats
            match = re.search(
                r"(?:address:\s*)?0x([0-9a-fA-F]+)\s*(?:found|ACK)", line, re.IGNORECASE
            )
            if match:
                addr = int(match.group(1), 16)
                addresses.append(addr)

        return addresses

    def i2c_read(
        self,
        address: int,
        connector: int,
        read_len: int,
        write_data: bytes,
    ) -> bytes:
        """Read from I2C device.

        Uses 'iicwr <addr> <con> <read_bytes> <write_data>' command.

        Args:
            address: I2C device address.
            connector: I2C connector number.
            read_len: Number of bytes to read.
            write_data: Data to write before reading (register address).

        Returns:
            Bytes read from device.
        """
        # Format write_data as hex bytes
        write_hex = " ".join(f"{b:02x}" for b in write_data)
        cmd = f"iicwr {address:x} {connector} {read_len} {write_hex}"
        response = self.send_command(cmd)

        return self._parse_i2c_read_response(response)

    def _parse_i2c_read_response(self, response: str) -> bytes:
        """Parse iicwr response.

        Expected format:
            Data: 01 02 03 04 05 06 07 08
        """
        for line in response.split("\n"):
            line = line.strip()

            # Look for "Data:" line
            if "data" in line.lower():
                # Extract hex bytes after colon
                _, _, hex_part = line.partition(":")
                hex_part = hex_part.strip()

                # Parse hex bytes
                byte_strs = hex_part.split()
                return bytes(int(b, 16) for b in byte_strs)

        raise OSError(f"Failed to parse i2c read response: {response!r}")

    def i2c_write(self, address: int, connector: int, data: bytes) -> None:
        """Write to I2C device.

        Uses 'iicw <addr> <con> <write_data...>' command.

        Args:
            address: I2C device address.
            connector: I2C connector number.
            data: Bytes to write.
        """
        # Format data as hex bytes
        data_hex = " ".join(f"{b:02x}" for b in data)
        cmd = f"iicw {address:x} {connector} {data_hex}"
        self.send_command(cmd)

    # --- Flash access ---

    def read_flash(self, address: int, count: int = 1) -> bytes:
        """Read from flash memory.

        Uses 'df <addr> [count]' command.

        Args:
            address: Flash address to read from.
            count: Number of bytes to read.

        Returns:
            Bytes read from flash.
        """
        cmd = f"df {address:x} {count:x}"
        response = self.send_command(cmd)

        return self._parse_flash_response(response)

    def _parse_flash_response(self, response: str) -> bytes:
        """Parse df (dump flash) response.

        Actual format from hardware (32-bit words, not individual bytes):
            00000000:efbeadde 00000b00 00000000 00000400
            00000010:00000000 01000000 00000400 00000400
        """
        import struct

        data = bytearray()

        for line in response.split("\n"):
            line = line.strip()

            # Parse "ADDR:WORD WORD WORD ..." format
            match = re.match(r"[0-9a-fA-F]+:(.+)", line)
            if not match:
                continue

            hex_part = match.group(1).strip()

            for word_str in hex_part.split():
                word_str = word_str.strip()
                if not word_str:
                    continue
                # Handle 8-char hex words (32-bit values)
                if re.match(r"^[0-9a-fA-F]{8}$", word_str):
                    word = int(word_str, 16)
                    # Store as little-endian bytes (PCIe convention)
                    data.extend(struct.pack("<I", word))
                # Also handle individual hex bytes for compatibility
                elif re.match(r"^[0-9a-fA-F]{2}$", word_str):
                    data.append(int(word_str, 16))

        return bytes(data)
