# Writing an Extractor

This guide explains how to implement a new video extractor for the anime-extensions SDK. Extractors resolve embed URLs from video hosters into playable streams.

## Overview

Extractors are classes that:
1. Match specific URL patterns (domains, paths)
2. Fetch and parse the hoster's embed page or API
3. Return typed `Stream` models with video URLs and required headers

## Quick Start

### 1. Create the Extractor File

Create a new file in `anime_extensions/extractors/<name>.py`:

```python
"""<Name> video extractor."""

from __future__ import annotations

import logging
from typing import Any

from ..core.extractor import Extractor
from ..models import Stream, Subtitle

log = logging.getLogger(__name__)


class ExampleExtractor(Extractor):
    """Extractor for ExampleHost video provider."""

    name = "ExampleHost"

    async def extract(
        self,
        url: str,
        **kwargs: Any,
    ) -> list[Stream]:
        """Extract video streams from ExampleHost embed URL."""
        session = self.context.http.session
        if not session:
            return []

        # Your extraction logic here
        # ...
        
        return streams
```

### 2. Register in the Extractor Catalogue

Extractors are registered in `anime_extensions/extractors/__init__.py` within the `BUILTIN_EXTRACTORS` catalogue tuple. Each entry defines the extractor class, regex matching pattern, and priority integer (higher priority matched first):

```python
BUILTIN_EXTRACTORS: tuple[tuple[type[Extractor], str | re.Pattern[str], int], ...] = (
    # ...
    (ExampleExtractor, r"example\.com|examplehost\.net", 0),
)
```

Common pattern examples:

```python
# Match multiple domains
(EchoVideoExtractor, r"vidplay|mycloud|datsav|dghg|echovideo", 0)

# Match with path context
(ByseExtractor, r"byfms|gn1r5n|bysekoze", 0)

# Match with strict domain boundaries
(DoodStreamExtractor, r"dood|myvidplay|ds2play|doodstream", 0)
```

### 3. Export from `__init__.py`

Add your extractor to `anime_extensions/extractors/__init__.py` `__all__`:

```python
from .example import ExampleExtractor

__all__ = [
    # ... existing extractors
    "ExampleExtractor",
    "BUILTIN_EXTRACTORS",
]
```

## The Extract Contract

Every extractor must implement `async def extract(self, url: str, **kwargs) -> list[Stream]`:

### Parameters

- `url` (str): The embed URL to extract from
- `**kwargs`: Optional parameters from the calling source:
  - `label_prefix` (str): Prefix for quality labels (e.g., `"Vidplay"`)
  - `quality_prefix` (str): Alias for `label_prefix`
  - `external_subs` (list[Subtitle]): Subtitles to attach to streams
  - Source-specific parameters (e.g., `embed_parent`, `embed_origin`)

### Return Value

Return a `list[Stream]`. Each `Stream` requires:

```python
Stream(
    url="https://video.example.com/stream.m3u8",  # Required: video URL
    quality="1080p",  # Required: quality label
    headers={"Referer": "...", "User-Agent": "..."},  # Optional but common
    subtitles=[Subtitle(url="...", label="English")],  # Optional
    is_hls=True,  # True for m3u8, False for direct MP4
)
```

### Error Handling

**Raise `ParsingError`** when the response is malformed or missing required data:

```python
from ..exceptions import ParsingError

if not sources:
    raise ParsingError(
        f"ExampleHost: 'sources' field missing or empty. Available keys: {list(data.keys())}"
    )
```

**Let HTTP errors propagate** — the `HttpClient` wraps them in typed exceptions (`HttpError`, `TimeoutError`).

**Return empty list `[]`** only when the resource genuinely doesn't exist (deleted video, removed mirror). Don't use `[]` to hide parsing failures.

## Common Patterns

### Fetching JSON APIs

```python
async with session.get(api_url, headers=headers) as resp:
    if resp.status != 200:
        raise ParsingError(f"ExampleHost: API returned {resp.status}")
    data = await resp.json(content_type=None)  # content_type=None for lenient parsing
```

### Following Redirects

```python
async with session.get(url, headers=headers) as resp:
    final_url = str(resp.url)  # The URL after redirects
    html = await resp.text(errors="replace")
```

### Parsing HTML with BeautifulSoup

```python
from bs4 import BeautifulSoup

soup = BeautifulSoup(html, "lxml")

# Extract data from elements
title = soup.title.get_text() if soup.title else ""
video_url = soup.find("source", {"src": True})["src"]

# Search in script tags
script_content = soup.find("script", string=re.compile("playerData")).string
```

### Processing m3u8 Playlists

```python
from ..utils.m3u8 import parse_m3u8_streams

hls_text = await self.context.http.get(
    m3u8_url, headers={"Referer": referer, "User-Agent": USER_AGENT}
)

streams = parse_m3u8_streams(
    hls_text,
    m3u8_url,
    referer=referer,
    subtitles=subtitles,
    default_headers={"Referer": referer, "User-Agent": USER_AGENT},
    label_prefix=label_prefix,
)
```

## Testing

### Unit Tests

Create `tests/extractors/test_<name>.py` with mocked HTTP responses:

