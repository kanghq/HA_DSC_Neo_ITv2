"""ITv2 application packet header.

Two wire shapes per NeoHub ``ITv2Session.ParseITv2Packet`` +
``MessageFactory.DeserializeMessage``:

  * **Full packet** (4+ bytes)::
        [0]     SenderSequence    (our increment-per-send byte)
        [1]     ReceiverSequence  (echo of the peer's last SenderSequence)
        [2..3]  Command           (uint16, big-endian)
        [4..]   Message body      (per-command-specific)

  * **SimpleAck** (2 bytes exactly)::
        [0]     SenderSequence
        [1]     ReceiverSequence
    No command word, no body. Implicit ``Command.Simple_Ack`` (0x0000).
    DLS5 / NeoHub special-case this: any 2-byte packet IS a SimpleAck.

For command-class messages (subclasses of ``CommandMessageBase``), the
first body byte is the ``CommandSequence``. Pure notifications/acks
don't carry it.
"""
from __future__ import annotations

from dataclasses import dataclass

from .commands import Command, name_of

HEADER_SIZE: int = 4
SIMPLE_ACK_PACKET_SIZE: int = 2  # SenderSeq + ReceiverSeq only
SENDER_SEQ_OFFSET: int = 0
RECEIVER_SEQ_OFFSET: int = 1
COMMAND_OFFSET: int = 2  # big-endian uint16


@dataclass(frozen=True)
class Packet:
    """A decrypted, un-framed ITv2 application packet."""
    sender_sequence: int
    receiver_sequence: int
    command: int
    body: bytes

    @property
    def command_name(self) -> str:
        return name_of(self.command)

    def __repr__(self) -> str:
        body_hex = self.body.hex() if len(self.body) <= 32 else self.body[:32].hex() + "..."
        return (f"Packet(snd=0x{self.sender_sequence:02x}, rcv=0x{self.receiver_sequence:02x}, "
                f"cmd={self.command_name}(0x{self.command:04x}), body={body_hex})")


def parse_packet(data: bytes) -> Packet:
    """Parse a decrypted, un-framed ITv2 packet.

    ``data`` is the inner packet bytes (no length prefix, no CRC, no
    TLink framing). May include trailing zero-padding from AES-ECB
    decryption: callers are responsible for trimming it to the
    length-prefix size before reaching this function.

    Raises ValueError if ``data`` is shorter than 2 bytes, or is
    between 2 and 4 bytes (ambiguous: neither a 2-byte ack nor a full
    header-with-body packet).
    """
    n = len(data)
    if n < SIMPLE_ACK_PACKET_SIZE:
        raise ValueError(
            f"packet too short: {n} bytes (need at least {SIMPLE_ACK_PACKET_SIZE})"
        )
    sender_seq = data[SENDER_SEQ_OFFSET]
    receiver_seq = data[RECEIVER_SEQ_OFFSET]
    if n == SIMPLE_ACK_PACKET_SIZE:
        # 2-byte SimpleAck form: no command word, no body
        return Packet(
            sender_sequence=sender_seq,
            receiver_sequence=receiver_seq,
            command=int(Command.Simple_Ack),
            body=b"",
        )
    if n < HEADER_SIZE:
        raise ValueError(
            f"packet has {n} bytes: ambiguous (neither 2-byte ack "
            f"nor full {HEADER_SIZE}-byte header packet)"
        )
    command = (data[COMMAND_OFFSET] << 8) | data[COMMAND_OFFSET + 1]
    body = bytes(data[HEADER_SIZE:])
    return Packet(
        sender_sequence=sender_seq,
        receiver_sequence=receiver_seq,
        command=command,
        body=body,
    )


def build_packet(
    sender_seq: int, receiver_seq: int,
    command: int | Command, body: bytes = b"",
) -> bytes:
    """Build a decrypted, un-framed ITv2 packet.

    Implicit special case: when ``command`` is ``Simple_Ack`` (0) and
    ``body`` is empty, the result is the 2-byte ack form (per NeoHub
    ``MessageFactory.SerializeMessage`` which returns an empty list for
    ``SimpleAck``).

    The caller is responsible for adding ITv2 length+CRC framing and
    the TLink transport wrapper (and encryption, if active).
    """
    if isinstance(command, Command):
        command = int(command)
    if not (0 <= sender_seq <= 0xFF):
        raise ValueError(f"sender_seq out of range: {sender_seq}")
    if not (0 <= receiver_seq <= 0xFF):
        raise ValueError(f"receiver_seq out of range: {receiver_seq}")
    if not (0 <= command <= 0xFFFF):
        raise ValueError(f"command out of range: {command}")

    # SimpleAck -> 2-byte form on the wire
    if command == int(Command.Simple_Ack) and not body:
        return bytes([sender_seq, receiver_seq])

    return bytes([
        sender_seq,
        receiver_seq,
        (command >> 8) & 0xFF,
        command & 0xFF,
    ]) + body
