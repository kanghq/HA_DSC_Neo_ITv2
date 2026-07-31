"""Pure-Python DSC ITv2 protocol library.

Embedded in the HACS custom component but kept as a clean separate module
so it could be extracted to PyPI later if useful.
"""

from .commands import ACK_COMMANDS, Command, name_of
from .crc import append_crc, crc16_ccitt, verify_crc
from .packet import Packet, build_packet, parse_packet

__all__ = [
    "ACK_COMMANDS",
    "Command",
    "Packet",
    "append_crc",
    "build_packet",
    "crc16_ccitt",
    "name_of",
    "parse_packet",
    "verify_crc",
]
