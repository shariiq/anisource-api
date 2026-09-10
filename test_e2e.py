"""Quick end-to-end test of the Anikoto scraper."""

import asyncio
import json

import pytest

from anime_extensions import Anikoto


@pytest.mark.asyncio
async def test_anikoto():
    async with Anikoto() as source:
        # 1. Get popular
        print("=== Popular ===")
        animes, has_next = await source.get_popular(page=1)
        print(f"Got {len(animes)} anime, has_next={has_next}")
        if animes:
            first = animes[0]
            print(f"  First: {first.title} ({first.id})")

        # 2. Search
        print("\n=== Search ===")
        results, _ = await source.search("Naruto", page=1)
        print(f"Found {len(results)} results")
        if results:
            print(f"  First: {results[0].title} ({results[0].id})")

        # 3. Get details
        print("\n=== Details ===")
        anime = None
        if results:
            anime = results[0]
            details = await source.get_details(anime.id)
            print(f"  Title: {details.title}")
            print(f"  Status: {details.status}")
            print(f"  Genres: {details.genres}")
            print(f"  Score: {details.score}")
            print(f"  Description: {details.description[:100]}...")

        # 4. Get episodes
        print("\n=== Episodes ===")
        episodes = []
        if anime:
            episodes = await source.get_episodes(anime.id)
            print(f"Got {len(episodes)} episodes")
            if episodes:
                ep = episodes[-1]  # Get a recent episode
                print(f"  Latest: {ep.title} (Ep {ep.number})")
                print(f"  ID: {ep.id}")

        # 5. Get servers
        print("\n=== Servers ===")
        if episodes:
            ep = episodes[-1]
            servers = await source.get_servers(ep.id)
            print(f"Got {len(servers)} servers")
            if servers:
                srv = servers[0]
                print(f"  First: {srv.name} ({srv.type}) - ID: {srv.id}")

                # 6. Get streams
                print("\n=== Streams ===")
                try:
                    streams = await source.get_streams(ep.id, srv.id)
                    print(f"Got {len(streams)} streams")
                    if streams:
                        s = streams[0]
                        print(f"  First: {s.quality} - {s.url[:80]}...")
                    else:
                        print("  (No streams found - may need valid server)")
                except Exception as e:
                    print(f"  Stream extraction failed: {e}")

        print("\n=== JSON Output Sample ===")
        if animes:
            print(json.dumps(animes[0].to_dict(), indent=2, default=str))

    print("\nAll tests completed!")


if __name__ == "__main__":
    asyncio.run(test_anikoto())
