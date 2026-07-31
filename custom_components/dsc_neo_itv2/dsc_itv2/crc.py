"""CRC-16-CCITT for DSC ITv2 transport framing.

OEM-authoritative: algorithm extracted from
`Tyco.TSP.Communications.ITV2.ITV2TransportInstructionHelper`
(decompiled from `Tyco.TSP.Communications.TLink.dll`).

Parameters:
  - Polynomial: 0x1021
  - Initial value: 0xFFFF
  - Bit processing: MSB-first (top bit examined first via b2 = 128 -> b2 >>= 1)
  - No XOR-out (returned as-is)
  - Stored in frame: 2 bytes, big-endian (HI byte first, LO byte second)

This matches what is often called CRC-16-CCITT (False) or CRC-16-IBM-3740.
"""

from __future__ import annotations


def crc16_ccitt(data: bytes | bytearray | memoryview, length: int | None = None) -> int:
    """Compute CRC-16-CCITT over `data[:length]`, defaulting to all of `data`."""
    if length is None:
        length = len(data)
    crc = 0xFFFF
    for i in range(length):
        b = data[i]
        bit_mask = 0x80
        while bit_mask:
            top = crc & 0x8000
            crc = (crc << 1) & 0xFFFF
            if b & bit_mask:
                top ^= 0x8000
            if top:
                crc ^= 0x1021
            bit_mask >>= 1
    return crc


def append_crc(buffer: bytearray) -> None:
    """Append the 2-byte big-endian CRC of `buffer` to the buffer.

    Mirrors `ITV2TransportInstructionHelper.AddCRC(List<byte>)`.
    """
    crc = crc16_ccitt(buffer, len(buffer))
    buffer.append((crc & 0xFF00) >> 8)
    buffer.append(crc & 0xFF)


def verify_crc(buffer: bytes | bytearray | memoryview) -> bool:
    """Verify the trailing 2-byte big-endian CRC on `buffer`.

    Mirrors `ITV2TransportInstructionHelper.IsCRCValid(List<byte>)`.
    Returns True iff the computed CRC over `buffer[:-2]` equals
    the value encoded in `buffer[-2:]`.
    """
    if len(buffer) < 2:
        return False
    expected = (buffer[-2] << 8) | buffer[-1]
    actual = crc16_ccitt(buffer, len(buffer) - 2)
    return expected == actual
