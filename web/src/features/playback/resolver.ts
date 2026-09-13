import type { AniListMedia } from "~/api/anilist";
import {
  type AnimeItem,
  type SourceInfo,
  fetchSources,
  searchSource,
} from "~/api/anisource";
import {
  extractSeasonNumber,
  normalizeTitle,
  similarityRatio,
  tokenJaccardSimilarity,
} from "~/lib/string-matching";

const RESOLVER_CACHE_KEY = "anisource_resolver_v1";
const LAST_SOURCE_KEY = "anisource_last_source_id";

export interface CachedResolution {
  anilistId: number;
  sourceId: string;
  animeId: string;
  title: string;
  timestamp: number;
  score: number;
  provenance: "auto" | "manual";
  sourceFingerprint?: string;
}

export interface CandidateScore {
  candidate: AnimeItem;
  score: number;
  reason: string;
}

export interface ResolutionResult {
  status: "resolved" | "ambiguous" | "not_found";
  sourceId: string;
  sourceName?: string;
  animeId?: string;
  title?: string;
  score?: number;
  provenance?: "cache" | "auto" | "manual";
  candidates?: CandidateScore[];
}

// -----------------------------------------------------------------------------
// Cache Storage
// -----------------------------------------------------------------------------

function getCache(): Record<string, CachedResolution> {
  try {
    const raw = localStorage.getItem(RESOLVER_CACHE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, CachedResolution>) : {};
  } catch {
    return {};
  }
}

function setCache(cache: Record<string, CachedResolution>): void {
  try {
    localStorage.setItem(RESOLVER_CACHE_KEY, JSON.stringify(cache));
  } catch {
    // Storage full or unavailable
  }
}

export function getCachedResolution(
  anilistId: number,
  sourceId: string,
  sourceFingerprint?: string,
): CachedResolution | null {
  const cache = getCache();
  const key = `${anilistId}:${sourceId}`;
  const cached = cache[key];
  if (!cached) return null;

  // A source base URL identifies the scraper catalog that produced the mapping.
  // Do not reuse a mapping after that catalog changes; it may point at a stale ID.
  if (
    sourceFingerprint &&
    cached.sourceFingerprint &&
    cached.sourceFingerprint !== sourceFingerprint
  ) {
    delete cache[key];
    setCache(cache);
    return null;
  }

  return cached;
}

export function saveResolution(
  anilistId: number,
  sourceId: string,
  animeId: string,
  title: string,
  score: number,
  provenance: "auto" | "manual",
  sourceFingerprint?: string,
): void {
  const cache = getCache();
  const key = `${anilistId}:${sourceId}`;
  cache[key] = {
    anilistId,
    sourceId,
    animeId,
    title,
    timestamp: Date.now(),
    score,
    provenance,
    sourceFingerprint,
  };
  setCache(cache);
  setLastSourceId(sourceId);
}

export function getLastSourceId(): string | null {
  try {
    return localStorage.getItem(LAST_SOURCE_KEY);
  } catch {
    return null;
  }
}

export function setLastSourceId(sourceId: string): void {
  try {
    localStorage.setItem(LAST_SOURCE_KEY, sourceId);
  } catch {
    // Local storage unavailable
  }
}

// -----------------------------------------------------------------------------
// Scoring Logic
// -----------------------------------------------------------------------------

export function scoreCandidate(media: AniListMedia, candidate: AnimeItem): CandidateScore {
  const targetTitles: string[] = [
    media.title.english,
    media.title.romaji,
    media.title.userPreferred,
    media.title.native,
    ...(media.synonyms || []),
  ].filter((t): t is string => Boolean(t && t.trim().length > 0));

  let maxTitleSim = 0;
  let maxJaccard = 0;
  let exactMatch = false;

  const candNorm = normalizeTitle(candidate.title);

  for (const t of targetTitles) {
    const norm = normalizeTitle(t);
    if (!norm) continue;

    if (norm === candNorm) {
      exactMatch = true;
      maxTitleSim = 1.0;
      maxJaccard = 1.0;
      break;
    }

    const sim = similarityRatio(norm, candNorm);
    const jaccard = tokenJaccardSimilarity(norm, candNorm);

    if (sim > maxTitleSim) maxTitleSim = sim;
    if (jaccard > maxJaccard) maxJaccard = jaccard;
  }

  // Base score from weighted string similarity
  let baseScore = exactMatch ? 1.0 : maxTitleSim * 0.65 + maxJaccard * 0.35;
  const reasons: string[] = [];

  if (exactMatch) {
    reasons.push("Exact normalized title match");
  } else {
    reasons.push(`Title similarity: ${(baseScore * 100).toFixed(0)}%`);
  }

  // Season / Sequel Alignment
  const targetSeasonNum =
    extractSeasonNumber(media.title.english || "") ||
    extractSeasonNumber(media.title.romaji || "") ||
    extractSeasonNumber(media.title.userPreferred || "");

  const candSeasonNum = extractSeasonNumber(candidate.title);

  if (targetSeasonNum !== null && candSeasonNum !== null) {
    if (targetSeasonNum === candSeasonNum) {
      baseScore += 0.1;
      reasons.push(`Season match (S${targetSeasonNum})`);
    } else {
      baseScore -= 0.45;
      reasons.push(`Season mismatch (target S${targetSeasonNum} vs S${candSeasonNum})`);
    }
  } else if (targetSeasonNum !== null && candSeasonNum === null) {
    // Target expects Season N, but candidate has no season indicator
    if (targetSeasonNum > 1) {
      baseScore -= 0.35;
      reasons.push(`Missing expected season ${targetSeasonNum}`);
    }
  } else if (targetSeasonNum === null && candSeasonNum !== null) {
    // Target is base/S1, candidate is S2+
    if (candSeasonNum > 1) {
      baseScore -= 0.35;
      reasons.push(`Unexpected sequel season ${candSeasonNum}`);
    }
  }

  // Format considerations
  const candLower = candidate.title.toLowerCase();
  if (media.format === "MOVIE") {
    if (candLower.includes("movie") || candLower.includes("the movie") || candLower.includes("film")) {
      baseScore += 0.1;
      reasons.push("Movie indicator match");
    } else if (candLower.includes("season") || candLower.includes("tv")) {
      baseScore -= 0.3;
      reasons.push("Format conflict: target is Movie");
    }
  } else if (media.format === "TV" || media.format === "TV_SHORT") {
    if (candLower.includes("movie") && !media.title.romaji?.toLowerCase().includes("movie")) {
      baseScore -= 0.35;
      reasons.push("Format conflict: candidate contains 'movie' for TV series");
    }
  }

  // Dub tag alignment
  if (candLower.includes("(dub)") || candLower.includes("[dub]")) {
    baseScore -= 0.05; // Slight preference for sub/base catalog
  }

  const finalScore = Math.max(0, Math.min(1.0, baseScore));
  return {
    candidate,
    score: Number(finalScore.toFixed(3)),
    reason: reasons.join("; "),
  };
}

