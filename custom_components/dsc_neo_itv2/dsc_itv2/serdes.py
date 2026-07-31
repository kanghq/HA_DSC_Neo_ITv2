"""Wire-format primitives for ITv2 message bodies.

All readers take ``(data, offset)`` and return ``(value, new_offset)``.
Writers append to a ``bytearray``. Mirrors NeoHub's ``BinarySerializer``
and its helpers (``CompactIntegerSerializer``, ``StringSerializer``,
``ByteArraySerializer``, ``DateTimeSerializer``,
``MultipleMessagePacketSerializer``).

Sources:
  - NeoHub ``DSC.TLink.Serialization.*`` (GPL-3.0)
"""
from __future__ import annotations

import datetime as _dt

# ---------------------------------------------------------------------------
# Primitive integers
# ---------------------------------------------------------------------------


def read_u8(data: bytes, offset: int) -> tuple[int, int]:
    if offset >= len(data):
        raise ValueError("truncated u8")
    return data[offset], offset + 1


def write_u8(out: bytearray, value: int) -> None:
    if not 0 <= value <= 0xFF:
        raise ValueError(f"u8 out of range: {value}")
    out.append(value)


def read_u16_be(data: bytes, offset: int) -> tuple[int, int]:
    if offset + 2 > len(data):
        raise ValueError("truncated u16")
    return (data[offset] << 8) | data[offset + 1], offset + 2


def write_u16_be(out: bytearray, value: int) -> None:
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"u16 out of range: {value}")
    out.append((value >> 8) & 0xFF)
    out.append(value & 0xFF)


def read_u32_be(data: bytes, offset: int) -> tuple[int, int]:
    if offset + 4 > len(data):
        raise ValueError("truncated u32")
    v = (
        (data[offset] << 24)
        | (data[offset + 1] << 16)
        | (data[offset + 2] << 8)
        | data[offset + 3]
    )
    return v, offset + 4


def write_u32_be(out: bytearray, value: int) -> None:
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"u32 out of range: {value}")
    out.append((value >> 24) & 0xFF)
    out.append((value >> 16) & 0xFF)
    out.append((value >> 8) & 0xFF)
    out.append(value & 0xFF)


# ---------------------------------------------------------------------------
# Compact integer: [len:1][N significant bytes BE]
#
# Length 0 is never written (we always emit at least one byte for value 0,
# matching NeoHub's FindSignificantByteIndex which always keeps at least one).
# ---------------------------------------------------------------------------


def read_compact_int(data: bytes, offset: int) -> tuple[int, int]:
    if offset >= len(data):
        raise ValueError("truncated compact-int length")
    length = data[offset]
    offset += 1
    if offset + length > len(data):
        raise ValueError(
            f"truncated compact-int value (need {length}, have {len(data) - offset})"
        )
    value = 0
    for b in data[offset:offset + length]:
        value = (value << 8) | b
    return value, offset + length


def write_compact_int(out: bytearray, value: int) -> None:
    if value < 0:
        raise ValueError(f"compact-int does not encode negatives: {value}")
    if value == 0:
        out.append(1)
        out.append(0)
        return
    full_len = (value.bit_length() + 7) // 8
    out.append(full_len)
    for i in range(full_len - 1, -1, -1):
        out.append((value >> (i * 8)) & 0xFF)


# ---------------------------------------------------------------------------
# Fixed-length byte arrays
# ---------------------------------------------------------------------------


def read_fixed_bytes(data: bytes, offset: int, length: int) -> tuple[bytes, int]:
    if offset + length > len(data):
        raise ValueError(f"truncated fixed array (need {length}, have {len(data) - offset})")
    return bytes(data[offset:offset + length]), offset + length


def write_fixed_bytes(out: bytearray, value: bytes, length: int) -> None:
    """Write exactly ``length`` bytes, zero-padding or truncating ``value``."""
    if len(value) >= length:
        out.extend(value[:length])
    else:
        out.extend(value)
        out.extend(b"\x00" * (length - len(value)))


# ---------------------------------------------------------------------------
# Length-prefixed byte arrays
# ---------------------------------------------------------------------------


def read_leading_length_bytes(
    data: bytes, offset: int, length_prefix_bytes: int = 1
) -> tuple[bytes, int]:
    if length_prefix_bytes == 1:
        if offset >= len(data):
            raise ValueError("truncated 1-byte length prefix")
        length = data[offset]
        offset += 1
    elif length_prefix_bytes == 2:
        if offset + 2 > len(data):
            raise ValueError("truncated 2-byte length prefix")
        length = (data[offset] << 8) | data[offset + 1]
        offset += 2
    else:
        raise ValueError(f"length_prefix_bytes must be 1 or 2, got {length_prefix_bytes}")
    if offset + length > len(data):
        raise ValueError(
            f"length-prefixed array truncated (declared {length}, have {len(data) - offset})"
        )
    return bytes(data[offset:offset + length]), offset + length


