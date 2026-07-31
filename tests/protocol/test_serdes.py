"""Wire-format primitives (serdes.py)."""

from __future__ import annotations

import datetime as dt

from dsc_itv2.serdes import (
    read_bcd_array_leading_length,
    read_bcd_fixed,
    read_bcd_leading_length,
    read_compact_int,
    read_fixed_bytes,
    read_fixed_unicode_string_array,
    read_leading_length_bytes,
    read_packed_datetime,
    read_u8,
    read_u16_be,
    read_u32_be,
    read_unbounded_bytes,
    read_unicode_string,
    read_unicode_string_array,
    read_variable_length_prefix,
    write_bcd_array_leading_length,
    write_bcd_fixed,
    write_bcd_leading_length,
    write_compact_int,
    write_fixed_bytes,
    write_fixed_unicode_string_array,
    write_leading_length_bytes,
    write_packed_datetime,
    write_u8,
    write_u16_be,
    write_u32_be,
    write_unicode_string,
    write_unicode_string_array,
    write_variable_length_prefix,
)
import pytest


def _w(fn, *args):
    """Run a writer and return the produced bytes."""
    out = bytearray()
    fn(out, *args)
    return bytes(out)


# --------------------------------------------------------------------------
# Fixed-width integers
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 1, 127, 128, 255])
def test_u8_roundtrip(value):
    assert read_u8(_w(write_u8, value), 0) == (value, 1)


@pytest.mark.parametrize("value", [0, 1, 0x00FF, 0xFF00, 0xFFFF])
def test_u16_be_roundtrip(value):
    assert read_u16_be(_w(write_u16_be, value), 0) == (value, 2)


def test_u16_is_big_endian():
    assert _w(write_u16_be, 0x1234) == b"\x12\x34"


@pytest.mark.parametrize("value", [0, 1, 0xDEADBEEF, 0xFFFFFFFF])
def test_u32_be_roundtrip(value):
    assert read_u32_be(_w(write_u32_be, value), 0) == (value, 4)


def test_u32_is_big_endian():
    assert _w(write_u32_be, 0x12345678) == b"\x12\x34\x56\x78"


def test_readers_honour_the_offset():
    data = b"\xff\x12\x34"
    assert read_u16_be(data, 1) == (0x1234, 3)


@pytest.mark.parametrize(
    ("writer", "value"),
    [
        (write_u8, -1),
        (write_u8, 256),
        (write_u16_be, -1),
        (write_u16_be, 0x10000),
        (write_u32_be, -1),
        (write_u32_be, 0x1_0000_0000),
    ],
)
def test_integer_writers_reject_out_of_range_values(writer, value):
    with pytest.raises(ValueError, match="out of range"):
        _w(writer, value)


@pytest.mark.parametrize(
    ("reader", "data"),
    [
        (read_u8, b""),
        (read_u16_be, b"\x00"),
        (read_u32_be, b"\x00\x00\x00"),
    ],
)
def test_integer_readers_reject_truncated_input(reader, data):
    with pytest.raises(ValueError, match="truncated"):
        reader(data, 0)


# --------------------------------------------------------------------------
# Compact integers
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 1, 255, 256, 0xFFFF, 0x010000, 2**32 - 1])
def test_compact_int_roundtrip(value):
    encoded = _w(write_compact_int, value)
    assert read_compact_int(encoded, 0) == (value, len(encoded))


def test_compact_int_zero_uses_a_single_significant_byte():
    assert _w(write_compact_int, 0) == b"\x01\x00"


def test_compact_int_drops_leading_zero_bytes():
    assert _w(write_compact_int, 0x0102) == b"\x02\x01\x02"


def test_compact_int_rejects_negatives():
    with pytest.raises(ValueError, match="negatives"):
        _w(write_compact_int, -1)


def test_compact_int_rejects_a_truncated_length():
    with pytest.raises(ValueError, match="truncated compact-int length"):
        read_compact_int(b"", 0)


def test_compact_int_rejects_a_truncated_value():
    with pytest.raises(ValueError, match="truncated compact-int value"):
        read_compact_int(b"\x04\x01", 0)


