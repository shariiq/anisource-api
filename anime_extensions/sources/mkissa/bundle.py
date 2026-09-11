"""Parser for MKissa crypto material embedded in obfuscated JavaScript."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ...utils.mkissa_crypto import MKissaCrypto

_IDENT = r"[$A-Za-z0-9_]+"
_CALL_PATTERN = rf"({_IDENT})\(\s*(-?\d+)\s*(?:,\s*(-?\d+)\s*)?\)"
_CALL_REGEX = re.compile(_CALL_PATTERN)
_TABLE_HEAD_REGEX = re.compile(
    rf"function ({_IDENT})\(\)\s*\{{\s*(?:const|let|var)\s+{_IDENT}\s*=\s*\["
)
_BASE_DECODER_REGEX = re.compile(
    rf"function ({_IDENT})\(({_IDENT})(?:,{_IDENT})*\)\{{return \2=\2-\(?([-\d+*\s]+?)\)?,({_IDENT})\(\)\[\2\]\}}"
)
_ALIAS_DECODER_REGEX = re.compile(
    rf"function ({_IDENT})\(({_IDENT})(?:,\s*({_IDENT}))?\)\{{\s*return ({_IDENT})\(\s*({_IDENT})\s*([-+])\s*(?:\{{.*?:\s*(-?\d+)\s*\}}\.[$A-Za-z0-9_]+|([-\d+*\s]+))\s*\)\s*\}}"
)
_ASSIGNMENT_REGEX_TEMPLATE = rf"\b{{name}}\s*=\s*({_CALL_PATTERN})\s*(?:,|;|\n)"
_ANY_ASSIGNMENT_REGEX = re.compile(rf"\b\w+\s*=\s*({_CALL_PATTERN})\s*(?:,|;|\n)")
_DEFAULT_PARAMETER_REGEX = re.compile(rf"function\s+({_IDENT})\s*\(\s*\w+\s*=\s*(\w+)\s*[,)]")
_ARRAY_REGEX = re.compile(r"=\[([^\]]+)\]")
_BUILD_ID_REGEX = re.compile(r"[A-Za-z0-9_-]{2,32}")
_SEED_REGEX = re.compile(r"[A-Za-z0-9+/]{11}=")
_TERM_REGEX = re.compile(r"[-+]*\d+(?:\*[-+]*\d+)*")


@dataclass(frozen=True, slots=True)
class MKissaConfig:
    salt_mul: int
    salt_add: int
    frag_mul: int
    frag_add: int
    boot_prefix: str
    join_char: str
    parts: tuple[str, ...]
    env_xor: int


@dataclass(frozen=True, slots=True)
class BuildInfo:
    """Frontend build identifier, seeds, and crypto constants."""

    build_id: str
    seeds: tuple[str, ...]
    config: MKissaConfig | None = None


@dataclass(frozen=True, slots=True)
class _BaseDecoder:
    table: str
    offset: int


@dataclass(frozen=True, slots=True)
class _AliasDecoder:
    base: str
    argument_index: int
    delta: int


class MKissaBundle:
    """Decode MKissa's rotated JavaScript string tables."""

    @classmethod
    def parse(cls, js: str) -> BuildInfo | None:
        """Extract a build identifier and seed fragments from a crypto chunk."""
        tables, bases, aliases = cls._decoders_from(js)
        parsed_seed_result = cls._find_seeds_and_rotation(js, tables, bases, aliases)
        if parsed_seed_result is None:
            # Fall back to extract build id and seeds individually
            build_id = cls._extract_build_id(js, tables, bases, aliases)
            if build_id is None:
                return None
            seeds = cls._extract_seeds(js, tables, bases, aliases)
            if seeds is None:
                return None
            return BuildInfo(build_id, tuple(seeds))

        seeds, rotation = parsed_seed_result
        build_id = cls._extract_build_id_with_rotation(js, tables, bases, aliases, rotation)
        if build_id is None:
            build_id = cls._extract_build_id(js, tables, bases, aliases)
            if build_id is None:
                return None
        config = cls._extract_config(js, tables, bases, aliases, rotation)
        return BuildInfo(build_id, tuple(seeds), config)

    @classmethod
    def _find_seeds_and_rotation(
        cls,
        js: str,
        tables: dict[str, list[str]],
        bases: dict[str, _BaseDecoder],
        aliases: dict[str, _AliasDecoder],
    ) -> tuple[list[str], int] | None:
        for match in _ARRAY_REGEX.finditer(js):
            expression = match.group(1)
            calls = [call.group(0) for call in _CALL_REGEX.finditer(expression)]
            if len(calls) not in (
                MKissaCrypto.SEED_COUNT * 2,
                MKissaCrypto.SEED_COUNT * 4,
            ):
                continue

            alias = cls._alias_for_call(calls[0], aliases)
            base = bases.get(alias.base) if alias else None
            table = tables.get(base.table, []) if base else []
            if not table:
                continue

            for rotation in range(len(table)):
                seeds = cls._seeds_at(calls, rotation, tables, bases, aliases)
                if seeds is not None:
                    return seeds, rotation
        return None

    @classmethod
    def _extract_build_id_with_rotation(
        cls,
        js: str,
        tables: dict[str, list[str]],
        bases: dict[str, _BaseDecoder],
        aliases: dict[str, _AliasDecoder],
        rotation: int,
    ) -> str | None:
        seeds_marker = js.find("const dm=")
        if seeds_marker < 0:
            return None
        window = js[max(0, seeds_marker - 2_000) : seeds_marker]
        declarations = re.compile(rf"\b(?:const|let|var)\s+{_IDENT}\s*=\s*({_CALL_PATTERN})")
        candidates = [match.group(1) for match in declarations.finditer(window)]
        if not candidates:
            return None

        # The crypto build is the final decoded declaration before the seed table.
        for call in reversed(candidates):
            decoded = cls._resolve(call, rotation, tables, bases, aliases)
            if decoded and _BUILD_ID_REGEX.fullmatch(decoded) and 2 <= len(decoded) <= 32:
                return decoded
        return None

    @classmethod
    def _extract_config(
        cls,
        js: str,
        tables: dict[str, list[str]],
        bases: dict[str, _BaseDecoder],
        aliases: dict[str, _AliasDecoder],
        rotation: int,
    ) -> MKissaConfig | None:
        # Look for Mf config object: Mf={v:1,saltMul:114,saltAdd:200,fragMul:219,fragAdd:67,bootPrefix:...,join:"~",parts:[...],...}
        config_match = re.search(r"=\s*\{[^{}]*saltMul:[^{}]*fragMul:[^{}]*\}", js)
        if not config_match:
            return None
        text = config_match.group(0)

        def extract_int(field: str, default: int) -> int:
            m = re.search(rf"{field}\s*:\s*(-?\d+)", text)
            return int(m.group(1)) if m else default

        salt_mul = extract_int("saltMul", 6)
        salt_add = extract_int("saltAdd", 244)
        frag_mul = extract_int("fragMul", 190)
        frag_add = extract_int("fragAdd", 88)
        env_xor = extract_int("envXor", 0)

        # Boot prefix
        boot_prefix_match = re.search(r"bootPrefix\s*:\s*(.+?)\s*,\s*[a-zA-Z0-9_]+\s*:", text)
        boot_prefix = "FD0xZhgI:"
        if boot_prefix_match:
            bp_expr = boot_prefix_match.group(1)
            parts = []
            for token in re.split(r"\s*\+\s*", bp_expr):
                token = token.strip()
                if token.startswith(('"', "'")) and token.endswith(('"', "'")):
                    parts.append(token[1:-1])
                elif _CALL_REGEX.fullmatch(token):
                    resolved = cls._resolve(token, rotation, tables, bases, aliases)
                    if resolved:
                        parts.append(resolved)
            if parts:
                boot_prefix = "".join(parts)

        # Join character
        join_match = re.search(r'join\s*:\s*["\']([^"\']+)["\']', text)
        join_char = join_match.group(1) if join_match else "."

        # Parts
        parts_match = re.search(r"parts\s*:\s*\[([^\]]+)\]", text)
        parts_list: list[str] = []
        if parts_match:
            # We can't split by comma because of fr(248,391). We need to split by ")+", "',", etc.
            # But wait, parts is an array like [fr(247,391)+"e", fr(190,300)+"ch"]
            # To split it safely, we can split by `,` that are NOT inside parentheses.
            items = []
            current = []
            paren_level = 0
            for char in parts_match.group(1):
                if char == "(":
                    paren_level += 1
                elif char == ")":
                    paren_level -= 1
                if char == "," and paren_level == 0:
                    items.append("".join(current))
                    current = []
                else:
                    current.append(char)
            if current:
                items.append("".join(current))

            for item in items:
                item = item.strip()
                item_parts = []
                for token in re.split(r"\s*\+\s*", item):
                    token = token.strip()
                    if token.startswith(('"', "'")) and token.endswith(('"', "'")):
                        item_parts.append(token[1:-1])
                    elif _CALL_REGEX.fullmatch(token):
                        resolved = cls._resolve(token, rotation, tables, bases, aliases)
                        if resolved:
                            item_parts.append(resolved)
                if item_parts:
                    parts_list.append("".join(item_parts))

        return MKissaConfig(
            salt_mul=salt_mul,
            salt_add=salt_add,
            frag_mul=frag_mul,
            frag_add=frag_add,
            boot_prefix=boot_prefix,
            join_char=join_char,
            parts=tuple(parts_list)
            if parts_list
            else ("host", "epoch", "group", "lane", "buildId"),
            env_xor=env_xor,
        )

    @classmethod
    def _decoders_from(
        cls, js: str
    ) -> tuple[
        dict[str, list[str]],
        dict[str, _BaseDecoder],
        dict[str, _AliasDecoder],
    ]:
        tables = cls._read_tables(js)
        bases = {
            match.group(1): _BaseDecoder(match.group(4), cls._fold(match.group(3)))
            for match in _BASE_DECODER_REGEX.finditer(js)
        }
        aliases = {name: _AliasDecoder(name, 0, 0) for name in bases}
        for match in _ALIAS_DECODER_REGEX.finditer(js):
            name, first_parameter, second_parameter, callee, argument, sign, obj_delta, arith_delta = match.groups()
            if callee not in bases:
                continue
            # Handle both old pattern: delta as arithmetic expression
            # and new pattern: delta from object property {_0x453117:564}._0x453117
            if obj_delta:
                delta = int(obj_delta)
                if sign == "-":
                    delta = -delta
            else:
                delta = cls._fold(sign + arith_delta) if arith_delta else 0

            aliases[name] = _AliasDecoder(
                callee,
                0 if argument == first_parameter else 1,
                delta,
            )
        return tables, bases, aliases

    @classmethod
    def _extract_build_id(
        cls,
        js: str,
        tables: dict[str, list[str]],
        bases: dict[str, _BaseDecoder],
        aliases: dict[str, _AliasDecoder],
    ) -> str | None:
        mask_default_variable = next(
            (
                match.group(2)
                for match in _DEFAULT_PARAMETER_REGEX.finditer(js)
                if re.search(
                    _ASSIGNMENT_REGEX_TEMPLATE.format(name=re.escape(match.group(2))),
                    js,
                )
            ),
            None,
        )

        candidates: list[str] = []
        if mask_default_variable:
            assignment = re.compile(
                _ASSIGNMENT_REGEX_TEMPLATE.format(name=re.escape(mask_default_variable))
            )
            candidates.extend(match.group(1) for match in assignment.finditer(js))

        marker_index = js.find("sf=")
        if marker_index >= 0:
            window = js[max(0, marker_index - 2000) : marker_index]
            candidates.extend(
                match.group(1)
                for match in _ANY_ASSIGNMENT_REGEX.finditer(window)
                if "+" not in match.group(1)
            )

        if not candidates:
            candidates.extend(
                match.group(1)
                for match in _ANY_ASSIGNMENT_REGEX.finditer(js)
                if "+" not in match.group(1)
            )

        for call in candidates:
            alias = cls._alias_for_call(call, aliases)
            if alias is None:
                continue
            base = bases.get(alias.base)
            table = tables.get(base.table, []) if base else []
            for rotation in range(len(table)):
                decoded = cls._resolve(call, rotation, tables, bases, aliases)
                if (
                    decoded
                    and _BUILD_ID_REGEX.fullmatch(decoded)
                    and cls._extract_seeds(js, tables, bases, aliases, rotation) is not None
                ):
                    return decoded

        for match in _CALL_REGEX.finditer(js):
            call = match.group(0)
            if "+" in call:
                continue
            alias = aliases.get(match.group(1))
            base = bases.get(alias.base) if alias else None
            table = tables.get(base.table, []) if base else []
            for rotation in range(len(table)):
                decoded = cls._resolve(call, rotation, tables, bases, aliases)
                if (
                    not decoded
                    or not _BUILD_ID_REGEX.fullmatch(decoded)
                    or not 2 <= len(decoded) <= 8
                ):
                    continue
                preceding = js[max(0, match.start() - 20) : match.start()]
                if "sf=" in preceding or "kd=" in preceding:
                    continue
                if cls._extract_seeds(js, tables, bases, aliases, rotation) is not None:
                    return decoded
        return None

    @classmethod
    def _extract_seeds(
        cls,
        js: str,
        tables: dict[str, list[str]],
        bases: dict[str, _BaseDecoder],
        aliases: dict[str, _AliasDecoder],
        forced_rotation: int | None = None,
    ) -> list[str] | None:
        for match in _ARRAY_REGEX.finditer(js):
            expression = match.group(1)
            calls = [call.group(0) for call in _CALL_REGEX.finditer(expression)]
            if len(calls) not in (
                MKissaCrypto.SEED_COUNT * 2,
                MKissaCrypto.SEED_COUNT * 4,
            ):
                continue
            if expression.count("+") < MKissaCrypto.SEED_COUNT:
                continue

            alias = cls._alias_for_call(calls[0], aliases)
            base = bases.get(alias.base) if alias else None
            table = tables.get(base.table, []) if base else []
            if not table:
                continue

            if forced_rotation is not None:
                seeds = cls._seeds_at(calls, forced_rotation, tables, bases, aliases)
                if seeds is not None:
                    return seeds
                continue

            matches = [
                seeds
                for rotation in range(len(table))
                if (seeds := cls._seeds_at(calls, rotation, tables, bases, aliases)) is not None
            ]
            if len(matches) == 1:
                return matches[0]
        return None

    @classmethod
    def _seeds_at(
        cls,
        calls: list[str],
        rotation: int,
        tables: dict[str, list[str]],
        bases: dict[str, _BaseDecoder],
        aliases: dict[str, _AliasDecoder],
    ) -> list[str] | None:
        if len(calls) % MKissaCrypto.SEED_COUNT:
            return None

        calls_per_seed = len(calls) // MKissaCrypto.SEED_COUNT
        seeds: list[str] = []
        for index in range(0, len(calls), calls_per_seed):
            fragments = [
                cls._resolve(call, rotation, tables, bases, aliases)
                for call in calls[index : index + calls_per_seed]
            ]
            if any(fragment is None for fragment in fragments):
                return None
            seed = "".join(fragment for fragment in fragments if fragment is not None)
            if not _SEED_REGEX.fullmatch(seed):
                return None
            seeds.append(seed)
        return seeds if len(seeds) == MKissaCrypto.SEED_COUNT else None

    @staticmethod
    def _alias_for_call(call: str, aliases: dict[str, _AliasDecoder]) -> _AliasDecoder | None:
        match = _CALL_REGEX.search(call)
        return aliases.get(match.group(1)) if match else None

    @staticmethod
    def _resolve(
        call: str,
        rotation: int,
        tables: dict[str, list[str]],
        bases: dict[str, _BaseDecoder],
        aliases: dict[str, _AliasDecoder],
    ) -> str | None:
        match = _CALL_REGEX.fullmatch(call)
        if match is None:
            return None
        alias = aliases.get(match.group(1))
        base = bases.get(alias.base) if alias else None
        table = tables.get(base.table, []) if base else []
        if alias is None or base is None or not table:
            return None
        arguments = [int(value) for value in match.groups()[1:] if value]
        if alias.argument_index >= len(arguments):
            return None
        index = arguments[alias.argument_index] + alias.delta - base.offset + rotation
        return table[index % len(table)]

    @classmethod
    def _read_tables(cls, js: str) -> dict[str, list[str]]:
        tables: dict[str, list[str]] = {}
        for match in _TABLE_HEAD_REGEX.finditer(js):
            values = cls._read_string_array(js, match.end() - 1)
            if values is not None:
                tables[match.group(1)] = values
        return tables

    @staticmethod
    def _read_string_array(js: str, opening_bracket: int) -> list[str] | None:
        items: list[str] = []
        index = opening_bracket + 1
        while index < len(js):
            character = js[index]
            if character == "]":
                return items
            if character in ", \t\r\n":
                index += 1
                continue
            if character not in "\"'":
                return None
            quote = character
            index += 1
            value: list[str] = []
            while index < len(js) and js[index] != quote:
                if js[index] == "\\":
                    if index + 1 >= len(js):
                        return None
                    value.append(js[index + 1])
                    index += 2
                else:
                    value.append(js[index])
                    index += 1
            if index >= len(js):
                return None
            items.append("".join(value))
            index += 1
        return None

    @classmethod
    def _fold(cls, expression: str) -> int:
        total = 0
        for term_match in _TERM_REGEX.finditer(expression.replace(" ", "")):
            term = term_match.group(0)
            sign = 1
            while term.startswith(("+", "-")):
                if term[0] == "-":
                    sign *= -1
                term = term[1:]
            factors = term.split("*")
            try:
                value = sign * cls._parse_signed_factor(factors[0])
                for factor in factors[1:]:
                    value *= cls._parse_signed_factor(factor)
            except ValueError:
                return 0
            total += value
        return total

    @staticmethod
    def _parse_signed_factor(factor: str) -> int:
        negative = False
        while factor.startswith(("+", "-")):
            if factor[0] == "-":
                negative = not negative
            factor = factor[1:]
        value = int(factor)
        return -value if negative else value
