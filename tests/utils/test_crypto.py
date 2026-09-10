"""Unit tests for cryptographic ciphers, RC4, VRF, Byse PoW solvers, and Miruro utilities."""

from anime_extensions.utils.crypto import (
    b64url_decode,
    b64url_encode,
    generate_byse_keypair_and_attestation,
    miruro_build_pipe_url,
    miruro_build_proxied_url,
    miruro_decrypt_pipe,
    miruro_fnv1a_mod2,
    miruro_xor_encode,
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


# ── Miruro crypto tests ───────────────────────────────────────────────────────


def test_miruro_xor_encode_deterministic():
    """Test Miruro XOR encoding produces consistent base64url output."""
    key = bytes.fromhex("a54d389c18527d9fd3e7f0643e27edbe")
    result = miruro_xor_encode("https://cdn.example/video.m3u8", key)

    assert isinstance(result, str)
    assert len(result) > 0
    assert "=" not in result  # base64url without padding
    # Deterministic: same input always produces same output
    assert miruro_xor_encode("https://cdn.example/video.m3u8", key) == result


def test_miruro_fnv1a_mod2_deterministic():
    """Test FNV-1a 32-bit hash mod 2 returns consistent 0 or 1."""
    # Same seed always returns same result
    seed = "episode-id-123|154587"
    result = miruro_fnv1a_mod2(seed)

    assert result in (0, 1)
    assert miruro_fnv1a_mod2(seed) == result

    # Empty seed defaults to 0
    assert miruro_fnv1a_mod2("") == 0

    # Different seeds may return different values
    result2 = miruro_fnv1a_mod2("different-seed")
    assert result2 in (0, 1)


def test_miruro_build_proxied_url_wraps_stream():
    """Test Miruro proxy URL wraps stream and referer through vault."""
    proxied = miruro_build_proxied_url(
        stream_url="https://cdn.kwik.cx/video.m3u8",
        referer="https://kwik.cx/",
        proxy_seed="ep-123|999",
    )

    # Must contain one of the vault hosts
    assert "vault01.ultracloud.cc" in proxied or "vault02.ultracloud.cc" in proxied
    # Must end with /pl.m3u8
    assert proxied.endswith("/pl.m3u8")
    # Must not contain the original URL in plaintext
    assert "cdn.kwik.cx" not in proxied


def test_miruro_build_pipe_url_encodes_payload():
    """Test pipe URL builds base64url-encoded JSON payload."""
    import json

    url = miruro_build_pipe_url(
        "https://www.miruro.tv",
        "info/154587",
        "GET",
        {"anilistId": 154587},
    )

    assert url.startswith("https://www.miruro.tv/api/secure/pipe?e=")

    # Extract and decode the payload
    encoded = url.split("?e=", 1)[1]
    decoded = b64url_decode(encoded)
    payload = json.loads(decoded.decode("utf-8"))

    assert payload["path"] == "info/154587"
    assert payload["method"] == "GET"
    assert payload["query"]["anilistId"] == 154587
    assert payload["version"] == "0.2.0"
    assert "timestamp" in payload


def test_miruro_decrypt_pipe_xor_gzip():
    """Test Miruro pipe response decryption (XOR + GZIP)."""
    import gzip

    # Simulate an obfuscated response: plain text → gzip → XOR → base64url
    plaintext = '{"media":{"id":154587,"title":{"userPreferred":"Frieren"}}}'
    gzipped = gzip.compress(plaintext.encode("utf-8"))

    key = bytes.fromhex("71951034f8fbcf53d89db52ceb3dc22c")
    xor_data = bytearray(gzipped)
    for i in range(len(xor_data)):
        xor_data[i] ^= key[i % len(key)]

    encoded = b64url_encode(bytes(xor_data))

    # Decrypt with header="2" (obfuscated)
    decrypted = miruro_decrypt_pipe(encoded, obfuscated_header="2")
    assert decrypted == plaintext

    # Passthrough when not obfuscated
    assert miruro_decrypt_pipe("plain text", obfuscated_header="1") == "plain text"