# --------------------------------------------------------------------------
# Byte arrays
# --------------------------------------------------------------------------


def test_fixed_bytes_roundtrip():
    assert read_fixed_bytes(_w(write_fixed_bytes, b"\x01\x02\x03", 3), 0, 3) == (
        b"\x01\x02\x03",
        3,
    )


def test_fixed_bytes_zero_pads_short_values():
    assert _w(write_fixed_bytes, b"\x01", 4) == b"\x01\x00\x00\x00"


def test_fixed_bytes_truncates_long_values():
    assert _w(write_fixed_bytes, b"\x01\x02\x03\x04", 2) == b"\x01\x02"


def test_fixed_bytes_rejects_truncated_input():
    with pytest.raises(ValueError, match="truncated fixed array"):
        read_fixed_bytes(b"\x01", 0, 4)


@pytest.mark.parametrize("prefix_len", [1, 2])
@pytest.mark.parametrize("value", [b"", b"\x01", b"\xaa" * 200])
def test_leading_length_bytes_roundtrip(prefix_len, value):
    encoded = _w(write_leading_length_bytes, value, prefix_len)
    assert read_leading_length_bytes(encoded, 0, prefix_len) == (value, len(encoded))


def test_leading_length_rejects_oversized_values():
    with pytest.raises(ValueError, match="too long for 1-byte prefix"):
        _w(write_leading_length_bytes, b"\x00" * 256, 1)


def test_leading_length_bytes_rejects_a_truncated_body():
    with pytest.raises(ValueError, match="truncated"):
        read_leading_length_bytes(b"\x04\x01", 0, 1)


def test_unbounded_bytes_consumes_the_remainder():
    assert read_unbounded_bytes(b"\x00\x01\x02\x03", 2) == (b"\x02\x03", 4)


def test_unbounded_bytes_at_the_end_returns_empty():
    assert read_unbounded_bytes(b"\x00", 1) == (b"", 1)


# --------------------------------------------------------------------------
# BCD strings
# --------------------------------------------------------------------------


def test_bcd_fixed_packs_two_nibbles_per_byte():
    assert _w(write_bcd_fixed, "1234", 2) == b"\x12\x34"


@pytest.mark.parametrize("digits", ["1234", "0000", "ABCD", "9999"])
def test_bcd_fixed_roundtrip(digits):
    assert read_bcd_fixed(_w(write_bcd_fixed, digits, 2), 0, 2) == (digits, 2)


def test_bcd_fixed_reads_back_uppercase():
    assert read_bcd_fixed(_w(write_bcd_fixed, "abcd", 2), 0, 2)[0] == "ABCD"


def test_bcd_fixed_rejects_non_hex_digits():
    with pytest.raises(ValueError, match="invalid BCD/hex digit"):
        _w(write_bcd_fixed, "12X4", 2)


def test_bcd_fixed_rejects_truncated_input():
    with pytest.raises(ValueError, match="truncated BCD"):
        read_bcd_fixed(b"\x12", 0, 4)


@pytest.mark.parametrize("digits", ["", "12", "1234", "123456"])
def test_bcd_leading_length_roundtrip(digits):
    encoded = _w(write_bcd_leading_length, digits)
    assert read_bcd_leading_length(encoded, 0) == (digits, len(encoded))


def test_bcd_leading_length_pads_an_odd_digit_count():
    value, _ = read_bcd_leading_length(_w(write_bcd_leading_length, "123"), 0)
    assert value in {"1230", "0123"}
    assert len(value) == 4


def test_bcd_leading_length_rejects_a_truncated_prefix():
    with pytest.raises(ValueError, match="truncated BCD length prefix"):
        read_bcd_leading_length(b"", 0)


def test_bcd_array_roundtrip():
    items = ["1234", "5678", "9999"]
    encoded = _w(write_bcd_array_leading_length, items)
    assert read_bcd_array_leading_length(encoded, 0) == (items, len(encoded))


