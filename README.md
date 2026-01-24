# plxtools

A Python tool for reconfiguring and controlling PLX/PEX PCIe switching ICs from Broadcom (formerly PLX Technology / Avago).

## Goals

### Long-term Goals

1. **PCIe Lane Bifurcation**: Enable runtime and EEPROM-based reconfiguration of PCIe slot lane assignments (e.g., split x16 into 4x4 for NVMe adapters)
2. **Port Configuration**: Modify port modes (Upstream, Downstream, Non-Transparent Bridge), enable/disable ports, adjust link parameters
3. **Dell C410x Support**: Enable reconfiguration of Dell PowerEdge C410x GPU expansion chassis, which uses PLX switches to provide 2:1, 4:1, and 8:1 fan-out configurations between up to 8 host servers and 16 GPU slots
4. **Hardware Recovery**: Provide I2C-based access for recovering switches with corrupted EEPROMs that prevent PCIe enumeration

### MVP Scope

Read-only EEPROM dump and decode for PEX8733 and PEX8696 via both PCIe and I2C.

## Supported Devices

- PEX8733 - 32-lane, 8-port PCIe Gen3 switch
- PEX8696 - 96-lane, 24-port PCIe Gen3 switch

## Installation

```bash
# Using uv (recommended)
uv pip install plxtools

# From source
git clone https://github.com/mithro/plxtools.git
cd plxtools
uv pip install -e ".[dev]"
```

## Usage

```bash
# List PLX switches in the system
plxtool list

# Read EEPROM from a switch
plxtool eeprom read 0000:03:00.0 -o switch.bin

# Decode EEPROM contents
plxtool eeprom decode switch.bin

# JSON output
plxtool --json list
```

## Access Methods

### PCIe (sysfs/mmap)

Access switches through the Linux PCIe subsystem. Requires root or appropriate permissions on `/sys/bus/pci/devices/*/config` and `/dev/mem` or `/sys/bus/pci/devices/*/resource0`.

### I2C

Access switches via I2C/SMBus interface. Useful for:
- Switches not enumerated on PCIe bus (corrupted EEPROM)
- Remote management scenarios
- Pre-boot configuration

## Development

```bash
# Clone and install dev dependencies
git clone https://github.com/mithro/plxtools.git
cd plxtools
uv pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/plxtools

# Linting
ruff check src/plxtools
```

## References

- [Broadcom PEX8733 Product Page](https://www.broadcom.com/products/pcie-switches-retimers/pcie-switches/pex8733)
- [PLX EEPROM Blog Post](https://billauer.co.il/blog/2015/10/linux-plx-avago-pcie-switch-eeprom/) - Practical EEPROM access examples
- [OCP pcicrawler](https://github.com/opencomputeproject/ocp-diag-pcicrawler) - Python PCIe tool reference

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.
