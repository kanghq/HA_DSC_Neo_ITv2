"""ITv2 encryption: AES-128-ECB with per-session derived keys."""

from __future__ import annotations

from dsc_itv2.encryption import (
    AES_BLOCK_SIZE,
    NEOHUB_DEFAULT_KEY,
    NEOHUB_DEFAULT_TYPE1_ACCESS_CODE,
    NEOHUB_DEFAULT_TYPE2_HEX,
    RawKeyCipher,
    Type1EncryptionHandler,
    Type2EncryptionHandler,
    key_from_type1_integration_id,
    key_from_type1_string,
    key_from_type2_hex,
    pad_to_block,
)
import pytest

TYPE2_KEY = "000102030405060708090a0b0c0d0e0f"

# Type 1 derives its inbound key from the access code and its outbound key
# from the Integration ID. Giving both the same leading 8 characters makes
# the two derived keys identical, which lets a single handler talk to
# itself: exactly what is needed to exercise the check-byte protocol.
T1_INTEGRATION_ID = "12345678ABCD"
T1_ACCESS_CODE = "12345678"


# --------------------------------------------------------------------------
# Padding + raw cipher
# --------------------------------------------------------------------------


@pytest.mark.parametrize("size", [0, 1, 15, 16, 17, 31, 32])
def test_pad_to_block_rounds_up_to_the_aes_block_size(size):
    padded = pad_to_block(b"\xaa" * size)
    assert len(padded) % AES_BLOCK_SIZE == 0
    assert len(padded) >= size
    assert padded[:size] == b"\xaa" * size


def test_pad_to_block_leaves_aligned_input_untouched():
    data = b"\xaa" * 32
    assert pad_to_block(data) is data


def test_raw_cipher_roundtrip():
    cipher = RawKeyCipher(bytes(range(16)))
    plaintext = b"\x01\x02\x03\x04" * 4
    assert cipher.decrypt(cipher.encrypt(plaintext)) == plaintext


def test_raw_cipher_pads_short_plaintext():
    cipher = RawKeyCipher(bytes(range(16)))
    assert len(cipher.encrypt(b"short")) == AES_BLOCK_SIZE


def test_raw_cipher_is_deterministic_ecb():
    cipher = RawKeyCipher(bytes(range(16)))
    assert cipher.encrypt(b"\x00" * 16) == cipher.encrypt(b"\x00" * 16)


def test_different_keys_produce_different_ciphertext():
    a = RawKeyCipher(bytes(range(16))).encrypt(b"\x00" * 16)
    b = RawKeyCipher(bytes(range(16, 32))).encrypt(b"\x00" * 16)
    assert a != b


@pytest.mark.parametrize("size", [0, 15, 17, 32])
def test_raw_cipher_rejects_wrong_key_lengths(size):
    with pytest.raises(ValueError, match="AES-128 key must be"):
        RawKeyCipher(b"\x00" * size)


def test_raw_cipher_rejects_unaligned_ciphertext():
    cipher = RawKeyCipher(bytes(range(16)))
    with pytest.raises(ValueError, match="not multiple of"):
        cipher.decrypt(b"\x00" * 17)


# --------------------------------------------------------------------------
# Key derivation
# --------------------------------------------------------------------------


def test_type2_key_is_the_hex_decoded_access_code():
    assert key_from_type2_hex(TYPE2_KEY) == bytes(range(16))


@pytest.mark.parametrize("bad", ["", "00", "0" * 31, "0" * 33])
def test_type2_key_must_be_32_hex_characters(bad):
    with pytest.raises(ValueError, match="32 hex chars"):
        key_from_type2_hex(bad)


def test_type2_key_must_be_valid_hex():
    with pytest.raises(ValueError, match="valid hex"):
        key_from_type2_hex("z" * 32)


def test_type1_key_repeats_eight_chars_four_times():
    assert key_from_type1_string("12345678") == bytes.fromhex("12345678" * 4)


def test_type1_key_ignores_characters_past_the_eighth():
    assert key_from_type1_string("12345678999999") == key_from_type1_string("12345678")


def test_type1_key_alias_is_retained_for_compatibility():
    assert key_from_type1_integration_id is key_from_type1_string


@pytest.mark.parametrize("bad", ["", "1234567"])
def test_type1_key_requires_at_least_eight_characters(bad):
    with pytest.raises(ValueError, match="at least 8 chars"):
        key_from_type1_string(bad)


def test_type1_key_requires_hex_decodable_digits():
    with pytest.raises(ValueError, match="hex-decodable"):
        key_from_type1_string("zzzzzzzz")


# --------------------------------------------------------------------------
# Type 2 handshake
# --------------------------------------------------------------------------


