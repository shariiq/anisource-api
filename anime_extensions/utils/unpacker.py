"""Dean Edwards P.A.C.K.E.R. JavaScript unpacker."""

from __future__ import annotations

import re

_PACKED_RE = re.compile(
    r"\}\s*\(\s*[\"'](?P<payload>.*?)[\"']\s*,\s*(?P<radix>\d+)\s*,\s*\d+\s*,\s*[\"'](?P<symbols>.*?)[\"']\.split\([\"']\|[\"']\)",
    re.DOTALL,
)


def unpack_packer(script: str) -> str | None:
    """Return unpacked P.A.C.K.E.R. source, or ``None`` for unsupported input."""
    match = _PACKED_RE.search(script)
    if not match:
        return None

    payload = match.group("payload")
    radix = int(match.group("radix"))
    symbols = match.group("symbols").split("|")

    def _parse_int(token: str, base: int) -> int:
        res = 0
        for char in token:
            if "0" <= char <= "9":
                digit = ord(char) - ord("0")
            elif "a" <= char <= "z":
                digit = ord(char) - ord("a") + 10
            elif "A" <= char <= "Z":
                digit = ord(char) - ord("A") + (10 if base <= 36 else 36)
            else:
                return -1
            if digit >= base:
                return -1
            res = res * base + digit
        return res

    def _replace_word(m: re.Match[str]) -> str:
        word = m.group(0)
        idx = _parse_int(word, radix)
        if 0 <= idx < len(symbols) and symbols[idx]:
            return symbols[idx]
        return word

    unpacked = re.sub(r"\b[0-9a-zA-Z]+\b", _replace_word, payload)
    return unpacked.replace(r"\'", "'").replace(r"\"", '"')