def write_leading_length_bytes(
    out: bytearray, value: bytes, length_prefix_bytes: int = 1
) -> None:
    if length_prefix_bytes == 1:
        if len(value) > 0xFF:
            raise ValueError(f"array too long for 1-byte prefix: {len(value)}")
        out.append(len(value))
    elif length_prefix_bytes == 2:
        if len(value) > 0xFFFF:
            raise ValueError(f"array too long for 2-byte prefix: {len(value)}")
        out.append((len(value) >> 8) & 0xFF)
        out.append(len(value) & 0xFF)
    else:
        raise ValueError(f"length_prefix_bytes must be 1 or 2, got {length_prefix_bytes}")
    out.extend(value)


def read_unbounded_bytes(data: bytes, offset: int) -> tuple[bytes, int]:
    return bytes(data[offset:]), len(data)


# ---------------------------------------------------------------------------
# BCD strings (each byte = two nibbles -> two hex digits)
# ---------------------------------------------------------------------------


def _hex_nibble(c: str) -> int:
    if "0" <= c <= "9":
        return ord(c) - ord("0")
    if "A" <= c <= "F":
        return ord(c) - ord("A") + 10
    if "a" <= c <= "f":
        return ord(c) - ord("a") + 10
    raise ValueError(f"invalid BCD/hex digit '{c}'")


def write_bcd_fixed(out: bytearray, digits: str, byte_length: int) -> None:
    """Write ``byte_length`` BCD bytes. Pads or truncates ``digits``.

    Panel uses hex sentinels (``"AAAA"`` for disabled access codes), so we
    accept ``A-F`` in addition to ``0-9``.
    """
    padded = (digits or "").ljust(byte_length * 2, "0")[: byte_length * 2]
    for i in range(byte_length):
        hi = _hex_nibble(padded[i * 2])
        lo = _hex_nibble(padded[i * 2 + 1])
        out.append((hi << 4) | lo)


def read_bcd_fixed(data: bytes, offset: int, byte_length: int) -> tuple[str, int]:
    if offset + byte_length > len(data):
        raise ValueError(f"truncated BCD (need {byte_length}, have {len(data) - offset})")
    out: list[str] = []
    for i in range(byte_length):
        b = data[offset + i]
        out.append(format((b >> 4) & 0x0F, "X"))
        out.append(format(b & 0x0F, "X"))
    return "".join(out), offset + byte_length


def write_bcd_leading_length(out: bytearray, digits: str) -> None:
    """Write ``[byte-length][BCD bytes]``. Odd-length digits get a trailing ``'0'``."""
    d = digits or ""
    if len(d) % 2 != 0:
        d += "0"
    byte_len = len(d) // 2
    if byte_len > 0xFF:
        raise ValueError(f"BCD too long for 1-byte prefix: {byte_len} bytes")
    out.append(byte_len)
    write_bcd_fixed(out, d, byte_len)


def read_bcd_leading_length(data: bytes, offset: int) -> tuple[str, int]:
    if offset >= len(data):
        raise ValueError("truncated BCD length prefix")
    byte_len = data[offset]
    offset += 1
    return read_bcd_fixed(data, offset, byte_len)


def write_bcd_array_leading_length(out: bytearray, items: list[str]) -> None:
    """Write ``[byte-length][BCD1][BCD2]...``: one shared length, N items packed."""
    if not items:
        out.append(0)
        return
    max_digits = max(len(s or "") for s in items)
    byte_len = (max_digits + 1) // 2
    if byte_len > 0xFF:
        raise ValueError(f"BCD element too long for 1-byte prefix: {byte_len} bytes")
    out.append(byte_len)
    for s in items:
        write_bcd_fixed(out, s, byte_len)


def read_bcd_array_leading_length(data: bytes, offset: int) -> tuple[list[str], int]:
    """Read ``[byte-length][BCD]*``: fills to end of buffer."""
    if offset >= len(data):
        raise ValueError("truncated BCD array length prefix")
    byte_len = data[offset]
    offset += 1
    if byte_len == 0:
        return [], offset
    items: list[str] = []
    while offset + byte_len <= len(data):
        s, offset = read_bcd_fixed(data, offset, byte_len)
        items.append(s)
    return items, offset


# ---------------------------------------------------------------------------
# Unicode (UTF-16 big-endian) strings
# ---------------------------------------------------------------------------


