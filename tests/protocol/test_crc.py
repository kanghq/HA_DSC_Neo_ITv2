"""CRC-16-CCITT (False): poly 0x1021, init 0xFFFF, no final XOR."""

from __future__ import annotations

from dsc_itv2.crc import append_crc, crc16_ccitt, verify_crc
import pytest


def test_check_value():
    """The canonical CRC-16-CCITT (False) check value for "123456789"."""
    assert crc16_ccitt(b"123456789") == 0x29B1


def test_empty_input_is_init_value():
    assert crc16_ccitt(b"") == 0xFFFF


@pytest.mark.parametrize("data", [b"\x00", b"\xff", b"\x00" * 16, bytes(range(256))])
def test_result_is_16_bit(data):
    assert 0 <= crc16_ccitt(data) <= 0xFFFF


def test_length_argument_limits_coverage():
    payload = b"123456789" + b"garbage"
    assert crc16_ccitt(payload, 9) == 0x29B1


def test_accepts_bytearray_and_memoryview():
    assert crc16_ccitt(bytearray(b"123456789")) == 0x29B1
    assert crc16_ccitt(memoryview(b"123456789")) == 0x29B1


def test_append_crc_is_big_endian():
    buf = bytearray(b"123456789")
    append_crc(buf)
    assert bytes(buf) == b"123456789" + b"\x29\xb1"


def test_append_then_verify_roundtrip():
    for payload in (b"", b"\x00", b"hello world", bytes(range(64))):
        buf = bytearray(payload)
        append_crc(buf)
        assert verify_crc(bytes(buf))


def test_verify_detects_payload_corruption():
    buf = bytearray(b"hello world")
    append_crc(buf)
    buf[0] ^= 0x01
    assert not verify_crc(bytes(buf))


def test_verify_detects_crc_corruption():
    buf = bytearray(b"hello world")
    append_crc(buf)
    buf[-1] ^= 0xFF
    assert not verify_crc(bytes(buf))


@pytest.mark.parametrize("short", [b"", b"\x00"])
def test_verify_rejects_buffers_too_short_to_hold_a_crc(short):
    assert verify_crc(short) is False


def test_single_bit_flips_change_the_crc():
    base = crc16_ccitt(b"\x00" * 8)
    for bit in range(8):
        mutated = bytearray(b"\x00" * 8)
        mutated[0] = 1 << bit
        assert crc16_ccitt(bytes(mutated)) != base
