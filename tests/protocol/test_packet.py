"""ITv2 application packet header."""

from __future__ import annotations

from dsc_itv2.commands import Command
from dsc_itv2.packet import (
    HEADER_SIZE,
    SIMPLE_ACK_PACKET_SIZE,
    Packet,
    build_packet,
    parse_packet,
)
import pytest


def test_full_packet_layout():
    wire = build_packet(0x11, 0x22, Command.Connection_Open_Session, b"\xde\xad")
    assert wire[0] == 0x11
    assert wire[1] == 0x22
    assert int.from_bytes(wire[2:4], "big") == int(Command.Connection_Open_Session)
    assert wire[4:] == b"\xde\xad"


def test_roundtrip_of_a_full_packet():
    wire = build_packet(0x01, 0x02, 0x1234, b"body")
    assert parse_packet(wire) == Packet(
        sender_sequence=0x01, receiver_sequence=0x02, command=0x1234, body=b"body"
    )


def test_simple_ack_collapses_to_two_bytes():
    wire = build_packet(0x05, 0x06, Command.Simple_Ack)
    assert len(wire) == SIMPLE_ACK_PACKET_SIZE
    assert wire == bytes([0x05, 0x06])


def test_two_byte_packet_parses_as_a_simple_ack():
    pkt = parse_packet(bytes([0x05, 0x06]))
    assert pkt.sender_sequence == 0x05
    assert pkt.receiver_sequence == 0x06
    assert pkt.command == int(Command.Simple_Ack)
    assert pkt.body == b""


def test_simple_ack_with_a_body_keeps_the_full_form():
    wire = build_packet(0x05, 0x06, Command.Simple_Ack, b"\x01")
    assert len(wire) == HEADER_SIZE + 1
    assert parse_packet(wire).body == b"\x01"


def test_an_empty_body_is_preserved_for_non_ack_commands():
    pkt = parse_packet(build_packet(0x00, 0x00, Command.Connection_Poll))
    assert pkt.command == int(Command.Connection_Poll)
    assert pkt.body == b""


def test_command_may_be_a_plain_int_or_an_enum():
    assert build_packet(0, 0, int(Command.Connection_Poll)) == build_packet(
        0, 0, Command.Connection_Poll
    )


def test_command_name_resolves_known_commands():
    pkt = parse_packet(build_packet(0, 0, Command.Connection_Poll))
    assert pkt.command_name == "Connection_Poll"


def test_command_name_falls_back_for_unknown_commands():
    pkt = parse_packet(build_packet(0, 0, 0x9999))
    assert pkt.command_name == "Unknown(0x9999)"


def test_repr_truncates_long_bodies():
    pkt = parse_packet(build_packet(0, 0, 0x1234, bytes(64)))
    assert "..." in repr(pkt)


@pytest.mark.parametrize("data", [b"", b"\x01"])
def test_packets_shorter_than_an_ack_are_rejected(data):
    with pytest.raises(ValueError, match="too short"):
        parse_packet(data)


def test_three_byte_packets_are_ambiguous_and_rejected():
    with pytest.raises(ValueError, match="ambiguous"):
        parse_packet(b"\x01\x02\x03")


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"sender_seq": 256, "receiver_seq": 0, "command": 0x1234}, "sender_seq"),
        ({"sender_seq": -1, "receiver_seq": 0, "command": 0x1234}, "sender_seq"),
        ({"sender_seq": 0, "receiver_seq": 256, "command": 0x1234}, "receiver_seq"),
        ({"sender_seq": 0, "receiver_seq": 0, "command": 0x10000}, "command"),
    ],
)
def test_out_of_range_values_are_rejected(kwargs, match):
    with pytest.raises(ValueError, match=match):
        build_packet(**kwargs)
