"""Exercise local SDK and deployed API source pipelines against a live query.

This is a diagnostic integration script, not a pytest test module. It verifies the
search-to-stream path for every active source and reports upstream-specific failures
without masking them as SDK failures.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx

from anime_extensions import ExtensionRuntime

DEFAULT_BASE_URL = "https://anisource-api.onrender.com"
DEFAULT_QUERY = "frieren"
MAX_CONCURRENT_STREAM_REQUESTS = 5


class Status(StrEnum):
    """Outcome of one source pipeline verification."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(slots=True)
class PipelineReport:
    """Diagnostic result for one local or deployed source pipeline."""

    environment: str
    source_id: str
    status: Status = Status.SKIP
    stages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    servers_tested: int = 0
    servers_resolved: int = 0
    streams_resolved: int = 0
    elapsed_seconds: float = 0.0
    stage_seconds: dict[str, float] = field(default_factory=dict)
    stream_results: list[StreamResult] = field(default_factory=list)
    _started_at: float = field(default=0.0, init=False, repr=False)

    def record(self, message: str) -> None:
        self.stages.append(message)
        print(f"[{self.environment}:{self.source_id}] {message}")

    def fail(self, message: str) -> None:
        self.errors.append(message)
        self.record(f"[FAIL] {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        self.record(f"[WARN] {message}")

    def finish(self) -> None:
        self.status = (
            Status.PASS if self.servers_resolved else (Status.FAIL if self.errors else Status.SKIP)
        )
        self.elapsed_seconds = time.perf_counter() - self._started_at

    def start(self) -> None:
        self._started_at = time.perf_counter()


@dataclass(frozen=True, slots=True)
class StreamResult:
    """Result of resolving one server's streams."""

    server_name: str
    stream_count: int
    error: str | None = None
    warnings: tuple[str, ...] = ()


def parse_args() -> argparse.Namespace:
    """Parse command-line options for live pipeline verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-q", "--query", default=DEFAULT_QUERY, help="Anime search query.")
    parser.add_argument(
        "-s",
        "--source",
        action="append",
        dest="sources",
        help="Source ID to test. Repeat to select multiple sources.",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_BASE_URL,
        help="Deployed API base URL (default: %(default)s).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request deployed API timeout in seconds (default: %(default)s).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--local-only", action="store_true", help="Test only the local SDK runtime.")
    mode.add_argument("--deployed-only", action="store_true", help="Test only the deployed API.")
    return parser.parse_args()


def api_base_url(base_url: str) -> str:
    """Normalize a server or API-root URL to the versioned API root."""
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith("/api/v1") else f"{normalized}/api/v1"


def selected(source_id: str, source_filter: set[str] | None) -> bool:
    """Return whether a source is included by the optional command-line filter."""
    return source_filter is None or source_id in source_filter


def stream_attributes(stream: Any) -> tuple[str, str, Mapping[str, str], int, bool]:
    """Extract the stream fields shared by SDK models and API JSON mappings."""
    if isinstance(stream, Mapping):
        url = stream.get("url", "")
        quality = stream.get("quality", "")
        headers = stream.get("headers", {})
        subtitles = stream.get("subtitles", [])
        is_hls = stream.get("is_hls", False)
    else:
        url = stream.url
        quality = stream.quality
        headers = stream.headers
        subtitles = stream.subtitles
        is_hls = stream.is_hls

    return str(url), str(quality), headers, len(subtitles), bool(is_hls)


def validate_streams(streams: Sequence[Any]) -> tuple[int, list[str]]:
    """Validate stream URLs and return non-fatal playback diagnostics."""
    warnings: list[str] = []
    valid_count = 0
    for stream in streams:
        url, quality, headers, subtitle_count, is_hls = stream_attributes(stream)
        if not url.startswith(("http://", "https://")):
            warnings.append(f"invalid playback URL for {quality or 'unlabeled'} stream: {url!r}")
            continue

        valid_count += 1
        header_names = {name.lower() for name in headers}
        missing_headers = {"referer", "user-agent"} - header_names
        details = f"{quality or 'unlabeled'}, {'HLS' if is_hls else 'direct'}, {subtitle_count} subtitle(s)"
        if missing_headers:
            warnings.append(f"{details}; no {', '.join(sorted(missing_headers))} header")
        else:
            warnings.append(f"{details}; playback headers present")
    return valid_count, warnings


async def resolve_servers(
    servers: Sequence[tuple[str, str]],
    resolve: Callable[[str], Awaitable[Sequence[Any]]],
) -> list[StreamResult]:
    """Resolve all server streams concurrently with a bounded request fan-out."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_STREAM_REQUESTS)

    async def resolve_one(server_id: str, server_name: str) -> StreamResult:
        try:
            async with semaphore:
                streams = await resolve(server_id)
            valid_count, warnings = validate_streams(streams)
            if not streams:
                return StreamResult(server_name, 0, "empty stream list")
            if not valid_count:
                return StreamResult(
                    server_name, 0, "no streams have valid HTTP(S) URLs", tuple(warnings)
                )
            return StreamResult(server_name, valid_count, warnings=tuple(warnings))
        except Exception as exc:  # Live upstream failures are reported per server.
            return StreamResult(server_name, 0, f"{type(exc).__name__}: {exc}")

    return await asyncio.gather(*(resolve_one(server_id, name) for server_id, name in servers))


def record_stream_results(report: PipelineReport, results: Sequence[StreamResult]) -> None:
    """Fold concurrently collected server results into one pipeline report."""
    report.servers_tested = len(results)
    report.stream_results.extend(results)
    for result in results:
        if result.error:
            report.fail(f"server {result.server_name!r}: {result.error}")
            continue
        report.servers_resolved += 1
        report.streams_resolved += result.stream_count
        report.record(f"[PASS] {result.server_name!r}: {result.stream_count} valid stream(s)")
        for warning in result.warnings:
            report.warn(f"server {result.server_name!r}: {warning}")


def report_summary(reports: Sequence[PipelineReport]) -> None:
    """Print an aligned summary after all selected pipelines finish."""
    print("\n=== PIPELINE SUMMARY ===")
    if not reports:
        print("No sources were selected.")
        return

    for report in reports:
        stages_str = ", ".join(
            f"{stage}: {sec:.1f}s" for stage, sec in report.stage_seconds.items()
        )
        if stages_str:
            stages_str = f" ({stages_str})"
        print(
            f"{report.status:<4} {report.environment:<8} {report.source_id:<14} "
            f"servers {report.servers_resolved}/{report.servers_tested}, "
            f"streams {report.streams_resolved}, {report.elapsed_seconds:.1f}s{stages_str}"
        )
    passed = sum(report.status is Status.PASS for report in reports)
    print(f"{passed}/{len(reports)} source pipelines passed")

    # Persist benchmarks to disk
    benchmark_dir = Path(".benchmarks")
    benchmark_dir.mkdir(exist_ok=True)
    benchmark_file = benchmark_dir / "last_run.json"

    timestamp = datetime.now(UTC).isoformat()
    data = {
        "timestamp": timestamp,
        "pipelines": [
            {
                "environment": r.environment,
                "source_id": r.source_id,
                "status": str(r.status),
                "elapsed_seconds": round(r.elapsed_seconds, 3),
                "servers_resolved": r.servers_resolved,
                "servers_tested": r.servers_tested,
                "streams_resolved": r.streams_resolved,
                "stage_seconds": {k: round(v, 3) for k, v in r.stage_seconds.items()},
                "server_results": [
                    {
                        "server_name": sr.server_name,
                        "stream_count": sr.stream_count,
                        "error": sr.error,
                        "warnings": list(sr.warnings),
                    }
                    for sr in r.stream_results
                ],
                "errors": r.errors,
                "warnings": r.warnings,
            }
            for r in reports
        ],
    }
    benchmark_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\nSaved benchmark results to {benchmark_file}")


async def test_local(query: str, source_filter: set[str] | None) -> list[PipelineReport]:
    """Run the complete pipeline against every active local SDK source."""
    print("\n=== TESTING LOCAL SDK RUNTIME ===")
    reports: list[PipelineReport] = []

    async with ExtensionRuntime() as runtime:
        source_ids = sorted(source.metadata.id for source in runtime.sources.list_all())
        for source_id in source_ids:
            if not selected(source_id, source_filter):
                continue

            report = PipelineReport("local", source_id)
            report.start()
            reports.append(report)
            source = runtime.get_source(source_id)
            if source is None:
                report.status = Status.SKIP
                report.record("[SKIP] source is disabled or unavailable in this runtime")
                report.finish()
                continue

            try:
                t0 = time.perf_counter()
                page = await source.search(query=query)
                report.stage_seconds["search"] = time.perf_counter() - t0
                if not page.items:
                    report.fail("search returned no results")
                    continue
                anime = page.items[0]
                report.record(f"search: {anime.title!r} ({anime.id})")

                t0 = time.perf_counter()
                details = await source.get_details(anime.id)
                report.stage_seconds["details"] = time.perf_counter() - t0
                report.record(f"details: {details.title!r}")

                t0 = time.perf_counter()
                episodes = await source.get_episodes(anime.id)
                report.stage_seconds["episodes"] = time.perf_counter() - t0
                if not episodes:
                    report.fail("no episodes found")
                    continue
                episode = episodes[0]
                report.record(f"episodes: {len(episodes)}; testing episode {episode.id!r}")

                t0 = time.perf_counter()
                servers = await source.get_servers(episode.id)
                report.stage_seconds["servers"] = time.perf_counter() - t0
                if not servers:
                    report.fail("no servers found")
                    continue
                report.record(f"servers: {len(servers)}")

                t0 = time.perf_counter()
                results = await resolve_servers(
                    [(server.id, server.name) for server in servers],
                    lambda server_id, src=source, ep=episode: src.get_streams(ep.id, server_id),
                )
                report.stage_seconds["streams"] = time.perf_counter() - t0
                record_stream_results(report, results)
            except Exception as exc:  # Report an individual upstream/source failure and continue.
                report.fail(f"pipeline error: {type(exc).__name__}: {exc}")
            finally:
                report.finish()

    return reports


async def response_json(response: httpx.Response, context: str) -> Any:
    """Decode a successful JSON response with diagnostic context."""
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"{context} returned invalid JSON") from exc


