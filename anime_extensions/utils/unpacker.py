"""Pure Python port of Dean Edwards Packer JS decoder.

Equivalent to lib/unpacker/src/eu/kanade/tachiyomi/lib/unpacker/Unpacker.kt.
"""

from __future__ import annotations

import re


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

        # Extract the payload function arguments (p, a, c, k, e, d)
        func_match = re.search(r"}\s*\('(.*)',\s*(\d+),\s*(\d+),\s*'([^']+)'\.split\('\|'\)", js)
        if not func_match:
            func_match = re.search(
                r"\}?\s*\('(.*)',\s*(\d+),\s*(\d+),\s*'([^']+)'\.split\('\|'\)", js
            )
            if not func_match:
                # Try finding based on common format
                func_match = re.search(
                    r"\}\s*\(\s*'([^']*)'\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'([^']+)'\.split\('\|'\)",
                    js,
                )

        if not func_match:
            # Fallback if standard regex fails
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
        p = p.replace("\\'", "'").replace("\\\\", "\\")

        # Create mapping dictionary
        dictionary: dict[str, str] = {}
        for i in range(c):
            val = Unpacker._radix_str(i, a)
            if i < len(keywords) and keywords[i]:
                dictionary[val] = keywords[i]
            else:
                dictionary[val] = val

        # Simple tokenizer
        result = []
        i = 0
        while i < len(p):
            # Check if it's part of a word
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

        unpacked = "".join(result)
        # Some packers wrap with another eval, recurse if needed
        return Unpacker.unpack(unpacked) if Unpacker.is_packed(unpacked) else unpacked

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
