"""MKissa cryptographic primitives for API request and response handling."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Constants from MKissa.kt and MKissaCrypto.kt
XOR_KEYS = [
    "allanimenews",
    "1234567890123456789",
    "1234567890123456789012345",
    "s5feqxw21",
    "feqx1",
]

def _compute_mask(key: str) -> int:
    mask = 0
    for char in key:
        mask ^= ord(char)
    return mask

XOR_MASKS = [_compute_mask(key) for key in XOR_KEYS]

# Crypto Constants
HASH_ALGO = hashlib.sha256
HMAC_ALGO = hashlib.sha256
IV_SIZE = 12
HEADER_SIZE = 1 + IV_SIZE  # 1 byte version + 12 bytes IV
TAG_LENGTH = 16  # 128 bits / 8

class MKissaCrypto:
    """Low-level cryptographic utilities for MKissa."""

    @staticmethod
    def sha256_hex(value: str) -> str:
        """Return SHA-256 hash of a string in hex."""
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def derive_mask(build_id: str, seeds: list[str]) -> bytes | None:
        """
        Derive the crypto mask from build_id and seeds.

        Matches Kotlin:
        stream = ByteArray(32) { i -> (buildId[i % buildId.length].code xor ((i * SALT_MUL + SALT_ADD) and 0xFF)).toByte() }
        mask = ByteArray(32)
        for (index in seeds.indices) {
            bytes = Base64.decode(seeds[index])
            for (offset in 0 until SEED_SIZE) {
                mask[base + offset] = (bytes[offset] xor stream[base + offset] xor ((index * FRAG_MUL + offset * FRAG_ADD) and 0xFF))
            }
        }
        """
        if not build_id or len(seeds) != 4:
            return None

        salt_mul, salt_add = 6, 244
        frag_mul, frag_add = 190, 88
        key_size = 32
        seed_size = key_size // 4

        # Step 1: Create the stream
        stream = bytearray(key_size)
        for i in range(key_size):
            char_code = ord(build_id[i % len(build_id)])
            stream[i] = (char_code ^ ((i * salt_mul + salt_add) & 0xFF)) & 0xFF

        # Step 2: Derive mask from seeds
        mask = bytearray(key_size)
        for index, seed in enumerate(seeds):
            try:
                seed_bytes = base64.b64decode(seed)
            except Exception:
                return None

            if len(seed_bytes) < seed_size:
                return None

            base = index * seed_size
            for offset in range(seed_size):
                val = (
                    (seed_bytes[offset] & 0xFF) ^
                    (stream[base + offset] & 0xFF) ^
                    ((index * frag_mul + offset * frag_add) & 0xFF)
                )
                mask[base + offset] = val & 0xFF

        if all(b == 0 for b in mask):
            return None

        return bytes(mask)

    @staticmethod
    def derive_key(mask: bytes, part_b: bytes) -> bytes:
        """Derive the final AES key by XORing mask and partB."""
        key_bytes = bytearray(32)
        for i in range(32):
            key_bytes[i] = (part_b[i] & 0xFF) ^ (mask[i % len(mask)] & 0xFF)
        return bytes(key_bytes)

    @staticmethod
    def boot_token(mask: bytes, build_id: str, epoch: int, key_group: str, referer_host: str, lane: str) -> str:
        """
        Generate a boot token for the handshake.

        Matches Kotlin:
        inner = hmac(mask, "FD0xZhgI:" + buildId)
        message = refererHost + "." + epoch + "." + keyGroup + "." + lane + "." + buildId
        return hmac(inner, message).toHex()
        """
        boot_prefix = "FD0xZhgI:"
        inner = hmac.new(mask, f"{boot_prefix}{build_id}".encode("utf-8"), HMAC_ALGO).digest()

        message = f"{referer_host}.{epoch}.{key_group}.{lane}.{build_id}"
        return hmac.new(inner, message.encode("utf-8"), HMAC_ALGO).hexdigest()

    @staticmethod
    def build_aa_req(key: bytes, epoch: int, build_id: str, query_hash: str, lane: str) -> str:
        """
        Build and encrypt the aaReq payload.

        Matches Kotlin:
        iv = sha256(epoch:buildId:queryHash:ts:lane).copyOfRange(0, 12)
        payload = json(v=1, ts=ts, epoch=epoch, buildId=buildId, qh=queryHash, k=lane)
        cipher = AES/GCM/NoPadding
        blob = [1] + iv + ciphertext
        """
        window_ms = 5 * 60 * 1000
        ts = int(time.time() * 1000 // window_ms * window_ms)

        # IV derivation
        iv_input = f"{epoch}:{build_id}:{query_hash}:{ts}:{lane}"
        iv = hashlib.sha256(iv_input.encode("utf-8")).digest()[:IV_SIZE]

        # Payload
        payload = {
            "v": 1,
            "ts": ts,
            "epoch": epoch,
            "buildId": build_id,
            "qh": query_hash,
            "k": lane,
        }
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        # Encrypt
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(iv, payload_bytes, None)

        # Construct blob: [version (1)] + [IV (12)] + [ciphertext]
        blob = bytearray([1]) + iv + ciphertext
        return base64.b64encode(blob).decode("ascii")

    @staticmethod
    def decrypt(base64_payload: str, key: bytes) -> str | None:
        """Decrypt an AES-GCM encrypted payload."""
        try:
            blob = base64.b64decode(base64_payload)
            if len(blob) < HEADER_SIZE:
                return None

            # blob[0] is version, blob[1:13] is IV
            iv = blob[1 : 1 + IV_SIZE]
            ciphertext = blob[1 + IV_SIZE :]

            aesgcm = AESGCM(key)
            decrypted_bytes = aesgcm.decrypt(iv, ciphertext, None)
            return decrypted_bytes.decode("utf-8")
        except Exception:
            return None

    @staticmethod
    def decrypt_source_url(url: str) -> str:
        """
        Decrypt obfuscated source URLs.

        Matches Kotlin:
        if startWith("--") -> keyType = 3
        if startWith("#-") -> keyType = 2
        if startWith("##") -> keyType = 1
        if startWith("-#") -> keyType = 4
        if startWith("#") -> keyType = 0
        else -> keyType = null (try all masks)
        """
        if url.startswith("--"):
            payload, key_type = url[2:], 3
        elif url.startswith("#-"):
            payload, key_type = url[2:], 2
        elif url.startswith("##"):
            payload, key_type = url[2:], 1
        elif url.startswith("-#"):
            payload, key_type = url[2:], 4
        elif url.startswith("#"):
            payload, key_type = url[1:], 0
        else:
            payload, key_type = url, None

        if len(payload) % 2 != 0:
            return url

        # Convert hex payload to bytes
        try:
            bytes_payload = bytes.fromhex(payload)
        except ValueError:
            return url

        if key_type is not None:
            # Use specific mask
            if key_type >= len(XOR_MASKS):
                return url
            mask = XOR_MASKS[key_type]
            return "".join(chr((b & 0xFF) ^ mask) for b in bytes_payload)

        # Try all masks
        for mask in XOR_MASKS:
            decoded = "".join(chr((b & 0xFF) ^ mask) for b in bytes_payload)
            if "/clock" in decoded or "http" in decoded:
                return decoded

        return url
