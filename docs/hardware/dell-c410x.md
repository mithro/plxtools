# Dell PowerEdge C410x GPU Expansion Chassis

The Dell PowerEdge C410x is a 3U GPU expansion chassis that uses PLX switches to provide PCIe connectivity between multiple host servers and GPU cards.

## Overview

- **Form Factor**: 3U rack chassis
- **GPU Slots**: 16 full-length, full-height PCIe x16 slots
- **Host Connections**: Up to 8 host servers via Host Interface Cards (HICs)
- **Fan-out Configurations**: 2:1, 4:1, and 8:1 GPU-to-host ratios

## Architecture

The C410x uses PLX PCIe switches on the Host Interface Cards (HICs) to provide flexible fan-out between hosts and GPUs:

### Fan-out Modes

| Mode | Hosts | GPUs per Host | HICs Required |
|------|-------|---------------|---------------|
| 2:1  | 8     | 2             | 8             |
| 4:1  | 4     | 4             | 4             |
| 8:1  | 2     | 8             | 2             |

### PLX Switch Usage

Each HIC contains a PLX switch that handles:
- Upstream port connected to host server
- Downstream ports connected to GPU backplane
- Lane bifurcation for different fan-out modes

## Documentation

- [Dell C410x Technical Guide](https://i.dell.com/sites/csdocuments/Shared-Content_data-Sheets_Documents/en/uk/Dell_PowerEdge_C410x_Technical_Guide.pdf)
- [Dell C410x Hardware Owner's Manual](https://dl.dell.com/manuals/all-products/esuprt_ser_stor_net/esuprt_cloud_products/poweredge-c410x_owner's%20manual_en-us.pdf)

## Use Cases for plxtools

### Reconfiguration

The C410x HICs can potentially be reconfigured to:
- Change fan-out ratio without swapping HICs
- Adjust lane width per GPU slot
- Enable/disable individual downstream ports

### Recovery

If a HIC's EEPROM becomes corrupted:
- The PLX switch may fail to enumerate on PCIe
- I2C access can be used to reprogram the EEPROM
- plxtools can help diagnose and recover from this state

## Hardware Notes

- The exact PLX switch model on C410x HICs needs to be verified
- HICs connect to host servers via proprietary cable
- GPU slots are standard PCIe x16 physical, x16 electrical

## Future Work

- Identify exact PLX switch models used on HICs
- Document I2C bus topology for HIC access
- Create EEPROM profiles for different fan-out modes
- Test reconfiguration procedures on actual hardware
