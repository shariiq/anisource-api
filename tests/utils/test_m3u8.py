"""Unit tests for M3U8 parsing and playlist processing utilities."""

from anime_extensions.utils.m3u8 import (
    absolutize_m3u8_urls,
    decode_numeric_hls,
    parse_m3u8_streams,
)


def test_decode_numeric_hls_standard():
    """Test standard decimal byte decoding for HLS streams."""
    # "Hello" in ascii decimal: 72, 101, 108, 108, 111
    encoded = "72\n101\n108\n108\n111"
    decoded = decode_numeric_hls(encoded)
    assert decoded == "Hello"


def test_decode_numeric_hls_passthrough():
    """Test that normal text is passed through untouched."""
    normal_text = "#EXTM3U\n#EXT-X-VERSION:3\n"
    assert decode_numeric_hls(normal_text) == normal_text


def test_decode_numeric_hls_out_of_range():
    """Test that invalid byte values abort decoding and return original text."""
    invalid = "300\n100\n"
    assert decode_numeric_hls(invalid) == invalid


def test_absolutize_m3u8_urls():
    """Test rewriting relative segment and key URIs to absolute URIs."""
    playlist = (
        "#EXTM3U\n"
        '#EXT-X-KEY:METHOD=AES-128,URI="key.enc"\n'
        "#EXTINF:10.0,\n"
        "segment_0.ts\n"
        "https://example.com/segment_1.ts\n"
    )
    base = "https://cdn.example.com/hls/ep1/"
    res = absolutize_m3u8_urls(playlist, base)

    assert 'URI="https://cdn.example.com/hls/ep1/key.enc"' in res
    assert "https://cdn.example.com/hls/ep1/segment_0.ts" in res
    assert "https://example.com/segment_1.ts" in res  # Absolute should remain untouched


def test_parse_m3u8_variant_streams():
    """Test parsing multi-variant master playlists with resolutions and bandwidth."""
    master = (
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=1280000,RESOLUTION=1280x720\n"
        "720p.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=2560000,RESOLUTION=1920x1080\n"
        "1080p.m3u8\n"
    )
    master_url = "https://cdn.example.com/video/master.m3u8"
    streams = parse_m3u8_streams(master, master_url, label_prefix="Vidplay")

    assert len(streams) == 2
    assert streams[0].quality == "Vidplay - 720p"
    assert streams[0].url == "https://cdn.example.com/video/720p.m3u8"
    assert streams[1].quality == "Vidplay - 1080p"
    assert streams[1].url == "https://cdn.example.com/video/1080p.m3u8"
    assert streams[0].is_hls is True
