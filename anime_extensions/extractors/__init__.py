"""Video hoster extractors."""

from .byse import ByseExtractor
from .dood import DoodExtractor
from .echovideo import EchoVideoExtractor
from .moon import MoonExtractor
from .streamwish import StreamWishExtractor
from .vidmoly import VidMolyExtractor
from .vtube import VtubeExtractor
from .wolfstream import WolfStreamExtractor

__all__ = [
    "ByseExtractor",
    "DoodExtractor",
    "EchoVideoExtractor",
    "MoonExtractor",
    "StreamWishExtractor",
    "VidMolyExtractor",
    "VtubeExtractor",
    "WolfStreamExtractor",
]
