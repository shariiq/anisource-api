export interface SourceInfo {
  id: string;
  name: string;
  base_url: string;
}

export interface SourceListResponse {
  sources: SourceInfo[];
  count: number;
}

export interface AnimeItem {
  id: string;
  title: string;
  url: string;
  thumbnail: string;
  description: string;
  genres: string[];
  studios: string[];
  producers: string[];
  alternative_titles: string[];
  status: string;
  score?: number | null;
  tags: string[];
}

export interface PaginatedResponse<T> {
  items: T[];
  page: number;
  has_next: boolean;
  total_returned: number;
}

export interface EpisodeItem {
  id: string;
  number: number;
  title: string;
  is_filler: boolean;
  has_sub: boolean;
  has_dub: boolean;
  scanlator: string;
  released_at?: string | null;
}

export interface ServerItem {
  id: string;
  name: string;
  type: string;
}

export interface SubtitleItem {
  url: string;
  label: string;
  language: string;
}

export interface StreamItem {
  url: string;
  quality: string;
  headers: Record<string, string>;
  subtitles: SubtitleItem[];
  is_hls: boolean;
}

export class AniSourceApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "AniSourceApiError";
    this.status = status;
    this.code = code;
  }
}

const ANISOURCE_API_ORIGIN = (
  import.meta.env.VITE_ANISOURCE_API_URL ?? "https://anisource-api.onrender.com"
).replace(/\/+$/, "");
const API_PREFIX = `${ANISOURCE_API_ORIGIN}/api/v1`;

async function apiFetch<T>(endpoint: string, init?: RequestInit): Promise<T> {
  const url = endpoint.startsWith("http") ? endpoint : `${API_PREFIX}${endpoint}`;
  const response = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let errorMsg = `AniSource API error: ${response.status} ${response.statusText}`;
    let errorCode: string | undefined;
    try {
      const data = await response.json();
      if (data?.error?.message) {
        errorMsg = data.error.message;
        errorCode = data.error.code;
      } else if (data?.detail) {
        errorMsg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // Ignored if non-JSON
    }
    throw new AniSourceApiError(response.status, errorMsg, errorCode);
  }

  return response.json() as Promise<T>;
}

export async function fetchSources(signal?: AbortSignal): Promise<SourceInfo[]> {
  const data = await apiFetch<SourceListResponse>("/sources", { signal });
  return data.sources;
}

export async function searchSource(
  sourceId: string,
  query: string,
  page = 1,
  signal?: AbortSignal,
): Promise<PaginatedResponse<AnimeItem>> {
  const params = new URLSearchParams({
    q: query,
    page: String(page),
  });
  return apiFetch<PaginatedResponse<AnimeItem>>(
    `/${encodeURIComponent(sourceId)}/search?${params.toString()}`,
    { signal },
  );
}

export async function fetchEpisodes(
  sourceId: string,
  animeId: string,
  signal?: AbortSignal,
): Promise<EpisodeItem[]> {
  return apiFetch<EpisodeItem[]>(
    `/${encodeURIComponent(sourceId)}/episodes/${encodeURIComponent(animeId)}`,
    { signal },
  );
}

export async function fetchServers(
  sourceId: string,
  episodeId: string,
  signal?: AbortSignal,
): Promise<ServerItem[]> {
  return apiFetch<ServerItem[]>(
    `/${encodeURIComponent(sourceId)}/servers/${encodeURIComponent(episodeId)}`,
    { signal },
  );
}

export async function fetchStreams(
  sourceId: string,
  episodeId: string,
  serverId: string,
  signal?: AbortSignal,
): Promise<StreamItem[]> {
  const params = new URLSearchParams({
    server_id: serverId,
  });
  return apiFetch<StreamItem[]>(
    `/${encodeURIComponent(sourceId)}/streams/${encodeURIComponent(episodeId)}?${params.toString()}`,
    { signal },
  );
}