```python
from unittest.mock import AsyncMock, MagicMock
import pytest
from anime_extensions.extractors.example import ExampleExtractor


class MockHttp:
    pass


class MockContext:
    def __init__(self):
        self.http = MockHttp()


@pytest.fixture
def extractor():
    ctx = MockContext()
    ctx.http.session = MagicMock()
    return ExampleExtractor(ctx)


@pytest.mark.asyncio
async def test_example_extraction(extractor):
    """Test basic extraction flow."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json.return_value = {
        "sources": [{"url": "https://example.com/video.m3u8", "label": "1080p"}],
    }
    mock_resp.__aenter__.return_value = mock_resp
    mock_resp.__aexit__.return_value = None
    
    extractor.context.http.session.get.return_value = mock_resp
    
    streams = await extractor.extract("https://example.com/embed/abc123")
    
    assert len(streams) == 1
    assert streams[0].url == "https://example.com/video.m3u8"
    assert "1080p" in streams[0].quality
```

### Live Tests

Create `tests/live/test_live_<name>.py` for integration testing:

```python
@pytest.mark.live
@pytest.mark.asyncio
async def test_live_extraction():
    """Test extraction against real embed URL."""
    from anime_extensions.core import ExtensionRuntime
    from anime_extensions.extractors.example import ExampleExtractor
    
    async with ExtensionRuntime() as runtime:
        extractor = runtime.resolve_extractor("https://example.com/embed/abc123")
        streams = await extractor.extract(url)
        
        assert len(streams) > 0
        assert streams[0].url.startswith("http")
```

Run with: `uv run pytest tests/live/test_live_<name>.py --run-live`

## Best Practices

### 1. Use `self.context.http.session`

Never create your own `aiohttp.ClientSession()`. The shared session provides:
- Connection pooling
- Timeout management
- TLS configuration
- Typed exception translation

### 2. Set Proper Headers

Most hosters require:
```python
headers = {
    "User-Agent": USER_AGENT,
    "Referer": embed_url,  # Or the hoster's base URL
}
```

### 3. Handle Multiple Payload Shapes

Video hosters change their API formats frequently. Support multiple response shapes:

```python
# Try primary format
if isinstance(sources, dict) and "file" in sources:
    url = sources["file"]
# Try alternate format
elif isinstance(sources, list) and sources:
    url = sources[0].get("url")
# Fallback
else:
    raise ParsingError(f"Unrecognized sources format: {type(sources)}")
```

### 4. Propagate Meaningful Errors

```python
# Good: Specific error with context
if not video_url:
    raise ParsingError(
        f"ExampleHost: could not extract video URL from payload. Keys present: {list(data.keys())}"
    )

# Bad: Silent failure
if not video_url:
    return []
```

### 5. Keep Constants Local to the Extractor

Define extractor-specific headers and protocol constants alongside the implementation. Runtime-owned HTTP lifecycle and request translation are provided by `self.context.http`; there is no shared extractor configuration module.

## Example: Minimal Extractor

```python
"""Simple video extractor for direct MP4 links."""

from __future__ import annotations

import logging
from typing import Any

from ..core.extractor import Extractor
from ..exceptions import ParsingError
from ..models import Stream

log = logging.getLogger(__name__)


class SimpleHostExtractor(Extractor):
    """Extractor for SimpleHost direct MP4 links."""

    name = "SimpleHost"

    async def extract(self, url: str, **kwargs: Any) -> list[Stream]:
        """Extract direct MP4 stream from SimpleHost URL."""
        session = self.context.http.session
        if not session:
            return []

        label_prefix = kwargs.get("label_prefix", "")

        # Fetch the embed page
        async with session.get(url, headers={"User-Agent": USER_AGENT}) as resp:
            if resp.status != 200:
                raise ParsingError(f"SimpleHost: returned HTTP {resp.status}")
            html = await resp.text(errors="replace")

        # Extract video URL from HTML
        import re

        match = re.search(r'data-src="(https://[^"]+\.mp4)"', html)
        if not match:
            raise ParsingError("SimpleHost: no video URL found in embed page")

        video_url = match.group(1)
        quality = f"{label_prefix} - 1080p" if label_prefix else "1080p"

        return [
            Stream(
                url=video_url,
                quality=quality,
                headers={"Referer": url, "User-Agent": USER_AGENT},
                is_hls=False,
            )
        ]
```

## Debugging Tips

1. **Log at debug level** for routine operations:
   ```python
   log.debug("Fetching API: %s", api_url)
   ```

2. **Log warnings for recoverable issues**:
   ```python
   log.warning("Failed to parse subtitle track: %s", track_data)
   ```

3. **Include URL context in errors**:
   ```python
   raise ParsingError(f"ExampleHost: extraction failed for {url}: {reason}")
   ```

4. **Test against real responses** by temporarily adding:
   ```python
   log.debug("Response data: %s", await resp.text())
   ```

## Common Pitfalls

- ❌ Creating your own `aiohttp.ClientSession()`
- ❌ Returning `[]` for malformed 200 OK responses (should raise `ParsingError`)
- ❌ Hardcoding timeout values (use the runtime-owned `HttpClient` defaults or inject a timeout explicitly)
- ❌ Forgetting to set `Referer` header (many hosters require it)
- ❌ Ignoring subtitle tracks in the payload
- ❌ Not handling both `{"file": "..."}` and `{"url": "..."}` keys

## Reference Implementations

Study these extractors for real-world patterns:

- `echovideo.py`: Multiple payload schemas, m3u8 parsing, subtitle extraction
- `byse.py`: Multi-stage challenge/PoW flow, complex crypto
- `dood.py`: Redirect handling, token extraction, random string generation
