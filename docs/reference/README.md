# Reference Documentation

This directory contains archived reference materials for PLX/PEX PCIe switch development.

## Datasheets and Design Notes

These documents require registration at Broadcom's documentation portal:

| Document | Description | Source |
|----------|-------------|--------|
| PEX8733 Data Book | Register map, EEPROM format for 32-lane switch | [Broadcom Docs](https://www.broadcom.com/products/pcie-switches-retimers/pcie-switches/pex8733) |
| PEX8696 Data Book | Register map, EEPROM format for 96-lane switch | [Broadcom Docs](https://www.broadcom.com/products/pcie-switches-retimers/pcie-switches/pex8696) |
| PEX 85xx EEPROM Design Note | EEPROM format and programming reference | [Broadcom](https://docs.broadcom.com/doc/PEX_8518_8517_8512_8508_EEPROM_Design_Note_v1_1_09Jul07) |

## SDK and Code References

| Resource | Description | Source |
|----------|-------------|--------|
| Broadcom PCI/PCIe SDK | Official SDK (registration required) | [Broadcom](https://www.broadcom.com/products/pcie-switches-retimers/software-dev-kits) |
| PLX SDK GitHub Mirror | Community mirror of PLX SDK source | [GitHub](https://github.com/xiallc/broadcom_pci_pcie_sdk) |

## Online Resources

### EEPROM Access

- [PLX EEPROM Blog Post](https://billauer.co.il/blog/2015/10/linux-plx-avago-pcie-switch-eeprom/) - Eli Billauer's practical guide to reading PLX switch EEPROM via PCIe BAR0 registers

Key technical details from the blog:
- EEPROM control register: offset `0x260` (via BAR0 mmap)
- EEPROM data register: offset `0x264`
- Read command: `(addr & 0x1fff) | 0x00a06000`
- Address width auto-detected via signature byte `0x5a` at offset 0

### Python PCIe Tools

- [OCP pcicrawler](https://github.com/opencomputeproject/ocp-diag-pcicrawler) - Open Compute Project's Python PCIe enumeration tool, useful reference for sysfs access patterns

## EEPROM Format

PLX EEPROM uses a little-endian format:

```
Offset  Size  Description
0x00    1     Signature (0x5a)
0x01    1     Reserved (0x00)
0x02    2     Payload length in bytes (num_writes * 6)
0x04    N*6   Register write entries

Each register write entry (6 bytes):
  Offset  Size  Description
  0x00    2     Register address: (reg_addr >> 2) | (port << 10)
  0x02    4     32-bit value to write
```

The EEPROM contents are loaded by the switch hardware at power-on to configure port modes, lane assignments, and other parameters.
