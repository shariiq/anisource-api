"""Built-in anime source implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anime_extensions.core.source import Source

from .anikoto import Anikoto
from .aniwaves import AniWaves


@dataclass(frozen=True)
class BuiltinSource:
    """A built-in source class with an enablement flag."""

    cls: type[Source]
    enabled: bool = True


# Explicit catalogue of built-in sources for runtime registration
BUILTIN_SOURCES: tuple[BuiltinSource, ...] = (
    BuiltinSource(AniWaves),
    BuiltinSource(Anikoto),
)

__all__ = ["Anikoto", "AniWaves", "BUILTIN_SOURCES", "BuiltinSource"]
