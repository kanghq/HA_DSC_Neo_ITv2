"""ITv2 encryption: AES-128-ECB with per-session derived keys.

Implements both Type 1 and Type 2 encryption handlers used by the
TL280 ITv2 handshake. Reference: NeoHub Type1EncryptionHandler.cs /
Type2EncryptionHandler.cs (GPL-3.0).

Type 1: uses Integration Identification Number [851][422] +
    Integration Access Code [851][423,450,477,504]. 48-byte initializer
    with check-byte validation. Two derived keys (one from each).

Type 2: uses Integration Access Code [851][700..703] only (32-char hex).
    16-byte initializer. The access code IS the AES key directly.

Both use AES-128-ECB with PaddingMode.None for KDF + session encryption.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import secrets
import threading

try:
    from Crypto.Cipher import AES
except ImportError as exc:
    raise ImportError("pycryptodome is required: pip install pycryptodome") from exc


AES_BLOCK_SIZE = 16


def pad_to_block(data: bytes) -> bytes:
    """Zero-pad to AES block boundary."""
    rem = len(data) % AES_BLOCK_SIZE
    if rem == 0:
        return data
    return data + b"\x00" * (AES_BLOCK_SIZE - rem)


class RawKeyCipher:
    """AES-128-ECB with PaddingMode.None and a fixed key.

    Building block for Type 1/Type 2 handlers and for post-handshake
    session encryption (one cipher per direction).
    """

    def __init__(self, key: bytes) -> None:
        if len(key) != AES_BLOCK_SIZE:
            raise ValueError(f"AES-128 key must be {AES_BLOCK_SIZE} bytes, got {len(key)}")
        self._key = bytes(key)
        self._lock = threading.Lock()
        self._cipher = None

    def _ensure(self):
        if self._cipher is None:
            self._cipher = AES.new(self._key, AES.MODE_ECB)
        return self._cipher

    def encrypt(self, plaintext: bytes) -> bytes:
        padded = pad_to_block(plaintext)
        with self._lock:
            return self._ensure().encrypt(padded)

    def decrypt(self, ciphertext: bytes) -> bytes:
        if len(ciphertext) % AES_BLOCK_SIZE != 0:
            raise ValueError(f"ciphertext length {len(ciphertext)} not multiple of {AES_BLOCK_SIZE}")
        with self._lock:
            return self._ensure().decrypt(ciphertext)


# ---- Key derivation helpers ------------------------------------------------

def key_from_type2_hex(access_code_hex: str) -> bytes:
    """Type 2: 32-char hex code IS the AES key directly."""
    if not access_code_hex or len(access_code_hex) != 32:
        raise ValueError("Type 2 access code must be exactly 32 hex chars")
    try:
        return bytes.fromhex(access_code_hex)
    except ValueError as exc:
        raise ValueError("Type 2 access code must be valid hex") from exc


def key_from_type1_string(value: str) -> bytes:
    """Type 1 KDF: first 8 chars repeated 4 times, hex-decoded.

    Per NeoHub Type1EncryptionHandler.TransformKeyString. Used for both
    the IntegrationID-derived key AND the Access Code-derived key.
    """
    if not value or len(value) < 8:
        raise ValueError("value must be at least 8 chars")
    first8 = value[:8]
    hex_str = first8 * 4
    try:
        return bytes.fromhex(hex_str)
    except ValueError as exc:
        raise ValueError("value must contain only hex-decodable digits") from exc


# Backwards-compat alias used by older tests
key_from_type1_integration_id = key_from_type1_string


def _even_indexes(data: bytes) -> bytes:
    """Bytes at even indices (0, 2, 4, ...)."""
    return bytes(data[i] for i in range(0, len(data), 2))


def _odd_indexes(data: bytes) -> bytes:
    """Bytes at odd indices (1, 3, 5, ...)."""
    return bytes(data[i] for i in range(1, len(data), 2))


# ---- Handshake handlers ----------------------------------------------------


class EncryptionHandler(ABC):
    """Base class for ITv2 per-session encryption handlers.

    Lifecycle (per session, exactly once each):
      1. configure_inbound() -> bytes
         Generates the local initializer for sending to the panel; sets
         up our INBOUND (decrypt) key from it.
      2. configure_outbound(remote_initializer)
         Processes the panel's initializer to set up our OUTBOUND
         (encrypt) key.
      3. encrypt(...) / decrypt(...) per packet thereafter.
    """

    def __init__(self) -> None:
        self._inbound_cipher: RawKeyCipher | None = None
        self._outbound_cipher: RawKeyCipher | None = None

    @abstractmethod
    def configure_inbound(self) -> bytes:
        """Return the bytes to send to the panel as our initializer."""

    @abstractmethod
    def configure_outbound(self, remote_initializer: bytes) -> None:
        """Process the panel's initializer to set up outbound encryption.

        Raises ValueError on validation failure (Type 1 check-byte mismatch).
        """

    @property
    def is_inbound_active(self) -> bool:
        """True once :meth:`configure_inbound` has been called."""
        return self._inbound_cipher is not None

    @property
    def is_outbound_active(self) -> bool:
        """True once :meth:`configure_outbound` has been called."""
        return self._outbound_cipher is not None

    def encrypt(self, plaintext: bytes) -> bytes:
        if self._outbound_cipher is None:
            raise RuntimeError("outbound not configured; call configure_outbound() first")
        return self._outbound_cipher.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        if self._inbound_cipher is None:
            raise RuntimeError("inbound not configured; call configure_inbound() first")
        return self._inbound_cipher.decrypt(ciphertext)


class Type2EncryptionHandler(EncryptionHandler):
    """Type 2: pre-shared 32-char hex AES key.

    Per direction:
      session_key = AES_encrypt(access_code_key, initializer_bytes)
    """

    INITIALIZER_LEN = 16

    def __init__(self, access_code_hex: str) -> None:
        super().__init__()
        self._access_code = key_from_type2_hex(access_code_hex)
        self._kdf_cipher = RawKeyCipher(self._access_code)

    def configure_inbound(self) -> bytes:
        local_initializer = secrets.token_bytes(self.INITIALIZER_LEN)
        inbound_key = self._kdf_cipher.encrypt(local_initializer)
        self._inbound_cipher = RawKeyCipher(inbound_key)
        return local_initializer

    def configure_outbound(self, remote_initializer: bytes) -> None:
        if len(remote_initializer) != self.INITIALIZER_LEN:
            raise ValueError(
                f"Type 2 remote initializer must be {self.INITIALIZER_LEN} bytes, "
                f"got {len(remote_initializer)}"
            )
        outbound_key = self._kdf_cipher.encrypt(remote_initializer)
        self._outbound_cipher = RawKeyCipher(outbound_key)


class Type1EncryptionHandler(EncryptionHandler):
    """Type 1: IntegrationID + 8-digit Integration Access Code.

    Inbound (us -> panel):
      1. Generate 32 random bytes
      2. Session key = odd-indexed bytes (16 bytes)
      3. Check bytes = even-indexed bytes (16 bytes)
      4. Encrypt 32 bytes with access-code-derived key
      5. Send check_bytes || ciphertext (48 bytes total)
      6. Panel decrypts ciphertext with access-code-derived key,
         verifies even-indexed bytes match check_bytes, uses odd-indexed
         bytes as the inbound session key on its side.

    Outbound (panel -> us):
      1. Receive 48 bytes from panel: 16 check + 32 cipher
      2. Decrypt cipher half with IntegrationID-derived key
      3. Verify even-indexed bytes of plaintext match check_bytes
      4. Use odd-indexed bytes of plaintext as outbound session key
    """

    INITIALIZER_LEN = 48
    CHECK_BYTES_LEN = 16
    CIPHER_HALF_LEN = 32

    def __init__(self, integration_id: str, access_code: str) -> None:
        super().__init__()
        self._integration_id_key = key_from_type1_string(integration_id)
        self._access_code_key = key_from_type1_string(access_code)
        self._iid_cipher = RawKeyCipher(self._integration_id_key)
        self._ac_cipher = RawKeyCipher(self._access_code_key)

    def configure_inbound(self) -> bytes:
        # Generate 32 random bytes; odd-indexed = session key, even = check
        random_bytes = secrets.token_bytes(self.CIPHER_HALF_LEN)
        check_bytes = _even_indexes(random_bytes)
        inbound_key = _odd_indexes(random_bytes)
        self._inbound_cipher = RawKeyCipher(inbound_key)

        # Encrypt the 32 random bytes with the access-code key
        cipher_half = self._ac_cipher.encrypt(random_bytes)

        return check_bytes + cipher_half  # 16 + 32 = 48 bytes

    def configure_outbound(self, remote_initializer: bytes) -> None:
        if len(remote_initializer) != self.INITIALIZER_LEN:
            raise ValueError(
                f"Type 1 remote initializer must be {self.INITIALIZER_LEN} bytes, "
                f"got {len(remote_initializer)}"
            )
        check_bytes = remote_initializer[:self.CHECK_BYTES_LEN]
        cipher_half = remote_initializer[self.CHECK_BYTES_LEN:]

        # Decrypt the cipher half with the IntegrationID-derived key
        plaintext = self._iid_cipher.decrypt(cipher_half)

        # Verify check bytes match the even-indexed bytes of plaintext
        if _even_indexes(plaintext) != check_bytes:
            raise ValueError(
                "Type 1 encryption initializer check-byte mismatch. "
                "likely wrong IntegrationID or wrong Access Code"
            )

        # Outbound key is the odd-indexed bytes of plaintext
        outbound_key = _odd_indexes(plaintext)
        self._outbound_cipher = RawKeyCipher(outbound_key)


# ---- Default keys (informational - NOT for production use) ------------------

# NeoHub-documented factory defaults
NEOHUB_DEFAULT_TYPE2_HEX: str = "12345678123456781234567812345678"
NEOHUB_DEFAULT_KEY: bytes = bytes.fromhex(NEOHUB_DEFAULT_TYPE2_HEX)
NEOHUB_DEFAULT_TYPE1_ACCESS_CODE: str = "12345678"
