"""Cryptographic primitives and ciphers for anime sources and extractors."""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import quote

from ..exceptions import CryptoError

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


def b64url_decode(s: str) -> bytes:
    """Decode base64url string with or without padding."""
    s = s.replace("-", "+").replace("_", "/")
    padding = len(s) % 4
    if padding == 2:
        s += "=="
    elif padding == 3:
        s += "="
    return base64.b64decode(s)


def b64url_encode(b: bytes) -> str:
    """Encode bytes into unpadded base64url string."""
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


# =====================================================================
# RC4 & VRF Cipher
# =====================================================================


def rc4_encrypt(key: str, data: str) -> str:
    """Perform RC4 stream cipher encryption/decryption on latin-1 / ISO-8859-1 strings.

    Matches Kotlin VrfCodec RC4 byte-to-char transformation.
    """
    key_bytes = key.encode("utf-8")
    data_chars = [ord(c) for c in data]

    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key_bytes[i % len(key_bytes)]) % 256
        s[i], s[j] = s[j], s[i]

    out = []
    i = 0
    j = 0
    for code in data_chars:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        out.append(chr(code ^ s[(s[i] + s[j]) % 256]))

    return "".join(out)


def vrf_encrypt(input_str: str, key: str = "simple-hash") -> str:
    """Encrypt string using VRF cipher (RC4 -> Latin1 -> Base64 -> URL encoded).

    Parity with Kotlin AniWaves VrfCodec.
    """
    rc4_res = rc4_encrypt(key, input_str)
    b64 = base64.b64encode(rc4_res.encode("latin-1")).decode("ascii")
    return quote(b64, safe="")


# =====================================================================
# Byse / Filemoon PoW Solver & Decryption
# =====================================================================


def _rotl32(value: int, shift: int) -> int:
    return ((value << shift) | (value >> (32 - shift))) & 0xFFFFFFFF


def _count_leading_zeros32(val: int) -> int:
    val &= 0xFFFFFFFF
    if val == 0:
        return 32
    return 32 - val.bit_length()


def solve_byse_pow(nonce: str, difficulty: int, max_iterations: int = 2_000_000) -> str:
    """Solve the Byse/BYFMS proof-of-work challenge.

    Port of the Kotlin ByseExtractor ChaCha-like buffer mix hash algorithm.
    """
    prefix = f"{nonce}:".encode("latin-1")
    buffer_size = 512
    buffer_mask = 511
    init_const = 2654435761
    final_const = 2246822519
    mask32 = 0xFFFFFFFF

    buf = [0] * buffer_size

    for counter in range(max_iterations + 1):
        input_bytes = prefix + str(counter).encode("latin-1")

        s0 = 1779033703
        s1 = 3144134277
        s2 = 1013904242
        s3 = 2773480762

        def mix() -> None:
            nonlocal s0, s1, s2, s3
            s0 = (s0 + s1) & mask32
            s3 = _rotl32(s3 ^ s0, 16)
            s2 = (s2 + s3) & mask32
            s1 = _rotl32(s1 ^ s2, 12)
            s0 = (s0 + s1) & mask32
            s3 = _rotl32(s3 ^ s0, 8)
            s2 = (s2 + s3) & mask32
            s1 = _rotl32(s1 ^ s2, 7)

        for b in input_bytes:
            s0 = (s0 + b) & mask32
            s0 = _rotl32(s0, 7)
            mix()

        for _ in range(8):
            mix()

        for i in range(buffer_size):
            mix()
            buf[i] = (s0 ^ s2) & mask32

        for _ in range(2):
            for si in range(buffer_size):
                a = buf[si] & buffer_mask
                c = (buf[si] + buf[a]) & mask32
                c = _rotl32(c, 13)
                c = (c ^ ((buf[(si + 1) & buffer_mask] * init_const) & mask32)) & mask32
                buf[si] = c
                s0 = (s0 ^ c) & mask32
                mix()

        mix()

        out_val = s0
        for ci in range(64):
            d = buf[ci]
            out_val = (out_val + d) & mask32
            out_val = _rotl32(out_val, 5)
            out_val = (out_val ^ ((d * final_const) & mask32)) & mask32
        out_val = (out_val ^ s2) & mask32

        if _count_leading_zeros32(out_val) >= difficulty:
            return str(counter)

    raise CryptoError(f"Byse: PoW exhausted ({max_iterations} iterations, difficulty={difficulty})")


def decrypt_byse_playback(playback: dict[str, Any]) -> str:
    """Decrypt the Byse encrypted playback response using AES-GCM (128-bit tag).

    Parity with Kotlin ByseExtractor.decrypt().
    """
    if not HAS_CRYPTOGRAPHY:
        raise CryptoError("Byse: cryptography package required for AES-GCM decryption")

    key_parts_raw = playback.get("key_parts", [])
    if not key_parts_raw:
        raise CryptoError("Byse: key_parts missing in encrypted playback")

    key_parts = [b64url_decode(k) for k in key_parts_raw]
    version_str = playback.get("version")
    if version_str is not None:
        try:
            version = int(version_str)
        except ValueError:
            version = 1

        if 1 <= version <= len(key_parts):
            key_bytes = key_parts[version - 1] + key_parts[len(key_parts) - version]
        else:
            key_bytes = b"".join(key_parts)
    else:
        key_bytes = b"".join(key_parts)

    payload_raw = playback.get("payload")
    iv_raw = playback.get("iv")
    if not payload_raw or not iv_raw:
        raise CryptoError("Byse: payload or iv missing in encrypted playback")

    payload_bytes = b64url_decode(payload_raw)
    iv_bytes = b64url_decode(iv_raw)

    if len(payload_bytes) < 16:
        raise CryptoError("Byse: payload too short (< 16 bytes for GCM tag)")

    try:
        aesgcm = AESGCM(key_bytes)
        decrypted = aesgcm.decrypt(iv_bytes, payload_bytes, None)
        return decrypted.decode("utf-8")
    except Exception as e:
        raise CryptoError(f"Byse: AES-GCM decryption failed: {e}") from e


def generate_byse_keypair_and_attestation(nonce: str) -> tuple[dict[str, Any], str]:
    """Generate EC P-256 keypair, sign the nonce with SHA256withECDSA, and return JWK + signature.

    Returns:
        tuple of (jwk_dict, base64url_signature)
    """
    if not HAS_CRYPTOGRAPHY:
        raise CryptoError("Byse: cryptography package required for ECDSA attestation")

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    public_numbers = public_key.public_numbers()

    # Padded 32-byte x and y coordinates
    x_bytes = public_numbers.x.to_bytes(32, byteorder="big")
    y_bytes = public_numbers.y.to_bytes(32, byteorder="big")

    jwk = {
        "alg": "ES256",
        "crv": "P-256",
        "ext": True,
        "key_ops": ["verify"],
        "kty": "EC",
        "x": b64url_encode(x_bytes),
        "y": b64url_encode(y_bytes),
    }

    signature = private_key.sign(
        nonce.encode("utf-8"),
        ec.ECDSA(hashes.SHA256()),
    )
    sig_b64 = b64url_encode(signature)

    return jwk, sig_b64
