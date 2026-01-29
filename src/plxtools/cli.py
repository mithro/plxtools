"""Command-line interface for plxtools."""

import json
import sys
from pathlib import Path

import click

from plxtools import __version__
from plxtools.discovery import discover_plx_devices, discover_plx_switches


@click.group()
@click.version_option(version=__version__)
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format")
@click.pass_context
def main(ctx: click.Context, json_output: bool) -> None:
    """PLX/PEX PCIe switch tools.

    Read and decode EEPROM contents from PLX switches via PCIe or I2C.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output


@main.command("list")
@click.option("--all", "show_all", is_flag=True, help="Show all PLX devices, not just switches")
@click.pass_context
def list_devices(ctx: click.Context, show_all: bool) -> None:
    """List PLX switches in the system."""
    if show_all:
        devices = discover_plx_devices()
    else:
        devices = discover_plx_switches()

    if ctx.obj["json"]:
        output = [
            {
                "bdf": d.bdf,
                "vendor_id": f"0x{d.vendor_id:04X}",
                "device_id": f"0x{d.device_id:04X}",
                "device_name": d.device_name,
                "is_switch": d.is_switch,
            }
            for d in devices
        ]
        click.echo(json.dumps(output, indent=2))
    else:
        if not devices:
            click.echo("No PLX devices found.")
            return

        click.echo(f"Found {len(devices)} PLX device(s):")
        click.echo()
        for device in devices:
            switch_marker = " [switch]" if device.is_switch else ""
            click.echo(f"  {device.bdf}: {device.device_name}{switch_marker}")


@main.group()
def eeprom() -> None:
    """EEPROM operations."""
    pass


@eeprom.command("read")
@click.argument("bdf")
@click.option("-o", "--output", type=click.Path(), help="Output file path")
@click.option("--max-size", type=int, default=8192, help="Maximum bytes to read")
@click.pass_context
def eeprom_read(ctx: click.Context, bdf: str, output: str | None, max_size: int) -> None:
    """Read EEPROM contents from a PLX switch.

    BDF is the PCI address (e.g., 0000:03:00.0).
    """
    from plxtools.backends.pcie_mmap import PcieMmapBackend
    from plxtools.backends.pcie_sysfs import validate_bdf
    from plxtools.eeprom import EepromController

    try:
        validate_bdf(bdf)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        with PcieMmapBackend(bdf) as backend:
            controller = EepromController(backend)
            info = controller.detect_eeprom()

            if not info.valid:
                click.echo(f"Warning: EEPROM signature invalid (0x{info.signature:02X})", err=True)

            data = controller.read_all(max_size)

            if output:
                Path(output).write_bytes(data)
                click.echo(f"Read {len(data)} bytes to {output}")
            elif ctx.obj["json"]:
                # Output as hex string in JSON
                result = {
                    "bdf": bdf,
                    "valid": info.valid,
                    "size": len(data),
                    "data_hex": data.hex(),
                }
                click.echo(json.dumps(result, indent=2))
            else:
                # Binary output to stdout
                sys.stdout.buffer.write(data)

    except FileNotFoundError:
        click.echo(f"Error: Device {bdf} not found", err=True)
        sys.exit(1)
    except PermissionError:
        click.echo(f"Error: Permission denied accessing {bdf}. Try running as root.", err=True)
        sys.exit(1)
    except OSError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@eeprom.command("decode")
@click.argument("file", type=click.Path(exists=True))
@click.option("--device", type=str, help="Device name for register lookup (e.g., PEX8733)")
@click.pass_context
def eeprom_decode(ctx: click.Context, file: str, device: str | None) -> None:
    """Decode EEPROM contents from a binary file.

    FILE is the path to the EEPROM binary dump.
    """
    from plxtools.devices import load_device_by_name
    from plxtools.eeprom import EepromDecoder

    device_def = None
    if device:
        device_def = load_device_by_name(device)
        if device_def is None:
            click.echo(
                f"Warning: Unknown device {device}, register names won't be resolved",
                err=True,
            )

    decoder = EepromDecoder(device_def)
    contents = decoder.decode_file(file)

    if ctx.obj["json"]:
        click.echo(contents.to_json())
    else:
        click.echo(decoder.format_human_readable(contents))


@main.command("info")
@click.argument("bdf")
@click.pass_context
def device_info(ctx: click.Context, bdf: str) -> None:
    """Show detailed information about a PLX device.

    BDF is the PCI address (e.g., 0000:03:00.0).
    """
    from plxtools.backends.pcie_sysfs import PcieSysfsBackend, validate_bdf
    from plxtools.devices import load_device_by_id

    try:
        validate_bdf(bdf)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        with PcieSysfsBackend(bdf) as backend:
            vendor_id = backend.vendor_id
            device_id = backend.device_id

            device_def = load_device_by_id(vendor_id, device_id)

            if ctx.obj["json"]:
                result = {
                    "bdf": bdf,
                    "vendor_id": f"0x{vendor_id:04X}",
                    "device_id": f"0x{device_id:04X}",
                    "device_name": device_def.info.name if device_def else None,
                    "ports": device_def.info.ports if device_def else None,
                    "lanes": device_def.info.lanes if device_def else None,
                }
                click.echo(json.dumps(result, indent=2))
            else:
                click.echo(f"Device: {bdf}")
                click.echo(f"Vendor ID: 0x{vendor_id:04X}")
                click.echo(f"Device ID: 0x{device_id:04X}")
                if device_def:
                    click.echo(f"Name: {device_def.info.name}")
                    click.echo(f"Description: {device_def.info.description}")
                    click.echo(f"Ports: {device_def.info.ports}")
                    click.echo(f"Lanes: {device_def.info.lanes}")

    except FileNotFoundError:
        click.echo(f"Error: Device {bdf} not found", err=True)
        sys.exit(1)
    except PermissionError:
        click.echo(f"Error: Permission denied accessing {bdf}. Try running as root.", err=True)
        sys.exit(1)


@main.command("shell")
def interactive_shell() -> None:
    """Start an interactive Python shell with plxtools loaded."""
    try:
        from IPython import start_ipython
    except ImportError:
        click.echo("Error: IPython is required for interactive shell.", err=True)
        click.echo("Install with: uv pip install ipython", err=True)
        sys.exit(1)

    # Pre-import useful modules
    banner = """
