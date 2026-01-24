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
        click.echo("Install with: pip install ipython", err=True)
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


if __name__ == "__main__":
    main()
