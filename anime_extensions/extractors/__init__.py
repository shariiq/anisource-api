"""Built-in video hoster extractors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .byse import ByseExtractor
from .dood import DoodExtractor
from .echovideo import EchoVideoExtractor
from .gogo import GogoStreamExtractor
from .moon import MoonExtractor
from .mp4upload import Mp4UploadExtractor
from .okru import OkruExtractor
from .streamlare import StreamlareExtractor
from .streamwish import StreamWishExtractor
from .vidmoly import VidMolyExtractor
from .vtube import VtubeExtractor
from .wolfstream import WolfStreamExtractor

if TYPE_CHECKING:
    from anime_extensions.core.extractor import Extractor


BUILTIN_EXTRACTORS: tuple[tuple[type[Extractor], str, int], ...] = (
    (ByseExtractor, r"byfms|gn1r5n|byse(?!sayeveum)", 0),
    (DoodExtractor, r"dood|myvidplay|ds2play|doodstream", 0),
    (EchoVideoExtractor, r"vidplay|mycloud|datsav|dghg|echovideo", 0),
    (GogoStreamExtractor, r"gogo|vidstreaming|playgo1\.cc|playtaku|vidcloud", 0),
    (MoonExtractor, r"bysesayeveum|fmoon|filemoon|moonembed", 0),
    (Mp4UploadExtractor, r"mp4upload\.com", 0),
    (OkruExtractor, r"ok\.ru|okru|odnoklassniki\.ru", 0),
    (StreamlareExtractor, r"streamlare\.com|slwatch\.co", 0),
    (
        StreamWishExtractor,
        r"streamwish\.\w+|wish\w*\.\w+|sw\w*\.\w+|niramirus\.\w+|medixiru\.\w+|streamwish",
        0,
    ),
    (VidMolyExtractor, r"vidmoly", 0),
    (VtubeExtractor, r"vtbe|vtube", 0),
    (WolfStreamExtractor, r"wolfstream", 0),
)

__all__ = [
    "BUILTIN_EXTRACTORS",
    "ByseExtractor",
    "DoodExtractor",
    "EchoVideoExtractor",
    "GogoStreamExtractor",
    "MoonExtractor",
    "Mp4UploadExtractor",
    "OkruExtractor",
    "StreamWishExtractor",
    "StreamlareExtractor",
    "VidMolyExtractor",
    "VtubeExtractor",
    "WolfStreamExtractor",
]
