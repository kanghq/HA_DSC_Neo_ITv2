"""ITv2 inner framing (length-prefix + CRC).

Lives inside a :mod:`tlink_framing` payload region. Adds a length
prefix and a CRC-16-CCITT trailer so the receiver can validate the
encrypted blob it just AES-decrypted (trailing zero-padding bytes from
the cipher are ignored by the length field).

Wire layout:

    <length-prefix> <packet bytes> <crc16 BE>

Length prefix (per NeoHub ``ITv2Framing.AddFraming``):
  * ``length == len(packet) + 2``  (the +2 covers the CRC trailer)
  * If ``length <= 0x7F``: one byte ``length``.
  * If ``length  > 0x7F``: two bytes, first byte ``(length>>8) | 0x80``,
    second byte ``length & 0xFF``.

CRC: CRC-16-CCITT (poly 0x1021, init 0xFFFF) computed over the length
bytes followed by the packet bytes, appended big-endian.

Source: NeoHub ``ITv2Framing.AddFraming`` / ``RemoveFraming``
(GPL-3.0), verified against DLS5 ``ITV2TransportInstructionHelper``.
"""
from __future__ import annotations

from dataclasses import dataclass

from .crc import crc16_ccitt

MAX_SINGLE_BYTE_LEN: int = 0x7F
LEN_TWO_BYTE_FLAG: int = 0x80
MAX_LEN: int = 0x7FFF  # 15 bits available when 2-byte form is used


def add_framing(packet: bytes) -> bytes:
    """Wrap ``packet`` with length prefix and CRC trailer."""
    length = len(packet) + 2  # +2 for CRC bytes
    if length > MAX_LEN:
        raise ValueError(f"packet too large for ITv2 framing: length={length}")

    if length <= MAX_SINGLE_BYTE_LEN:
        len_bytes = bytes([length])
    else:
        len_bytes = bytes([(length >> 8) | LEN_TWO_BYTE_FLAG, length & 0xFF])

    crc_input = len_bytes + packet
    crc = crc16_ccitt(crc_input, len(crc_input))
    return crc_input + bytes([(crc >> 8) & 0xFF, crc & 0xFF])


@dataclass(frozen=True)
class ITv2Frame:
    """A removed-framing ITv2 packet body."""
    packet: bytes        # bytes between the length prefix and the CRC
    consumed: int        # how many bytes of the source were consumed


def remove_framing(data: bytes) -> ITv2Frame:
    """Strip length prefix + CRC. Validates CRC.

    ``data`` may contain trailing bytes (e.g., AES zero-padding); only
    the bytes covered by the length prefix are inspected. The CRC is
    computed over the length bytes + packet, matching ``add_framing``.

    Raises ValueError on:
      * truncated input
      * length-prefix overruns ``data``
      * CRC mismatch
    """
    if not data:
        raise ValueError("empty input to remove_framing")

    b0 = data[0]
    if b0 & LEN_TWO_BYTE_FLAG:
        if len(data) < 2:
            raise ValueError("truncated 2-byte length prefix")
        length = ((b0 & 0x7F) << 8) | data[1]
        len_bytes = bytes(data[:2])
        body_offset = 2
    else:
        length = b0
        len_bytes = bytes(data[:1])
        body_offset = 1

    if length < 2:
        raise ValueError(f"ITv2 length {length} too small (must include 2 CRC bytes)")

    total_needed = body_offset + (length - 2) + 2  # prefix + packet + crc
    if len(data) < total_needed:
        raise ValueError(
            f"ITv2 frame truncated: declared length {length} needs {total_needed} bytes, have {len(data)}"
        )

    packet_end = body_offset + (length - 2)
    packet = bytes(data[body_offset:packet_end])
    crc_expected = (data[packet_end] << 8) | data[packet_end + 1]

    crc_input = len_bytes + packet
    crc_actual = crc16_ccitt(crc_input, len(crc_input))
    if crc_actual != crc_expected:
        raise ValueError(
            f"ITv2 CRC mismatch: expected 0x{crc_expected:04X}, got 0x{crc_actual:04X}"
        )

    return ITv2Frame(packet=packet, consumed=total_needed)
