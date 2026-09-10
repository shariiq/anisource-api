"""Anikoto cryptographic utilities."""

from __future__ import annotations

import base64
from urllib.parse import quote


def _rc4_encrypt(key: str, data: str) -> str:
    """RC4 stream cipher."""
    key_bytes = key.encode("utf-8")
    data_bytes = data.encode("utf-8")

    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key_bytes[i % len(key_bytes)]) % 256
        S[i], S[j] = S[j], S[i]

    out = bytearray(len(data_bytes))
    i = 0
    j = 0
    for idx, byte in enumerate(data_bytes):
        i = (i + 1) % 256
        j = (S[i]) % 256
        S[i], S[j] = S[j], S[i]
        out[idx] = byte ^ S[(S[i] + S[j]) % 256]

    return base64.urlsafe_b64encode(out).decode("utf-8").rstrip("=")


def _exchange(input_str: str, keys: list[str]) -> str:
    """Character substitution."""
    key1, key2 = keys[0], keys[1]
    result = []
    for ch in input_str:
        idx = key1.find(ch)
        result.append(key2[idx] if idx != -1 else ch)
    return "".join(result)


def vrf_encrypt(input_str: str) -> str:
    """Encrypt string using Anikoto's VRF cipher."""
    _EXCHANGE_KEY_1 = ["AP6GeR8H0lwUz1", "UAz8Gwl10P6ReH"]
    _KEY_1 = "ItFKjuWokn4ZpB"
    _KEY_2 = "fOyt97QWFB3"
    _EXCHANGE_KEY_2 = ["1majSlPQd2M5", "da1l2jSmP5QM"]
    _EXCHANGE_KEY_3 = ["CPYvHj09Au3", "0jHA9CPYu3v"]
    _KEY_3 = "736y1uTJpBLUX"

    vrf = input_str
    vrf = _exchange(vrf, _EXCHANGE_KEY_1)
    vrf = _rc4_encrypt(_KEY_1, vrf)
    vrf = _rc4_encrypt(_KEY_2, vrf)
    vrf = _exchange(vrf, _EXCHANGE_KEY_2)
    vrf = _exchange(vrf, _EXCHANGE_KEY_3)
    vrf = vrf[::-1]
    vrf = _rc4_encrypt(_KEY_3, vrf)
    vrf = base64.urlsafe_b64encode(vrf.encode("utf-8")).decode("utf-8").rstrip("=")
    return quote(vrf, safe="")
