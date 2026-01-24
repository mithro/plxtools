"""EEPROM operations for PLX switches."""

from plxtools.eeprom.controller import EepromController, EepromInfo, read_eeprom
from plxtools.eeprom.decoder import (
    EepromContents,
    EepromDecoder,
    RegisterWrite,
    decode_eeprom,
    decode_eeprom_file,
)

__all__ = [
    "EepromContents",
    "EepromController",
    "EepromDecoder",
    "EepromInfo",
    "RegisterWrite",
    "decode_eeprom",
    "decode_eeprom_file",
    "read_eeprom",
]
