"""TLink transport framing (byte-stuff layer).

The lowest on-wire layer over TCP. A TLink packet consists of two
delimited regions: an optional ``header`` (terminated by ``0x7E``) and a
``payload`` (terminated by ``0x7F``). Both regions are byte-stuffed:

    0x7D -> 0x7D 0x00
    0x7E -> 0x7D 0x01
    0x7F -> 0x7D 0x02

For ITv2 specifically, the panel sends a 12-byte ASCII "Integration ID"
as the first packet's header; the client reuses that same value for all
subsequent outbound packets (see NeoHub ``TLinkTransport.DefaultHeader``
and ``ITv2Session.SessionId``).

Wire layout (after stuffing):

    <stuffed_header> 0x7E <stuffed_payload> 0x7F

Sources:
  - NeoHub ``TLinkTransport`` (GPL-3.0): Stuff/Unstuff + ParseFrame
  - DLS5 ``TLInstructionHelper.StuffBytes`` / ``UnStuffBytes`` (OEM)
"""
from __future__ import annotations

from dataclasses import dataclass

HEADER_DELIM: int = 0x7E
PAYLOAD_DELIM: int = 0x7F
ESC: int = 0x7D


def stuff(data: bytes | bytearray | memoryview) -> bytes:
    """Apply PPP/HDLC byte-stuffing for the three reserved values."""
    out = bytearray()
    for b in data:
        if b == ESC:
            out.append(ESC); out.append(0x00)
        elif b == HEADER_DELIM:
            out.append(ESC); out.append(0x01)
        elif b == PAYLOAD_DELIM:
            out.append(ESC); out.append(0x02)
        else:
            out.append(b)
    return bytes(out)


def unstuff(data: bytes | bytearray | memoryview) -> bytes:
    """Reverse byte-stuffing. Raises ValueError on malformed escapes."""
    out = bytearray()
    n = len(data)
    i = 0
    while i < n:
        b = data[i]
        if b == HEADER_DELIM:
            raise ValueError("invalid 0x7E inside stuffed region")
        if b == PAYLOAD_DELIM:
            raise ValueError("invalid 0x7F inside stuffed region")
        if b == ESC:
            if i + 1 >= n:
                raise ValueError("truncated escape at end of buffer")
            nxt = data[i + 1]
            if nxt == 0x00:
                out.append(ESC)
            elif nxt == 0x01:
                out.append(HEADER_DELIM)
            elif nxt == 0x02:
                out.append(PAYLOAD_DELIM)
            else:
                raise ValueError(f"invalid escape byte 0x{nxt:02x} after 0x7D")
            i += 2
        else:
            out.append(b)
            i += 1
    return bytes(out)


def pack(header: bytes, payload: bytes) -> bytes:
    """Build a complete on-wire TLink packet from raw header + payload."""
    return stuff(header) + bytes([HEADER_DELIM]) + stuff(payload) + bytes([PAYLOAD_DELIM])


@dataclass(frozen=True)
class TLinkPacket:
    """A parsed TLink packet: header + payload (both unstuffed)."""
    header: bytes
    payload: bytes


def extract_packet(buffer: bytes) -> tuple[TLinkPacket | None, bytes]:
    """Attempt to peel one complete TLink packet from a streaming buffer.

    Per NeoHub ``TLinkTransport.TryExtractPacket``: a packet is delimited
    by the first ``0x7F`` byte in the buffer (no SOF marker: the start
    is just the buffer position, since stuffing prevents ``0x7F`` from
    occurring inside the packet).

    Returns ``(packet, leftover)``. If no complete packet is yet
    available, returns ``(None, buffer)``.
    """
    end = buffer.find(PAYLOAD_DELIM)
    if end < 0:
        return None, buffer
    raw = buffer[: end + 1]  # includes the 0x7F
    leftover = buffer[end + 1 :]
    pkt = _parse_packet(raw)
    return pkt, leftover


def _parse_packet(raw: bytes) -> TLinkPacket:
    """Split raw (ending in 0x7F) into header + payload (both unstuffed).

    Raises ValueError if the header or payload delimiter is missing.
    """
    if not raw or raw[-1] != PAYLOAD_DELIM:
        raise ValueError("packet must end with 0x7F payload delimiter")
    body = raw[:-1]
    sep = body.find(HEADER_DELIM)
    if sep < 0:
        raise ValueError("missing 0x7E header delimiter")
    header_stuffed = body[:sep]
    payload_stuffed = body[sep + 1 :]
    return TLinkPacket(
        header=unstuff(header_stuffed),
        payload=unstuff(payload_stuffed),
    )


def parse_all(buffer: bytes) -> tuple[list[TLinkPacket], bytes]:
    """Peel as many complete packets as possible from a streaming buffer.

    Returns ``(packets, leftover)``. Malformed packets are skipped (their
    bytes are consumed; an exception is not raised to the caller: use
    ``extract_packet`` directly when caller wants per-packet error
    handling).
    """
    out: list[TLinkPacket] = []
    rest = buffer
    while True:
        pkt, rest = extract_packet(rest)
        if pkt is None:
            return out, rest
        out.append(pkt)