def test_bcd_array_rejects_a_truncated_prefix():
    with pytest.raises(ValueError, match="truncated BCD array length prefix"):
        read_bcd_array_leading_length(b"", 0)


# --------------------------------------------------------------------------
# UTF-16BE strings
# --------------------------------------------------------------------------


def test_unicode_string_is_utf16_big_endian():
    assert _w(write_unicode_string, "AB", 1) == b"\x04\x00A\x00B"


@pytest.mark.parametrize("prefix_len", [1, 2])
@pytest.mark.parametrize("text", ["", "Front Door", "Küche", "车库", "a" * 100])
def test_unicode_string_roundtrip(prefix_len, text):
    encoded = _w(write_unicode_string, text, prefix_len)
    assert read_unicode_string(encoded, 0, prefix_len) == (text, len(encoded))


@pytest.mark.parametrize(
    "items", [[], ["Front Door"], ["Front Door", "Back Door", "Garage"]]
)
def test_fixed_unicode_string_array_roundtrip(items):
    encoded = _w(write_fixed_unicode_string_array, items)
    decoded, offset = read_fixed_unicode_string_array(encoded, 0)
    assert list(decoded) == items
    assert offset == len(encoded)


def test_fixed_unicode_string_array_strips_null_padding():
    items = ["A", "Longer label"]
    decoded, _ = read_fixed_unicode_string_array(
        _w(write_fixed_unicode_string_array, items), 0
    )
    assert list(decoded) == items


@pytest.mark.parametrize("prefix_len", [1, 2])
def test_unicode_string_array_roundtrip(prefix_len):
    items = ["Zone 1", "Zone 2", ""]
    encoded = _w(write_unicode_string_array, items, prefix_len)
    decoded, offset = read_unicode_string_array(encoded, 0, prefix_len)
    assert list(decoded) == items
    assert offset == len(encoded)


# --------------------------------------------------------------------------
# Packed date/time
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "when",
    [
        dt.datetime(2000, 1, 1, 0, 0, 0),
        dt.datetime(2024, 6, 15, 13, 45, 30),
        dt.datetime(2063, 12, 31, 23, 59, 59),
    ],
)
def test_packed_datetime_roundtrip(when):
    encoded = _w(write_packed_datetime, when)
    assert len(encoded) == 4
    assert read_packed_datetime(encoded, 0) == (when, 4)


def test_packed_datetime_discards_sub_second_precision():
    when = dt.datetime(2024, 6, 15, 13, 45, 30, 123456)
    decoded, _ = read_packed_datetime(_w(write_packed_datetime, when), 0)
    assert decoded == when.replace(microsecond=0)


@pytest.mark.parametrize("year", [1999, 2064])
def test_packed_datetime_rejects_out_of_range_years(year):
    with pytest.raises(ValueError, match="year out of range"):
        _w(write_packed_datetime, dt.datetime(year, 1, 1))


def test_packed_datetime_rejects_truncated_input():
    with pytest.raises(ValueError, match="truncated"):
        read_packed_datetime(b"\x00\x00", 0)


# --------------------------------------------------------------------------
# Variable-length prefix
# --------------------------------------------------------------------------


@pytest.mark.parametrize("length", [0, 1, 0x7E, 0x7F, 0x80, 0x1234, 0x7FFF])
def test_variable_length_prefix_roundtrip(length):
    encoded = _w(write_variable_length_prefix, length)
    assert read_variable_length_prefix(encoded, 0) == (length, len(encoded))


def test_variable_length_prefix_uses_one_byte_up_to_0x7f():
    assert len(_w(write_variable_length_prefix, 0x7F)) == 1


def test_variable_length_prefix_uses_two_bytes_above_0x7f():
    assert len(_w(write_variable_length_prefix, 0x80)) == 2


def test_variable_length_prefix_rejects_oversized_lengths():
    with pytest.raises(ValueError, match="0x7FFF"):
        _w(write_variable_length_prefix, 0x8000)


def test_variable_length_prefix_rejects_truncated_input():
    with pytest.raises(ValueError, match="truncated"):
        read_variable_length_prefix(b"", 0)
