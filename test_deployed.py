import asyncio
import sys

import httpx

from anime_extensions.core.runtime import ExtensionRuntime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "https://anisource-api.onrender.com"


async def test_deployed(query: str):
    print("\n=======================================================")
    print(f"=== TESTING DEPLOYED API ({BASE_URL}) ===")
    print("=======================================================")
    async with httpx.AsyncClient(timeout=60.0) as client:
        print(f"Testing sources for query: '{query}'")
        try:
            sources_resp = await client.get(f"{BASE_URL}/api/v1/sources")
        except Exception as e:
            print(f"Failed to reach deployed API: {e}")
            return

        if sources_resp.status_code != 200:
            print(f"Failed to get sources: HTTP {sources_resp.status_code} - {sources_resp.text}")
            return

        sources = sources_resp.json().get("sources", [])
        for source in sources:
            source_id = source["id"]
            print(f"\n--- [Deployed] Testing source: {source_id} ---")

            search_resp = await client.get(
                f"{BASE_URL}/api/v1/{source_id}/search", params={"q": query}
            )
            if search_resp.status_code != 200:
                print(
                    f"[{source_id}] Search failed: HTTP {search_resp.status_code} - {search_resp.text}"
                )
                continue

            results = search_resp.json().get("items", [])
            if not results:
                print(f"[{source_id}] No search results")
                continue

            anime_id = results[0]["id"]
            print(f"[{source_id}] Found anime: {results[0]['title']} (id: {anime_id})")

            details_resp = await client.get(f"{BASE_URL}/api/v1/{source_id}/anime/{anime_id}")
            if details_resp.status_code != 200:
                print(f"[{source_id}] Details failed: HTTP {details_resp.status_code}")
                continue

            episodes_resp = await client.get(f"{BASE_URL}/api/v1/{source_id}/episodes/{anime_id}")
            if episodes_resp.status_code != 200:
                print(f"[{source_id}] Episodes failed: HTTP {episodes_resp.status_code}")
                continue

            episodes = episodes_resp.json()
            if not episodes:
                print(f"[{source_id}] No episodes found")
                continue

            print(f"[{source_id}] Found {len(episodes)} episodes")
            episode_id = episodes[0]["id"]

            servers_resp = await client.get(f"{BASE_URL}/api/v1/{source_id}/servers/{episode_id}")
            if servers_resp.status_code != 200:
                print(f"[{source_id}] Servers failed: HTTP {servers_resp.status_code}")
                continue

            servers = servers_resp.json()
            if not servers:
                print(f"[{source_id}] No servers found")
                continue

            print(f"[{source_id}] Found {len(servers)} servers")

            resolved = 0
            for server in servers:
                server_id = server["id"]
                server_name = server["name"]
                streams_resp = await client.get(
                    f"{BASE_URL}/api/v1/{source_id}/streams/{episode_id}",
                    params={"server_id": server_id},
                )
                if streams_resp.status_code == 200:
                    streams = streams_resp.json()
                    if streams:
                        print(
                            f"[{source_id}] [PASS] Got {len(streams)} stream(s) for server '{server_name}'"
                        )
                        resolved += 1
                    else:
                        print(
                            f"[{source_id}] [FAIL] 0 streams for server '{server_name}' (empty list)"
                        )
                else:
                    print(
                        f"[{source_id}] [FAIL] Server '{server_name}': HTTP {streams_resp.status_code} - {streams_resp.text}"
                    )

            if resolved > 0:
                print(
                    f"[{source_id}] -> PIPELINE SUCCESS ({resolved}/{len(servers)} servers resolved)"
                )
            else:
                print(f"[{source_id}] -> PIPELINE FAILED (0/{len(servers)} servers resolved)")


async def test_local(query: str):
    print("\n=======================================================")
    print("=== TESTING LOCAL SDK RUNTIME ===")
    print("=======================================================")
    runtime = ExtensionRuntime()
    await runtime.start()
    try:
        source_ids = ["anikoto", "animenosub", "aniwaves", "mkissa"]
        for source_id in source_ids:
            print(f"\n--- [Local] Testing source: {source_id} ---")
            try:
                source = runtime.get_source(source_id)
                if not source:
                    print(f"[{source_id}] Source is inactive or quarantined.")
                    continue
                results, _ = await source.search(query=query)
                if not results:
                    print(f"[{source_id}] No search results")
                    continue

                anime_id = results[0].id
                print(f"[{source_id}] Found anime: {results[0].title} (id: {anime_id})")

                details = await source.get_details(anime_id=anime_id)
                print(f"[{source_id}] Details: {details.title}")

                episodes = await source.get_episodes(anime_id=anime_id)
                if not episodes:
                    print(f"[{source_id}] No episodes found")
                    continue
                print(f"[{source_id}] Found {len(episodes)} episodes")

                episode_id = episodes[0].id
                servers = await source.get_servers(episode_id=episode_id)
                if not servers:
                    print(f"[{source_id}] No servers found")
                    continue
                print(f"[{source_id}] Found {len(servers)} servers")

                resolved = 0
                for server in servers:
                    try:
                        streams = await source.get_streams(
                            episode_id=episode_id, server_id=server.id
                        )
                        if streams:
                            print(
                                f"[{source_id}] [PASS] Got {len(streams)} stream(s) for server '{server.name}'"
                            )
                            resolved += 1
                        else:
                            print(
                                f"[{source_id}] [FAIL] 0 streams for server '{server.name}' (empty list)"
                            )
                    except Exception as e:
                        print(
                            f"[{source_id}] [FAIL] Server '{server.name}': {type(e).__name__}: {e}"
                        )

                if resolved > 0:
                    print(
                        f"[{source_id}] -> PIPELINE SUCCESS ({resolved}/{len(servers)} servers resolved)"
                    )
                else:
                    print(f"[{source_id}] -> PIPELINE FAILED (0/{len(servers)} servers resolved)")
            except Exception as e:
                print(f"[{source_id}] Pipeline error: {type(e).__name__}: {e}")
    finally:
        await runtime.close()


async def main():
    query = "frieren"
    await test_local(query)
    await test_deployed(query)


if __name__ == "__main__":
    asyncio.run(main())