def write_unicode_string(out: bytearray, s: str, length_prefix_bytes: int = 1) -> None:
    encoded = (s or "").encode("utf-16-be")
    write_leading_length_bytes(out, encoded, length_prefix_bytes)


def read_unicode_string(
    data: bytes, offset: int, length_prefix_bytes: int = 1
) -> tuple[str, int]:
    encoded, offset = read_leading_length_bytes(data, offset, length_prefix_bytes)
    return encoded.decode("utf-16-be"), offset


def write_fixed_unicode_string_array(out: bytearray, items: list[str]) -> None:
    """Write ``[CompactInt: byte-width][UTF-16BE x N (padded)]``.

    Byte-width is computed as the max UTF-16BE byte length over ``items``.
    """
    if not items:
        write_compact_int(out, 0)
        return
    fixed_len = max(len((s or "").encode("utf-16-be")) for s in items)
    write_compact_int(out, fixed_len)
    for s in items:
        encoded = (s or "").encode("utf-16-be")
        out.extend(encoded)
        if len(encoded) < fixed_len:
            out.extend(b"\x00" * (fixed_len - len(encoded)))


def read_fixed_unicode_string_array(data: bytes, offset: int) -> tuple[list[str], int]:
    """Inverse of :func:`write_fixed_unicode_string_array`. Consumes to end of buffer."""
    fixed_len, offset = read_compact_int(data, offset)
    items: list[str] = []
    if fixed_len == 0:
        return items, offset
    while offset + fixed_len <= len(data):
        chunk = data[offset:offset + fixed_len]
        offset += fixed_len
        items.append(chunk.decode("utf-16-be").rstrip("\x00"))
    return items, offset


def write_unicode_string_array(
    out: bytearray, items: list[str], length_prefix_bytes: int = 1
) -> None:
    """Write a sequence of length-prefixed UTF-16BE strings (no outer count)."""
    for s in items or []:
        write_unicode_string(out, s, length_prefix_bytes)


def read_unicode_string_array(
    data: bytes, offset: int, length_prefix_bytes: int = 1
) -> tuple[list[str], int]:
    items: list[str] = []
    while offset < len(data):
        s, offset = read_unicode_string(data, offset, length_prefix_bytes)
        items.append(s)
    return items, offset


# ---------------------------------------------------------------------------
# Packed DateTime (32 bits)
#
#   bits 31-27 (5): hour
#   bits 26-21 (6): minute
#   bits 20-15 (6): second
#   bits 14-9  (6): year - 2000
#   bits 8-5   (4): month
#   bits 4-0   (5): day
# ---------------------------------------------------------------------------


def write_packed_datetime(out: bytearray, dt: _dt.datetime) -> None:
    if not 2000 <= dt.year <= 2063:
        raise ValueError(f"DSC packed DateTime year out of range: {dt.year}")
    packed = 0
    packed |= (dt.hour & 0x1F) << 27
    packed |= (dt.minute & 0x3F) << 21
    packed |= (dt.second & 0x3F) << 15
    packed |= ((dt.year - 2000) & 0x3F) << 9
    packed |= (dt.month & 0x0F) << 5
    packed |= (dt.day & 0x1F)
    write_u32_be(out, packed)


def read_packed_datetime(data: bytes, offset: int) -> tuple[_dt.datetime, int]:
    packed, offset = read_u32_be(data, offset)
    hour = (packed >> 27) & 0x1F
    minute = (packed >> 21) & 0x3F
    second = (packed >> 15) & 0x3F
    year = ((packed >> 9) & 0x3F) + 2000
    month = (packed >> 5) & 0x0F
    day = packed & 0x1F
    return _dt.datetime(year, month, day, hour, minute, second), offset


# ---------------------------------------------------------------------------
# MultipleMessagePacket length prefix (variable: 1 or 2 bytes, MSB flag)
#
# Same encoding as ITv2 framing length prefix.
# ---------------------------------------------------------------------------


def write_variable_length_prefix(out: bytearray, length: int) -> None:
    if length > 0x7FFF:
        raise ValueError(f"variable-length prefix max is 0x7FFF, got {length}")
    if length > 0x7F:
        out.append(((length >> 8) | 0x80) & 0xFF)
        out.append(length & 0xFF)
    else:
        out.append(length & 0xFF)


def read_variable_length_prefix(data: bytes, offset: int) -> tuple[int, int]:
    if offset >= len(data):
        raise ValueError("truncated variable length prefix")
    first = data[offset]
    offset += 1
    if first & 0x80:
        if offset >= len(data):
            raise ValueError("truncated 2-byte variable length prefix")
        second = data[offset]
        offset += 1
        return ((first & 0x7F) << 8) | second, offset
    return first, offset
