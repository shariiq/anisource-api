"""Unit tests for cryptographic ciphers, RC4, VRF, and Byse PoW solvers."""

import pytest

from anime_extensions.exceptions import CryptoError
from anime_extensions.utils.crypto import (
    b64url_decode,
    b64url_encode,
    generate_byse_keypair_and_attestation,
    rc4_encrypt,
    solve_byse_pow,
    vrf_encrypt,
)


def test_b64url_roundtrip():
    """Test base64url encode and decode parity."""
    data = b"Hello, World! Testing Base64 URL encode without padding."
    encoded = b64url_encode(data)
    assert "=" not in encoded
    decoded = b64url_decode(encoded)
    assert decoded == data


def test_rc4_cipher_symmetry():
    """Test RC4 encrypt/decrypt symmetric identity."""
    key = "secret-stream-key"
    plaintext = "Anime streaming URL path: /watch/naruto-123"

    ciphertext = rc4_encrypt(key, plaintext)
    assert ciphertext != plaintext

    # Decrypting ciphertext with the same key gives back original plaintext
    recovered = rc4_encrypt(key, ciphertext)
    assert recovered == plaintext


def test_vrf_encryption():
    """Test deterministic VRF cipher generation."""
    res = vrf_encrypt("naruto", key="test-key")
    assert isinstance(res, str)
    assert len(res) > 0
    # Consistent output for deterministic inputs
    assert vrf_encrypt("naruto", key="test-key") == res


def test_byse_pow_solver():
    """Test ChaCha buffer mix PoW solver with low difficulty."""
    # Difficulty 1 is fast and deterministic (verifies solver execution path)
    nonce = "test-nonce-12345"
    solution = solve_byse_pow(nonce, difficulty=1, max_iterations=5000)
    assert solution.isdigit()


def test_byse_keypair_attestation():
    """Test ECDSA P-256 keypair generation and JWK signature."""
    nonce = "session-nonce-xyz"
    jwk, signature = generate_byse_keypair_and_attestation(nonce)

    assert jwk["kty"] == "EC"
    assert jwk["crv"] == "P-256"
    assert "x" in jwk
    assert "y" in jwk
    assert isinstance(signature, str)
    assert len(signature) > 0