def test_type2_initializer_is_16_random_bytes():
    handler = Type2EncryptionHandler(TYPE2_KEY)
    first = handler.configure_inbound()
    second = Type2EncryptionHandler(TYPE2_KEY).configure_inbound()
    assert len(first) == Type2EncryptionHandler.INITIALIZER_LEN == 16
    assert first != second


def test_type2_activity_flags_track_configuration():
    handler = Type2EncryptionHandler(TYPE2_KEY)
    assert not handler.is_inbound_active
    assert not handler.is_outbound_active
    handler.configure_inbound()
    assert handler.is_inbound_active
    handler.configure_outbound(b"\x00" * 16)
    assert handler.is_outbound_active


def test_type2_peers_agree_on_session_keys():
    """The panel's outbound key must match our inbound key, and vice versa."""
    us = Type2EncryptionHandler(TYPE2_KEY)
    panel = Type2EncryptionHandler(TYPE2_KEY)

    our_init = us.configure_inbound()
    panel_init = panel.configure_inbound()
    us.configure_outbound(panel_init)
    panel.configure_outbound(our_init)

    plaintext = b"hello panel\x00\x00\x00\x00\x00"
    assert panel.decrypt(us.encrypt(plaintext)) == plaintext
    assert us.decrypt(panel.encrypt(plaintext)) == plaintext


def test_type2_mismatched_access_keys_do_not_interoperate():
    us = Type2EncryptionHandler(TYPE2_KEY)
    panel = Type2EncryptionHandler("ff" * 16)
    us.configure_outbound(panel.configure_inbound())
    panel.configure_outbound(us.configure_inbound())
    assert panel.decrypt(us.encrypt(b"\x00" * 16)) != b"\x00" * 16


@pytest.mark.parametrize("size", [0, 15, 17, 48])
def test_type2_rejects_a_wrong_sized_remote_initializer(size):
    handler = Type2EncryptionHandler(TYPE2_KEY)
    with pytest.raises(ValueError, match="must be 16 bytes"):
        handler.configure_outbound(b"\x00" * size)


# --------------------------------------------------------------------------
# Type 1 handshake
# --------------------------------------------------------------------------


def test_type1_initializer_is_48_bytes():
    handler = Type1EncryptionHandler(T1_INTEGRATION_ID, T1_ACCESS_CODE)
    assert len(handler.configure_inbound()) == Type1EncryptionHandler.INITIALIZER_LEN


def test_type1_check_bytes_derive_the_session_key():
    handler = Type1EncryptionHandler(T1_INTEGRATION_ID, T1_ACCESS_CODE)
    initializer = handler.configure_inbound()
    handler.configure_outbound(initializer)

    plaintext = b"\x11" * 16
    assert handler.decrypt(handler.encrypt(plaintext)) == plaintext


def test_type1_rejects_a_corrupted_initializer():
    handler = Type1EncryptionHandler(T1_INTEGRATION_ID, T1_ACCESS_CODE)
    initializer = bytearray(handler.configure_inbound())
    initializer[0] ^= 0xFF
    with pytest.raises(ValueError, match="check-byte mismatch"):
        handler.configure_outbound(bytes(initializer))


def test_type1_rejects_wrong_credentials():
    honest = Type1EncryptionHandler(T1_INTEGRATION_ID, T1_ACCESS_CODE)
    impostor = Type1EncryptionHandler("99999999AAAA", "99999999")
    with pytest.raises(ValueError, match="check-byte mismatch"):
        impostor.configure_outbound(honest.configure_inbound())


@pytest.mark.parametrize("size", [0, 16, 32, 47, 49])
def test_type1_rejects_a_wrong_sized_remote_initializer(size):
    handler = Type1EncryptionHandler(T1_INTEGRATION_ID, T1_ACCESS_CODE)
    with pytest.raises(ValueError, match="must be 48 bytes"):
        handler.configure_outbound(b"\x00" * size)


# --------------------------------------------------------------------------
# Lifecycle guards
# --------------------------------------------------------------------------


def test_encrypt_before_configure_outbound_is_an_error():
    handler = Type2EncryptionHandler(TYPE2_KEY)
    with pytest.raises(RuntimeError, match="outbound not configured"):
        handler.encrypt(b"\x00" * 16)


def test_decrypt_before_configure_inbound_is_an_error():
    handler = Type2EncryptionHandler(TYPE2_KEY)
    with pytest.raises(RuntimeError, match="inbound not configured"):
        handler.decrypt(b"\x00" * 16)


# --------------------------------------------------------------------------
# Documented factory defaults
# --------------------------------------------------------------------------


def test_documented_factory_defaults():
    assert NEOHUB_DEFAULT_TYPE2_HEX == "12345678123456781234567812345678"
    assert bytes.fromhex(NEOHUB_DEFAULT_TYPE2_HEX) == NEOHUB_DEFAULT_KEY
    assert NEOHUB_DEFAULT_TYPE1_ACCESS_CODE == "12345678"
