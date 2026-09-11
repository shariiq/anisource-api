"""Dean Edwards P.A.C.K.E.R. JavaScript unpacker.

Provides both functional `unpack_packer` and object-oriented `Unpacker` helper.
"""

from __future__ import annotations

import re

_PACKED_RE = re.compile(
    r"\}\s*\(\s*[\"'](?P<payload>.*?)[\"']\s*,\s*(?P<radix>\d+)\s*,\s*(?P<count>\d+)?\s*,\s*[\"'](?P<symbols>.*?)[\"']\.split\([\"']\|[\"']\)",
    re.DOTALL,
)


def unpack_packer(script: str) -> str | None:
    """Return unpacked P.A.C.K.E.R. source, or ``None`` for unsupported/unpacked input."""
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


class Unpacker:
    """Helper to detect and unpack Dean Edwards packed JavaScript."""

    @staticmethod
    def is_packed(js: str) -> bool:
        """Check if the provided javascript is packed."""
        return "eval(function(p,a,c,k,e,d)" in js or "eval(function(p,a,c,k,e,r)" in js

    @staticmethod
    def unpack(js: str) -> str:
        """Unpack Dean Edwards packed JavaScript."""
        if not Unpacker.is_packed(js):
            return js

        unpacked = unpack_packer(js)
        if unpacked is not None:
            return Unpacker.unpack(unpacked) if Unpacker.is_packed(unpacked) else unpacked

        # Fallback regex if standard format differs
        func_match = re.search(
            r"\}\s*\(\s*['\"](.*?)['\"]\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*['\"](.*?)['\"]\.split\(['\"]\|['\"]\)",
            js,
            re.DOTALL,
        )
        if not func_match:
            p_match = re.search(r"return p}\s*\('(.*?)',\s*(\d+),\s*(\d+),\s*'(.*?)'\.split", js)
            if p_match:
                p, a, c, k = p_match.groups()
                a = int(a)
                c = int(c)
            else:
                return js
        else:
            p, a, c, k = func_match.groups()
            a = int(a)
            c = int(c)

        keywords = k.split("|")
        p = p.replace(r"\'", "'").replace(r"\\", "\\")

        dictionary: dict[str, str] = {}
        for i in range(c):
            val = Unpacker._radix_str(i, a)
            if i < len(keywords) and keywords[i]:
                dictionary[val] = keywords[i]
            else:
                dictionary[val] = val

        result = []
        i = 0
        while i < len(p):
            if p[i].isalnum() or p[i] == "_":
                word = p[i]
                i += 1
                while i < len(p) and (p[i].isalnum() or p[i] == "_"):
                    word += p[i]
                    i += 1
                result.append(dictionary.get(word, word))
            else:
                result.append(p[i])
                i += 1

        unpacked_str = "".join(result)
        return Unpacker.unpack(unpacked_str) if Unpacker.is_packed(unpacked_str) else unpacked_str

    @staticmethod
    def _radix_str(num: int, radix: int) -> str:
        """Convert an integer to a string in a given radix/base (up to 62)."""
        if num == 0:
            return "0"
        chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        res = ""
        while num > 0:
            res = chars[num % radix] + res
            num //= radix
        return res
