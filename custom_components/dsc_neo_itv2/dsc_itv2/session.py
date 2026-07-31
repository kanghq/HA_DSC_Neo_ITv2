"""ITv2 session codec: pure-sync handshake state machine.

I/O-free: callers feed bytes received from the TCP socket to
:meth:`SessionCodec.feed` and forward any returned ``bytes_to_send``
back over the socket. The full handshake (per NeoHub
``ITv2Session.DoHandshakeAsync``) is driven entirely by inbound packets.

Once handshake completes the codec emits a :class:`Connected` event and
the caller may invoke :meth:`send_message` to encode application
messages for transmission. Inbound notifications are emitted as
:class:`Notification` events.

This file does NOT spin up sockets, asyncio, or threads. It's purely a
deterministic state machine that we can drive with unit tests using
synthetic byte streams.

Reference: NeoHub ``DSC.TLink.ITv2.ITv2Session`` (GPL-3.0).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import Enum, auto
import logging

from . import itv2_framing, messages, packet, tlink_framing
from .commands import Command, name_of
from .encryption import (
    EncryptionHandler,
    Type1EncryptionHandler,
    Type2EncryptionHandler,
)
from .messages import (
    CommandResponse,
    ConnectionEndSession,
    OpenSession,
    RequestAccess,
    SimpleAck,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Settings (per-connection, indexed by SessionId after handshake step 1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConnectionSettings:
    """Keys / identifiers needed to encrypt the session.

    Provide whatever applies to the panel's chosen encryption type. The
    codec validates the chosen type against what's set at handshake
    time.
    """
    integration_id: str | None = None          # [851][422] (12 digits)
    type1_access_code: str | None = None       # [851][423,450,477,504]
    type2_access_code_hex: str | None = None   # [851][700..703] (32 hex)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class State(Enum):
    AWAITING_OPEN_SESSION = auto()
    AWAITING_OPEN_SESSION_ACK_FROM_PANEL = auto()    # we sent CommandResponse, expect SimpleAck
    AWAITING_OPEN_SESSION_ECHO_RESPONSE = auto()     # we echoed OpenSession, expect CommandResponse
    AWAITING_OPEN_SESSION_ECHO_ACK = auto()          # we sent SimpleAck back, expect RequestAccess
    AWAITING_REQUEST_ACCESS_ACK_FROM_PANEL = auto()  # we acked RequestAccess, expect SimpleAck
    AWAITING_OUR_REQUEST_ACCESS_RESPONSE = auto()    # we sent our RequestAccess, expect CommandResponse
    READY = auto()
    CLOSED = auto()
    FAILED = auto()


# ---------------------------------------------------------------------------
# Events emitted by feed()
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BytesToSend:
    """Raw wire bytes that the caller must write to the TCP socket."""
    data: bytes


@dataclass(frozen=True)
class Connected:
    """Handshake completed. The session is now READY."""
    session_id: str
    encryption_type: int   # 1 or 2
    panel_firmware_major: int
    panel_firmware_minor: int


@dataclass(frozen=True)
class Notification:
    """An application-layer message arrived from the panel."""
    command: int
    command_name: str
    body: bytes
    decoded: object | None  # populated when a decoder is registered


@dataclass(frozen=True)
class Closed:
    """Panel sent Connection_End_Session or the codec was shut down."""
    reason: str


@dataclass(frozen=True)
class Failed:
    """Unrecoverable error (framing/encryption/handshake)."""
    reason: str


Event = BytesToSend | Connected | Notification | Closed | Failed


# ---------------------------------------------------------------------------
# Codec
# ---------------------------------------------------------------------------


class SessionCodec:
    """Deterministic, I/O-free ITv2 session codec.

    Usage::

        codec = SessionCodec(settings)
        # ...
        events = codec.feed(bytes_from_socket)
        for ev in events:
            if isinstance(ev, BytesToSend):
                socket.send(ev.data)
            elif isinstance(ev, Connected):
                ...
    """

    def __init__(self, settings: ConnectionSettings) -> None:
        self._settings = settings

        # TLink layer
        self._buffer: bytes = b""
        self._default_header: bytes = b""

        # Session identification
        self._session_id: str = ""

        # ITv2 layer
        self._state: State = State.AWAITING_OPEN_SESSION
        self._encryption: EncryptionHandler | None = None
        self._panel_open_session: OpenSession | None = None

        # Sequence state: matches NeoHub semantics:
        #   _local_sequence starts at 1; first outbound non-handshake use is 1, then ++ for each
        #   _remote_sequence tracks the panel's last sender_sequence
        #   _command_sequence starts at the panel's OpenSession.command_sequence, ++ per outbound command
        self._local_sequence: int = 1
        self._remote_sequence: int = 0
        self._command_sequence: int = 0

    # ---- Public API ----

    @property
    def state(self) -> State:
        return self._state

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def is_ready(self) -> bool:
        return self._state == State.READY

    def feed(self, data: bytes) -> list[Event]:
        """Process bytes received from the panel. Returns events to act on.

        Idempotent in the sense that calling with ``b""`` is a no-op.
        """
        events: list[Event] = []
        if data:
            self._buffer += data
        while True:
            tlink_pkt, self._buffer = tlink_framing.extract_packet(self._buffer)
            if tlink_pkt is None:
                return events
            if not self._default_header:
                self._default_header = tlink_pkt.header
                self._session_id = self._default_header.decode("ascii", errors="replace")
                _LOGGER.debug("TLink default header captured: SessionId=%r", self._session_id)
            try:
                self._process_payload(tlink_pkt.payload, events)
            except Exception as exc:
                _LOGGER.exception("Fatal codec error")
                self._state = State.FAILED
                events.append(Failed(reason=str(exc)))
                return events

    def send_message(self, msg) -> bytes:
        """Encode an application message for transmission.

        Returns the raw bytes to write. Increments the local sequence
        counter. Must NOT be called before the :class:`Connected` event.
        """
        if self._state != State.READY:
            raise RuntimeError(f"cannot send_message in state {self._state.name}")
        command, body = messages.encode_message(msg)
        sender_seq = self._next_local_sequence()
        return self._build_wire_bytes(sender_seq, self._remote_sequence, command, body)

    def close(self) -> bytes:
        """Build a Connection_End_Session frame; caller should send + close socket."""
        if self._state in (State.CLOSED, State.FAILED):
            return b""
        command, body = messages.encode_message(ConnectionEndSession())
        sender_seq = self._next_local_sequence()
        out = self._build_wire_bytes(sender_seq, self._remote_sequence, command, body)
        self._state = State.CLOSED
        return out

    # ---- Internal: inbound processing ----

    def _process_payload(self, raw_payload: bytes, events: list[Event]) -> None:
        """Decrypt (if active), de-frame, parse, dispatch."""
        # Decrypt if our inbound is active
        if self._encryption is not None and self._encryption.is_inbound_active:
            try:
                decoded = self._encryption.decrypt(raw_payload)
            except Exception as exc:
                raise ValueError(f"decryption failed: {exc}") from exc
        else:
            decoded = raw_payload

        frame = itv2_framing.remove_framing(decoded)
        pkt = packet.parse_packet(frame.packet)
        self._remote_sequence = pkt.sender_sequence

        msg = messages.decode_message(pkt.command, pkt.body)
        _LOGGER.debug(
            "RX [snd=0x%02x rcv=0x%02x] %s body=%s",
            pkt.sender_sequence, pkt.receiver_sequence,
            pkt.command_name, pkt.body.hex(),
        )

        self._dispatch(pkt, msg, events)

    def _dispatch(self, pkt: packet.Packet, msg, events: list[Event]) -> None:
        # Step 1: panel sends OpenSession
        if isinstance(msg, OpenSession) and self._state == State.AWAITING_OPEN_SESSION:
            self._panel_open_session = msg
            self._command_sequence = msg.command_sequence
            _LOGGER.debug(
                "Handshake step 1: OpenSession received (encryption=%d, fw=%d.%d)",
                msg.encryption_type, msg.firmware_major, msg.firmware_minor,
            )
            self._send_command_response(msg.command_sequence, pkt.sender_sequence, events)
            self._state = State.AWAITING_OPEN_SESSION_ACK_FROM_PANEL
            return

        # Step 3: panel acks our CommandResponse
        if isinstance(msg, SimpleAck) and self._state == State.AWAITING_OPEN_SESSION_ACK_FROM_PANEL:
            _LOGGER.debug("Handshake step 3: panel acked our OpenSession ack")
            self._send_open_session_echo(events)
            self._state = State.AWAITING_OPEN_SESSION_ECHO_RESPONSE
            return

        # Step 5: panel responds to our OpenSession echo
        if isinstance(msg, CommandResponse) and self._state == State.AWAITING_OPEN_SESSION_ECHO_RESPONSE:
            _LOGGER.debug(
                "Handshake step 5: OpenSession echo response code=%d",
                msg.response_code,
            )
            if msg.response_code != 0:
                raise ValueError(f"panel rejected OpenSession echo: code={msg.response_code}")
            # Step 6: send SimpleAck back
            self._send_simple_ack(pkt.sender_sequence, events)
            # Set up the encryption handler (not yet active on wire)
            self._setup_encryption_handler()
            self._state = State.AWAITING_OPEN_SESSION_ECHO_ACK
            return

        # Step 7: panel sends RequestAccess
        if isinstance(msg, RequestAccess) and self._state == State.AWAITING_OPEN_SESSION_ECHO_ACK:
            _LOGGER.debug(
                "Handshake step 7: RequestAccess received (%d-byte initializer)",
                len(msg.initializer),
            )
            # Configure outbound encryption from panel's initializer.
            # This MUST happen before our next outbound send (step 8).
            assert self._encryption is not None
            self._encryption.configure_outbound(msg.initializer)
            # Step 8: send encrypted CommandResponse
            self._send_command_response(msg.command_sequence, pkt.sender_sequence, events)
            self._state = State.AWAITING_REQUEST_ACCESS_ACK_FROM_PANEL
            return

        # Step 9: panel acks our encrypted CommandResponse (still plaintext on
        # panel->us direction since panel hasn't seen our initializer yet)
        if isinstance(msg, SimpleAck) and self._state == State.AWAITING_REQUEST_ACCESS_ACK_FROM_PANEL:
            _LOGGER.debug("Handshake step 9: panel acked our encrypted CommandResponse")
            # Step 10: configure OUR inbound, then send our RequestAccess
            assert self._encryption is not None
            our_initializer = self._encryption.configure_inbound()
            self._send_our_request_access(our_initializer, events)
            self._state = State.AWAITING_OUR_REQUEST_ACCESS_RESPONSE
            return

        # Step 11: panel responds to our RequestAccess (encrypted, decrypted above)
        if isinstance(msg, CommandResponse) and self._state == State.AWAITING_OUR_REQUEST_ACCESS_RESPONSE:
            if msg.response_code != 0:
                raise ValueError(f"panel rejected our RequestAccess: code={msg.response_code}")
            _LOGGER.debug("Handshake step 11: panel accepted our RequestAccess")
            # Step 12: send final SimpleAck
            self._send_simple_ack(pkt.sender_sequence, events)
            self._state = State.READY
            assert self._panel_open_session is not None
            events.append(Connected(
                session_id=self._session_id,
                encryption_type=self._panel_open_session.encryption_type,
                panel_firmware_major=self._panel_open_session.firmware_major,
                panel_firmware_minor=self._panel_open_session.firmware_minor,
            ))
            return

        # Post-handshake: notifications
        if self._state == State.READY:
            if isinstance(msg, ConnectionEndSession) or pkt.command == int(Command.Connection_End_Session):
                events.append(Closed(reason="panel sent Connection_End_Session"))
                self._state = State.CLOSED
                return
            if isinstance(msg, SimpleAck):
                return  # ignore raw acks (they're responses to our sends)
            # All other inbound messages get acked + published as notifications
            self._send_simple_ack(pkt.sender_sequence, events)
            events.append(Notification(
                command=pkt.command,
                command_name=name_of(pkt.command),
                body=pkt.body,
                decoded=msg,  # None if no decoder registered
            ))
            return

        raise ValueError(
            f"unexpected {pkt.command_name} (0x{pkt.command:04x}) in state {self._state.name}"
        )

    # ---- Internal: outbound builders ----

    def _send_command_response(self, command_seq: int, panel_sender_seq: int, events: list[Event]) -> None:
        cr = CommandResponse(command_sequence=command_seq, response_code=0)
        cmd, body = messages.encode_message(cr)
        wire = self._build_wire_bytes(self._local_sequence, panel_sender_seq, cmd, body)
        events.append(BytesToSend(data=wire))

    def _send_simple_ack(self, panel_sender_seq: int, events: list[Event]) -> None:
        cmd, body = messages.encode_message(SimpleAck())
        wire = self._build_wire_bytes(self._local_sequence, panel_sender_seq, cmd, body)
        events.append(BytesToSend(data=wire))

    def _send_open_session_echo(self, events: list[Event]) -> None:
        assert self._panel_open_session is not None
        self._command_sequence = self._next_command_sequence()
        echo = dataclasses.replace(
            self._panel_open_session,
            command_sequence=self._command_sequence,
        )
        cmd, body = messages.encode_message(echo)
        sender_seq = self._next_local_sequence()
        wire = self._build_wire_bytes(sender_seq, self._remote_sequence, cmd, body)
        events.append(BytesToSend(data=wire))

    def _send_our_request_access(self, initializer: bytes, events: list[Event]) -> None:
        self._command_sequence = self._next_command_sequence()
        ra = RequestAccess(
            command_sequence=self._command_sequence,
            initializer=initializer,
        )
        cmd, body = messages.encode_message(ra)
        sender_seq = self._next_local_sequence()
        wire = self._build_wire_bytes(sender_seq, self._remote_sequence, cmd, body)
        events.append(BytesToSend(data=wire))

    def _build_wire_bytes(
        self,
        sender_seq: int,
        receiver_seq: int,
        command: int,
        body: bytes,
    ) -> bytes:
        """Build a complete outbound wire frame (packet -> ITv2 frame -> encrypt -> TLink)."""
        pkt = packet.build_packet(sender_seq, receiver_seq, command, body)
        framed = itv2_framing.add_framing(pkt)
        if self._encryption is not None and self._encryption.is_outbound_active:
            framed = self._encryption.encrypt(framed)
        return tlink_framing.pack(self._default_header, framed)

    # ---- Internal: helpers ----

    def _next_local_sequence(self) -> int:
        self._local_sequence = (self._local_sequence + 1) & 0xFF
        if self._local_sequence == 0:  # avoid 0 (matches NeoHub's pre-increment from 1)
            self._local_sequence = 1
        return self._local_sequence

    def _next_command_sequence(self) -> int:
        self._command_sequence = (self._command_sequence + 1) & 0xFF
        if self._command_sequence == 0:
            self._command_sequence = 1
        return self._command_sequence

    def _setup_encryption_handler(self) -> None:
        assert self._panel_open_session is not None
        etype = self._panel_open_session.encryption_type
        if etype == 1:
            if not self._settings.type1_access_code:
                raise ValueError("panel requested Type 1 encryption but type1_access_code is not configured")
            if not self._settings.integration_id:
                raise ValueError("panel requested Type 1 encryption but integration_id is not configured")
            self._encryption = Type1EncryptionHandler(
                integration_id=self._settings.integration_id,
                access_code=self._settings.type1_access_code,
            )
        elif etype == 2:
            if not self._settings.type2_access_code_hex:
                raise ValueError("panel requested Type 2 encryption but type2_access_code_hex is not configured")
            self._encryption = Type2EncryptionHandler(
                access_code_hex=self._settings.type2_access_code_hex,
            )
        else:
            raise ValueError(f"unsupported encryption type: {etype}")
        _LOGGER.debug("Encryption handler initialized: type=%d", etype)