async def test_deployed(
    query: str,
    base_url: str,
    timeout: float,
    source_filter: set[str] | None,
) -> list[PipelineReport]:
    """Run the complete pipeline through the deployed FastAPI API."""
    api_url = api_base_url(base_url)
    print(f"\n=== TESTING DEPLOYED API ({api_url}) ===")
    reports: list[PipelineReport] = []

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            payload = await response_json(await client.get(f"{api_url}/sources"), "source list")
            if not isinstance(payload, Mapping):
                raise RuntimeError("source list response is not an object")
            source_ids = sorted(str(source["id"]) for source in payload.get("sources", []))
        except (httpx.HTTPError, RuntimeError, KeyError, TypeError) as exc:
            report = PipelineReport("deployed", "<source-list>", Status.FAIL)
            report.start()
            report.fail(f"unable to discover sources: {type(exc).__name__}: {exc}")
            report.finish()
            return [report]

        requested_ids = source_filter or set(source_ids)
        for missing_id in sorted(requested_ids - set(source_ids)):
            report = PipelineReport("deployed", missing_id, Status.FAIL)
            report.start()
            report.fail("source is not returned by the deployed API")
            report.finish()
            reports.append(report)

        for source_id in source_ids:
            if not selected(source_id, source_filter):
                continue

            report = PipelineReport("deployed", source_id)
            report.start()
            reports.append(report)
            try:
                t0 = time.perf_counter()
                search = await response_json(
                    await client.get(f"{api_url}/{source_id}/search", params={"q": query}),
                    f"{source_id} search",
                )
                report.stage_seconds["search"] = time.perf_counter() - t0
                if not isinstance(search, Mapping) or not search.get("items"):
                    report.fail("search returned no results")
                    continue
                anime = search["items"][0]
                anime_id = str(anime["id"])
                report.record(f"search: {anime.get('title', '<untitled>')!r} ({anime_id})")

                t0 = time.perf_counter()
                details = await response_json(
                    await client.get(f"{api_url}/{source_id}/anime/{anime_id}"),
                    f"{source_id} details",
                )
                report.stage_seconds["details"] = time.perf_counter() - t0
                if not isinstance(details, Mapping):
                    report.fail("details response is not an object")
                    continue
                report.record(f"details: {details.get('title', '<untitled>')!r}")

                t0 = time.perf_counter()
                episodes = await response_json(
                    await client.get(f"{api_url}/{source_id}/episodes/{anime_id}"),
                    f"{source_id} episodes",
                )
                report.stage_seconds["episodes"] = time.perf_counter() - t0
                if not isinstance(episodes, list) or not episodes:
                    report.fail("no episodes found")
                    continue
                episode_id = str(episodes[0]["id"])
                report.record(f"episodes: {len(episodes)}; testing episode {episode_id!r}")

                t0 = time.perf_counter()
                servers = await response_json(
                    await client.get(f"{api_url}/{source_id}/servers/{episode_id}"),
                    f"{source_id} servers",
                )
                report.stage_seconds["servers"] = time.perf_counter() - t0
                if not isinstance(servers, list) or not servers:
                    report.fail("no servers found")
                    continue
                report.record(f"servers: {len(servers)}")

                async def get_streams(
                    server_id: str, src_id=source_id, ep_id=episode_id
                ) -> Sequence[Any]:
                    streams = await response_json(
                        await client.get(
                            f"{api_url}/{src_id}/streams/{ep_id}",
                            params={"server_id": server_id},
                        ),
                        f"{src_id} streams for {server_id}",
                    )
                    if not isinstance(streams, list):
                        raise RuntimeError("stream response is not an array")
                    return streams

                t0 = time.perf_counter()
                results = await resolve_servers(
                    [(str(server["id"]), str(server["name"])) for server in servers],
                    get_streams,
                )
                report.stage_seconds["streams"] = time.perf_counter() - t0
                record_stream_results(report, results)
            except (httpx.HTTPError, RuntimeError, KeyError, TypeError) as exc:
                report.fail(f"pipeline error: {type(exc).__name__}: {exc}")
            finally:
                report.finish()

    return reports


async def main(args: argparse.Namespace) -> int:
    """Run selected environments and return a process exit status."""
    if args.timeout <= 0:
        raise ValueError("--timeout must be greater than zero")

    source_filter = set(args.sources) if args.sources else None
    reports: list[PipelineReport] = []
    if not args.deployed_only:
        reports.extend(await test_local(args.query, source_filter))
    if not args.local_only:
        reports.extend(await test_deployed(args.query, args.url, args.timeout, source_filter))

    report_summary(reports)
    return 0 if reports and any(report.status is Status.PASS for report in reports) else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(asyncio.run(main(parse_args())))
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc
