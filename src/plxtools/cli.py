"""Command-line interface for plxtools.

This module will be implemented in Phase 8.
"""

import click


@click.group()
@click.version_option()
def main() -> None:
    """PLX/PEX PCIe switch tools.

    Read and decode EEPROM contents from PLX switches via PCIe or I2C.
    """
    pass


@main.command()
def list() -> None:
    """List PLX switches in the system."""
    click.echo("CLI not yet fully implemented. Use the Python API directly.")
    click.echo()

    from plxtools.discovery import discover_plx_switches

    switches = discover_plx_switches()
    if not switches:
        click.echo("No PLX switches found.")
        return

    for device in switches:
        click.echo(f"{device.bdf}: {device.device_name} ({device.vendor_name})")


if __name__ == "__main__":
    main()
