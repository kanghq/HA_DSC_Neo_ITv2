"""ITv2 inner framing: length prefix + CRC-16 trailer."""

from __future__ import annotations

from dsc_itv2.crc import crc16_ccitt
from dsc_itv2.itv2_framing import (
    LEN_TWO_BYTE_FLAG,
    MAX_SINGLE_BYTE_LEN,
    add_framing,
    remove_framing,
)
import pytest


def test_single_byte_prefix_layout():
    framed = add_framing(b"\x01\x02\x03")
    assert framed[0] == 5  # 3 payload bytes + 2 CRC bytes
    assert framed[1:4] == b"\x01\x02\x03"
    assert framed[4:] == crc16_ccitt(framed[:4]).to_bytes(2, "big")


def test_two_byte_prefix_is_used_above_0x7f():
    packet = b"\xaa" * (MAX_SINGLE_BYTE_LEN - 1)  # length becomes 0x80
    framed = add_framing(packet)
    assert framed[0] & LEN_TWO_BYTE_FLAG
    assert ((framed[0] & 0x7F) << 8) | framed[1] == len(packet) + 2


def test_prefix_stays_single_byte_at_the_boundary():
    packet = b"\xaa" * (MAX_SINGLE_BYTE_LEN - 2)  # length becomes exactly 0x7F
    framed = add_framing(packet)
    assert framed[0] == MAX_SINGLE_BYTE_LEN
    assert not framed[0] & LEN_TWO_BYTE_FLAG


@pytest.mark.parametrize(
    "packet",
    [
        b"",
        b"\x00",
        b"\x01\x02\x03\x04",
        bytes(range(120)),
        bytes(range(256)) * 2,
    ],
)
def test_roundtrip(packet):
    frame = remove_framing(add_framing(packet))
    assert frame.packet == packet
    assert frame.consumed == len(add_framing(packet))


def test_trailing_aes_padding_is_ignored():
    framed = add_framing(b"\x01\x02\x03")
    frame = remove_framing(framed + b"\x00" * 13)
    assert frame.packet == b"\x01\x02\x03"
    assert frame.consumed == len(framed)


def test_consumed_allows_walking_concatenated_frames():
    buf = add_framing(b"first") + add_framing(b"second")
    first = remove_framing(buf)
    second = remove_framing(buf[first.consumed :])
    assert first.packet == b"first"
    assert second.packet == b"second"


def test_crc_mismatch_is_rejected():
    framed = bytearray(add_framing(b"payload"))
    framed[-1] ^= 0xFF
    with pytest.raises(ValueError, match="CRC mismatch"):
        remove_framing(bytes(framed))


def test_payload_corruption_is_caught_by_the_crc():
    framed = bytearray(add_framing(b"payload"))
    framed[2] ^= 0x01
    with pytest.raises(ValueError, match="CRC mismatch"):
        remove_framing(bytes(framed))


def test_empty_input_is_rejected():
    with pytest.raises(ValueError, match="empty input"):
        remove_framing(b"")


def test_truncated_two_byte_prefix_is_rejected():
    with pytest.raises(ValueError, match="truncated 2-byte length prefix"):
        remove_framing(bytes([LEN_TWO_BYTE_FLAG | 0x01]))


def test_length_below_the_crc_size_is_rejected():
    with pytest.raises(ValueError, match="too small"):
        remove_framing(b"\x01\x00\x00")


def test_declared_length_overrunning_the_buffer_is_rejected():
    with pytest.raises(ValueError, match="truncated"):
        remove_framing(b"\x20\x01\x02")


def test_packet_too_large_for_the_length_field():
    with pytest.raises(ValueError, match="too large"):
        add_framing(b"\x00" * 0x7FFF)