// -----------------------------------------------------------------------------
// Execution Flow
// -----------------------------------------------------------------------------

export async function resolveAniListToSource(
  media: AniListMedia,
  selectedSourceId?: string,
  signal?: AbortSignal,
): Promise<ResolutionResult> {
  const sources = await fetchSources(signal);
  if (!sources.length) {
    return { status: "not_found", sourceId: "" };
  }

  // Determine source resolution order
  const lastSourceId = getLastSourceId();
  const preferredSourceId = selectedSourceId || lastSourceId || sources[0].id;

  const orderedSources: SourceInfo[] = [];
  const primary = sources.find((s) => s.id === preferredSourceId) || sources[0];
  orderedSources.push(primary);
  for (const s of sources) {
    if (s.id !== primary.id) orderedSources.push(s);
  }

  // 1. Check Cache for Primary Source
  const cached = getCachedResolution(media.id, primary.id, primary.base_url);
  if (cached) {
    return {
      status: "resolved",
      sourceId: primary.id,
      sourceName: primary.name,
      animeId: cached.animeId,
      title: cached.title,
      score: cached.score,
      provenance: "cache",
    };
  }

  // Search queries to try
  const queriesToTry = Array.from(
    new Set(
      [media.title.english, media.title.romaji, media.title.userPreferred]
        .filter((t): t is string => Boolean(t && t.trim().length > 0))
        .map((t) => t.trim()),
    ),
  );

  let accumulatedCandidates: CandidateScore[] = [];

  // 2. Query Sources sequentially
  for (const source of orderedSources) {
    const candidateMap = new Map<string, AnimeItem>();

    for (const q of queriesToTry) {
      if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
      try {
        const response = await searchSource(source.id, q, 1, signal);
        for (const item of response.items) {
          if (!candidateMap.has(item.id)) {
            candidateMap.set(item.id, item);
          }
        }
        if (candidateMap.size >= 8) break;
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") throw err;
        // Continue fallback
      }
    }

    if (candidateMap.size === 0) {
      continue;
    }

    const scored = Array.from(candidateMap.values())
      .map((item) => scoreCandidate(media, item))
      .sort((a, b) => b.score - a.score);

    accumulatedCandidates = scored;

    const top = scored[0];
    const second = scored[1];

    // High confidence match
    if (top && top.score >= 0.82) {
      // Check if it's distinctly better than #2 if #2 exists
      const margin = second ? top.score - second.score : 1.0;
      if (margin >= 0.1 || top.score >= 0.95) {
        saveResolution(media.id, source.id, top.candidate.id, top.candidate.title, top.score, "auto", source.base_url);
        return {
          status: "resolved",
          sourceId: source.id,
          sourceName: source.name,
          animeId: top.candidate.id,
          title: top.candidate.title,
          score: top.score,
          provenance: "auto",
        };
      }
    }

    // If we have plausible candidates but ambiguous, prompt user
    if (top && top.score >= 0.5) {
      return {
        status: "ambiguous",
        sourceId: source.id,
        sourceName: source.name,
        candidates: scored.slice(0, 6),
      };
    }
  }

  if (accumulatedCandidates.length > 0) {
    return {
      status: "ambiguous",
      sourceId: primary.id,
      sourceName: primary.name,
      candidates: accumulatedCandidates.slice(0, 6),
    };
  }

  return {
    status: "not_found",
    sourceId: primary.id,
    sourceName: primary.name,
  };
}
