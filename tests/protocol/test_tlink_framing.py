"""TLink transport framing: byte stuffing and packet extraction."""

from __future__ import annotations

from dsc_itv2.tlink_framing import (
    ESC,
    HEADER_DELIM,
    PAYLOAD_DELIM,
    TLinkPacket,
    extract_packet,
    pack,
    parse_all,
    stuff,
    unstuff,
)
import pytest

INTEGRATION_ID = b"123456789012"


def test_reserved_byte_mapping():
    assert stuff(bytes([ESC])) == bytes([ESC, 0x00])
    assert stuff(bytes([HEADER_DELIM])) == bytes([ESC, 0x01])
    assert stuff(bytes([PAYLOAD_DELIM])) == bytes([ESC, 0x02])


def test_ordinary_bytes_pass_through_untouched():
    plain = bytes(b for b in range(256) if b not in (ESC, HEADER_DELIM, PAYLOAD_DELIM))
    assert stuff(plain) == plain


def test_stuff_unstuff_roundtrip_over_every_byte_value():
    payload = bytes(range(256))
    assert unstuff(stuff(payload)) == payload


def test_stuffed_output_never_contains_a_delimiter():
    stuffed = stuff(bytes(range(256)))
    assert HEADER_DELIM not in stuffed
    assert PAYLOAD_DELIM not in stuffed


@pytest.mark.parametrize(
    ("bad", "match"),
    [
        (bytes([HEADER_DELIM]), "0x7E"),
        (bytes([PAYLOAD_DELIM]), "0x7F"),
        (bytes([ESC]), "truncated escape"),
        (bytes([ESC, 0x99]), "invalid escape byte"),
    ],
)
def test_unstuff_rejects_malformed_input(bad, match):
    with pytest.raises(ValueError, match=match):
        unstuff(bad)


def test_pack_layout():
    wire = pack(b"AB", b"CD")
    assert wire == b"AB" + bytes([HEADER_DELIM]) + b"CD" + bytes([PAYLOAD_DELIM])


def test_pack_extract_roundtrip():
    payload = bytes(range(256))
    pkt, leftover = extract_packet(pack(INTEGRATION_ID, payload))
    assert pkt == TLinkPacket(header=INTEGRATION_ID, payload=payload)
    assert leftover == b""


def test_extract_returns_none_for_an_incomplete_packet():
    wire = pack(INTEGRATION_ID, b"payload")
    pkt, leftover = extract_packet(wire[:-1])
    assert pkt is None
    assert leftover == wire[:-1]


def test_extract_leaves_trailing_bytes_in_the_buffer():
    wire = pack(INTEGRATION_ID, b"one")
    pkt, leftover = extract_packet(wire + b"partial-next")
    assert pkt.payload == b"one"
    assert leftover == b"partial-next"


def test_empty_payload_is_a_valid_packet():
    pkt, leftover = extract_packet(pack(INTEGRATION_ID, b""))
    assert pkt.header == INTEGRATION_ID
    assert pkt.payload == b""
    assert leftover == b""


def test_parse_all_drains_multiple_packets():
    stream = pack(INTEGRATION_ID, b"one") + pack(INTEGRATION_ID, b"two") + b"tail"
    packets, leftover = parse_all(stream)
    assert [p.payload for p in packets] == [b"one", b"two"]
    assert leftover == b"tail"


def test_parse_all_on_an_empty_buffer():
    assert parse_all(b"") == ([], b"")


def test_delimiters_in_payload_round_trip():
    payload = bytes([PAYLOAD_DELIM, HEADER_DELIM, ESC, 0x00, 0x01, 0x02])
    pkt, leftover = extract_packet(pack(INTEGRATION_ID, payload))
    assert pkt.payload == payload
    assert leftover == b""