plxtools Interactive Shell
===========================
Available imports:
  - plxtools.backends (MockBackend, PcieSysfsBackend, PcieMmapBackend, I2cBackend)
  - plxtools.discovery (discover_plx_devices, discover_plx_switches)
  - plxtools.devices (load_device_by_name, load_device_by_id)
  - plxtools.eeprom (EepromController, EepromDecoder)

Example:
  from plxtools.discovery import discover_plx_switches
  switches = discover_plx_switches()
"""
    click.echo(banner)

    start_ipython(  # type: ignore[no-untyped-call]
        argv=[],
        user_ns={
            "plxtools": __import__("plxtools"),
        },
    )


# --- Serial commands ---


@main.group()
def serial() -> None:
    """Serial interface operations for PEX880xx switches."""
    pass


@serial.command("list")
@click.option("--probe", is_flag=True, help="Probe devices to get model info (slower)")
@click.pass_context
def serial_list(ctx: click.Context, probe: bool) -> None:
    """List PLX switches accessible via serial interface."""
    from plxtools.discovery import discover_serial_devices

    devices = discover_serial_devices(probe=probe)

    if ctx.obj["json"]:
        output = [
            {
                "device_path": d.device_path,
                "usb_vendor_id": f"0x{d.usb_vendor_id:04X}",
                "usb_product_id": f"0x{d.usb_product_id:04X}",
                "serial_number": d.serial_number,
                "model": d.model,
                "is_atlas": d.is_atlas,
            }
            for d in devices
        ]
        click.echo(json.dumps(output, indent=2))
    else:
        if not devices:
            click.echo("No PLX serial devices found.")
            return

        click.echo(f"Found {len(devices)} serial device(s):")
        click.echo()
        for device in devices:
            atlas_marker = " [ATLAS]" if device.is_atlas else ""
            model_str = f" ({device.model})" if device.model else ""
            click.echo(f"  {device.device_path}{model_str}{atlas_marker}")


@serial.command("info")
@click.argument("device")
@click.pass_context
def serial_info(ctx: click.Context, device: str) -> None:
    """Show version and environment info for a serial PLX device.

    DEVICE is the serial device path (e.g., /dev/ttyACM0).
    """
    from plxtools.backends.serial import SerialBackend

    try:
        with SerialBackend(device) as backend:
            ver_info = backend.get_version()
            env_info = backend.get_environment()

            if ctx.obj["json"]:
                result = {
                    "device": device,
                    "version": {
                        "serial_number": ver_info.serial_number,
                        "company": ver_info.company,
                        "model": ver_info.model,
                        "version": ver_info.version,
                        "build_date": ver_info.build_date,
                    },
                    "environment": {
                        "switch_temp_c": env_info.switch_temp_c,
                        "fan_rpm": env_info.fan_rpm,
                        "voltage_12v_mv": env_info.voltage_12v_mv,
                        "voltage_1v8_mv": env_info.voltage_1v8_mv,
                        "voltage_0v9_mv": env_info.voltage_0v9_mv,
                    },
                }
                click.echo(json.dumps(result, indent=2))
            else:
                click.echo(f"Device: {device}")
                click.echo()
                click.echo("Version Information:")
                click.echo(f"  Serial Number: {ver_info.serial_number}")
                click.echo(f"  Company:       {ver_info.company}")
                click.echo(f"  Model:         {ver_info.model}")
                click.echo(f"  Version:       {ver_info.version}")
                click.echo(f"  Build Date:    {ver_info.build_date}")
                click.echo()
                click.echo("Environment:")
                click.echo(f"  Temperature:   {env_info.switch_temp_c} C")
                click.echo(f"  Fan Speed:     {env_info.fan_rpm} RPM")
                click.echo(f"  12V Rail:      {env_info.voltage_12v_mv} mV")
                click.echo(f"  1.8V Rail:     {env_info.voltage_1v8_mv} mV")
                click.echo(f"  0.9V Rail:     {env_info.voltage_0v9_mv} mV")

    except FileNotFoundError:
        click.echo(f"Error: Device {device} not found", err=True)
        sys.exit(1)
    except PermissionError:
        click.echo(f"Error: Permission denied accessing {device}.", err=True)
        sys.exit(1)
    except OSError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@serial.command("ports")
@click.argument("device")
@click.pass_context
def serial_ports(ctx: click.Context, device: str) -> None:
    """Show PCIe port link status.

    DEVICE is the serial device path (e.g., /dev/ttyACM0).
    """
    from plxtools.backends.serial import SerialBackend

    try:
        with SerialBackend(device) as backend:
            ports = backend.get_port_status()

            if ctx.obj["json"]:
                output = [
                    {
                        "port": p.port,
                        "type": p.port_type,
                        "speed": p.speed,
                        "width": p.width,
                        "max_speed": p.max_speed,
                        "max_width": p.max_width,
                    }
                    for p in ports
                ]
                click.echo(json.dumps(output, indent=2))
            else:
                if not ports:
                    click.echo("No port information available.")
                    return

                # Print table header
                click.echo(f"{'Port':>4}  {'Type':<12}  {'Speed':<6}  {'Width':>5}  "
                          f"{'Max Speed':<9}  {'Max Width':>9}")
                click.echo("-" * 60)

                for p in ports:
                    click.echo(f"{p.port:>4}  {p.port_type:<12}  {p.speed:<6}  "
                              f"x{p.width:>4}  {p.max_speed:<9}  x{p.max_width:>8}")

    except FileNotFoundError:
        click.echo(f"Error: Device {device} not found", err=True)
        sys.exit(1)
    except PermissionError:
        click.echo(f"Error: Permission denied accessing {device}.", err=True)
        sys.exit(1)
    except OSError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@serial.command("read")
@click.argument("device")
@click.argument("offset", type=str)
@click.pass_context
def serial_read(ctx: click.Context, device: str, offset: str) -> None:
    """Read a single 32-bit register.

    DEVICE is the serial device path (e.g., /dev/ttyACM0).
    OFFSET is the register offset in hex (e.g., 0x60800000).
    """
    from plxtools.backends.serial import SerialBackend

    try:
        offset_int = int(offset, 0)  # Auto-detect base (0x prefix for hex)
    except ValueError:
        click.echo(f"Error: Invalid offset '{offset}'", err=True)
        sys.exit(1)

    try:
        with SerialBackend(device) as backend:
            value = backend.read32(offset_int)

            if ctx.obj["json"]:
                result = {
                    "offset": f"0x{offset_int:08X}",
                    "value": f"0x{value:08X}",
                }
                click.echo(json.dumps(result, indent=2))
            else:
                click.echo(f"{offset_int:08X}: {value:08X}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except FileNotFoundError:
        click.echo(f"Error: Device {device} not found", err=True)
        sys.exit(1)
    except PermissionError:
        click.echo(f"Error: Permission denied accessing {device}.", err=True)
        sys.exit(1)
    except OSError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@serial.command("dump")
@click.argument("device")
@click.argument("offset", type=str)
@click.argument("count", type=int, default=16)
@click.pass_context
def serial_dump(ctx: click.Context, device: str, offset: str, count: int) -> None:
    """Dump multiple 32-bit registers.

    DEVICE is the serial device path (e.g., /dev/ttyACM0).
    OFFSET is the starting register offset in hex.
    COUNT is the number of 32-bit words to read (default 16).
    """
    from plxtools.backends.serial import SerialBackend

    try:
        offset_int = int(offset, 0)
    except ValueError:
        click.echo(f"Error: Invalid offset '{offset}'", err=True)
        sys.exit(1)

    try:
        with SerialBackend(device) as backend:
            values: list[tuple[int, int]] = []
            for i in range(count):
                addr = offset_int + i * 4
                value = backend.read32(addr)
                values.append((addr, value))

            if ctx.obj["json"]:
                output = [
                    {"offset": f"0x{addr:08X}", "value": f"0x{val:08X}"}
                    for addr, val in values
                ]
                click.echo(json.dumps(output, indent=2))
            else:
                # Print 4 values per line
                for i in range(0, len(values), 4):
                    row = values[i:i + 4]
                    addr = row[0][0]
                    vals = " ".join(f"{v:08X}" for _, v in row)
                    click.echo(f"{addr:08X}: {vals}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except FileNotFoundError:
        click.echo(f"Error: Device {device} not found", err=True)
        sys.exit(1)
    except PermissionError:
        click.echo(f"Error: Permission denied accessing {device}.", err=True)
        sys.exit(1)
    except OSError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@serial.command("write")
@click.argument("device")
@click.argument("offset", type=str)
@click.argument("value", type=str)
@click.pass_context
def serial_write(ctx: click.Context, device: str, offset: str, value: str) -> None:
    """Write a 32-bit register.

    DEVICE is the serial device path (e.g., /dev/ttyACM0).
    OFFSET is the register offset in hex.
    VALUE is the 32-bit value to write in hex.
    """
    from plxtools.backends.serial import SerialBackend

    try:
        offset_int = int(offset, 0)
        value_int = int(value, 0)
    except ValueError:
        click.echo("Error: Invalid offset or value", err=True)
        sys.exit(1)

    try:
        with SerialBackend(device) as backend:
            backend.write32(offset_int, value_int)

            if ctx.obj["json"]:
                result = {
                    "offset": f"0x{offset_int:08X}",
                    "value": f"0x{value_int:08X}",
                    "status": "ok",
                }
                click.echo(json.dumps(result, indent=2))
            else:
                click.echo(f"Wrote 0x{value_int:08X} to 0x{offset_int:08X}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except FileNotFoundError:
        click.echo(f"Error: Device {device} not found", err=True)
        sys.exit(1)
    except PermissionError:
        click.echo(f"Error: Permission denied accessing {device}.", err=True)
        sys.exit(1)
    except OSError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@serial.command("i2c-scan")
@click.argument("device")
@click.pass_context
def serial_i2c_scan(ctx: click.Context, device: str) -> None:
    """Scan I2C bus for devices.

    DEVICE is the serial device path (e.g., /dev/ttyACM0).
    """
    from plxtools.backends.serial import SerialBackend

    try:
        with SerialBackend(device) as backend:
            addresses = backend.i2c_scan()

            if ctx.obj["json"]:
                output = {
                    "addresses": [f"0x{a:02X}" for a in addresses],
                    "count": len(addresses),
                }
                click.echo(json.dumps(output, indent=2))
            else:
                if not addresses:
                    click.echo("No I2C devices found.")
                    return

                click.echo(f"Found {len(addresses)} I2C device(s):")
                for addr in addresses:
                    click.echo(f"  0x{addr:02X}")

    except FileNotFoundError:
        click.echo(f"Error: Device {device} not found", err=True)
        sys.exit(1)
    except PermissionError:
        click.echo(f"Error: Permission denied accessing {device}.", err=True)
        sys.exit(1)
    except OSError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@serial.command("flash")
@click.argument("device")
@click.argument("offset", type=str)
@click.argument("count", type=str, default="0x100")
@click.option("-o", "--output", type=click.Path(), help="Output file path")
@click.pass_context
def serial_flash(
    ctx: click.Context,
    device: str,
    offset: str,
    count: str,
    output: str | None,
) -> None:
    """Read flash memory contents.

    DEVICE is the serial device path (e.g., /dev/ttyACM0).
    OFFSET is the flash address in hex.
    COUNT is the number of bytes to read (default 0x100).
    """
    from plxtools.backends.serial import SerialBackend

    try:
        offset_int = int(offset, 0)
        count_int = int(count, 0)
    except ValueError:
        click.echo("Error: Invalid offset or count", err=True)
        sys.exit(1)

    try:
        with SerialBackend(device) as backend:
            data = backend.read_flash(offset_int, count_int)

            if output:
                Path(output).write_bytes(data)
                click.echo(f"Read {len(data)} bytes to {output}")
            elif ctx.obj["json"]:
                result = {
                    "offset": f"0x{offset_int:08X}",
                    "size": len(data),
                    "data_hex": data.hex(),
                }
                click.echo(json.dumps(result, indent=2))
            else:
                # Hex dump format
                for i in range(0, len(data), 16):
                    row = data[i:i + 16]
                    hex_part = " ".join(f"{b:02x}" for b in row)
                    # Pad to full width if needed
                    hex_part = hex_part.ljust(47)
                    # ASCII representation
                    ascii_part = "".join(
                        chr(b) if 32 <= b < 127 else "." for b in row
                    )
                    click.echo(f"{offset_int + i:08x}: {hex_part}  |{ascii_part}|")

    except FileNotFoundError:
        click.echo(f"Error: Device {device} not found", err=True)
        sys.exit(1)
    except PermissionError:
        click.echo(f"Error: Permission denied accessing {device}.", err=True)
        sys.exit(1)
    except OSError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
