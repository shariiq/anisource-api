"""Deterministic tests for MKissa source."""

from unittest.mock import AsyncMock

import pytest

from anime_extensions.sources.mkissa import MKissa

# Mock responses
POPULAR_RESPONSE = {
    "data": {
        "queryPopular": {
            "recommendations": [
                {
                    "anyCard": {
                        "_id": "123",
                        "name": "Test Anime",
                        "thumbnail": "https://img.example/thumb.jpg",
                    }
                }
            ]
        }
    }
}

SEARCH_RESPONSE = {
    "data": {
        "shows": {
            "edges": [
                {
                    "_id": "123",
                    "name": "Test Anime",
                    "thumbnail": "https://img.example/thumb.jpg",
                }
            ]
        }
    }
}

DETAILS_RESPONSE = {
    "data": {
        "show": {
            "thumbnail": "https://img.example/thumb.jpg",
            "description": "A great anime description",
            "type": "TV",
            "season": {"quarter": "Spring", "year": 2024},
            "score": 8.5,
            "genres": ["Action", "Adventure"],
            "status": "Releasing",
            "studios": {"edges": [{"isMain": True, "node": {"name": "Studio MAPPA"}}]},
        }
    }
}

EPISODES_RESPONSE = {
    "data": {
        "show": {
            "_id": "123",
            "availableEpisodesDetail": {
                "sub": ["1", "2"],
                "dub": ["1"],
            },
        }
    }
}


@pytest.fixture
def source():
    return MKissa()


@pytest.mark.asyncio
async def test_get_popular(source):
    source._graphql_request = AsyncMock(return_value=POPULAR_RESPONSE)
    animes, has_next = await source.get_popular()
    assert len(animes) == 1
    assert animes[0].id == "123"
    assert animes[0].title == "Test Anime"


@pytest.mark.asyncio
async def test_search(source):
    source._graphql_request = AsyncMock(return_value=SEARCH_RESPONSE)
    animes, has_next = await source.search("test")
    assert len(animes) == 1
    assert animes[0].id == "123"


@pytest.mark.asyncio
async def test_get_details(source):
    source._graphql_request = AsyncMock(return_value=DETAILS_RESPONSE)
    anime = await source.get_details("123")
    assert anime.status == "ongoing"
    assert "Studio MAPPA" in anime.studios
    assert "8.5★" in anime.description


@pytest.mark.asyncio
async def test_get_episodes(source):
    source._graphql_request = AsyncMock(return_value=EPISODES_RESPONSE)
    episodes = await source.get_episodes("123")
    assert len(episodes) == 3
    assert episodes[0].number == 2.0
    assert "sub" in episodes[0].id
    assert any(episode.has_dub for episode in episodes)
