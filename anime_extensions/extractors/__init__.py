"""Video hoster extractors."""

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

__all__ = [
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
