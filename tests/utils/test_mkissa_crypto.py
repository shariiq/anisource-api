"""Unit tests for MKissa cryptographic primitives."""

import base64
import hashlib
import hmac
import json
from unittest.mock import patch

from anime_extensions.utils.mkissa_crypto import MKissaCrypto


def test_sha256_hex():
    """Verify SHA-256 hex hashing."""
    test_val = "test_string"
    expected = hashlib.sha256(test_val.encode("utf-8")).hexdigest()
    assert MKissaCrypto.sha256_hex(test_val) == expected


def test_derive_mask_valid():
    """Verify mask derivation with valid inputs."""
    build_id = "build123"
    # Mock seeds to be valid base64
    valid_seeds = [base64.b64encode(b"12345678").decode() for _ in range(4)]

    mask = MKissaCrypto.derive_mask(build_id, valid_seeds)
    assert mask is not None
    assert len(mask) == 32


def test_derive_mask_invalid_seeds():
    """Verify derive_mask returns None on invalid inputs."""
    # Wrong number of seeds
    assert MKissaCrypto.derive_mask("bid", ["s1", "s2", "s3"]) is None
    # Invalid base64 seed
    assert MKissaCrypto.derive_mask("bid", ["!!!", "s2", "s3", "s4"]) is None
    # Empty build_id
    assert MKissaCrypto.derive_mask("", ["s1", "s2", "s3", "s4"]) is None


def test_derive_key():
    """Verify AES key derivation (XOR of mask and partB)."""
    mask = b"A" * 32
    part_b = b"B" * 32
    key = MKissaCrypto.derive_key(mask, part_b)

    assert len(key) == 32
    # XOR result should be constant
    assert key[0] == ord("A") ^ ord("B")


def test_boot_token():
    """Verify HMAC boot token generation."""
    mask = b"test_mask_32_bytes_long_constant!!"
    build_id = "build_id"
    epoch = 12345
    key_group = "mkissa"
    referer_host = "mkissa.to"
    lane = "k7"

    token = MKissaCrypto.boot_token(mask, build_id, epoch, key_group, referer_host, lane)

    # Manual verification
    boot_prefix = "FD0xZhgI:"
    inner = hmac.new(mask, f"{boot_prefix}{build_id}".encode(), hashlib.sha256).digest()
    message = f"{referer_host}.{epoch}.{key_group}.{lane}.{build_id}"
    expected = hmac.new(inner, message.encode("utf-8"), hashlib.sha256).hexdigest()

    assert token == expected


def test_build_aa_req_and_decrypt():
    """Verify aaReq encryption and subsequent decryption."""
    key = b"A" * 32
    epoch = 12345
    build_id = "build_id"
    query_hash = "hash"
    lane = "k7"

    with patch("time.time", return_value=1000.0):
        aa_req_b64 = MKissaCrypto.build_aa_req(key, epoch, build_id, query_hash, lane)

    decrypted = MKissaCrypto.decrypt(aa_req_b64, key)
    assert decrypted is not None

    payload = json.loads(decrypted)
    assert payload["epoch"] == epoch
    assert payload["buildId"] == build_id
    assert payload["qh"] == query_hash
    assert payload["k"] == lane


def test_decrypt_source_url():
    """Verify XOR source URL decryption."""
    # Test case 1: Specific prefix '#' (keyType 0)
    # XOR mask 0 is derived from "allanimenews"
    mask0 = 0
    for char in "allanimenews":
        mask0 ^= ord(char)

    url = "https://example.com"
    bytes_url = url.encode("utf-8")
    encrypted_bytes = bytes([b ^ mask0 for b in bytes_url])
    encrypted_hex = encrypted_bytes.hex()

    assert MKissaCrypto.decrypt_source_url(f"#{encrypted_hex}") == url

    # Test case 2: No prefix (try all masks)
    assert MKissaCrypto.decrypt_source_url(f"#{encrypted_hex}") == url  # should work as prefix #
    assert MKissaCrypto.decrypt_source_url(encrypted_hex) == url  # should work via trial


def test_decrypt_source_url_preserves_plain_url() -> None:
    """Plain source URLs are not affected by frontend storage configuration."""
    url = "https://watchanime.uns.bio/#6kxskx"

    assert MKissaCrypto.decrypt_source_url(url) == url


def test_decrypt_source_url_invalid():
    """Verify decryption failure for invalid inputs."""
    # Odd length hex
    assert MKissaCrypto.decrypt_source_url("#abc") == "#abc"
    # Non-hex
    assert MKissaCrypto.decrypt_source_url("#xyz") == "#xyz"
