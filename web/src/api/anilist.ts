export const ANILIST_ENDPOINT =
  import.meta.env.VITE_ANILIST_ENDPOINT ?? "https://graphql.anilist.co";

export const ANILIST_FORMATS = ["TV", "TV_SHORT", "MOVIE", "SPECIAL", "OVA", "ONA", "MUSIC"] as const;
export const ANILIST_STATUSES = ["FINISHED", "RELEASING", "NOT_YET_RELEASED", "CANCELLED"] as const;
export const ANILIST_SEASONS = ["WINTER", "SPRING", "SUMMER", "FALL"] as const;
export const ANILIST_SORTS = [
  "SEARCH_MATCH",
  "POPULARITY_DESC",
  "SCORE_DESC",
  "TRENDING_DESC",
  "START_DATE_DESC",
  "UPDATED_AT_DESC",
] as const;

export type AniListFormat = (typeof ANILIST_FORMATS)[number];
export type AniListStatus = (typeof ANILIST_STATUSES)[number];
export type AniListSeason = (typeof ANILIST_SEASONS)[number];
export type AniListSort = (typeof ANILIST_SORTS)[number];

export interface AniListImage {
  large: string;
  extraLarge?: string;
  color?: string;
}

export interface AniListTitle {
  romaji?: string;
  english?: string;
  native?: string;
  userPreferred?: string;
}

export interface AniListName {
  full: string;
  native?: string;
  alternative?: string[];
}

export interface AniListMedia {
  id: number;
  idMal?: number | null;
  title: AniListTitle;
  synonyms: string[];
  type: "ANIME" | "MANGA";
  format?: AniListFormat | null;
  status?: AniListStatus | null;
  season?: AniListSeason | null;
  seasonYear?: number | null;
  episodes?: number | null;
  duration?: number | null;
  averageScore?: number | null;
  meanScore?: number | null;
  popularity?: number | null;
  trending?: number | null;
  isAdult?: boolean;
  isLocked?: boolean;
  countryOfOrigin?: string | null;
  source?: string | null;
  coverImage: AniListImage;
  bannerImage?: string | null;
  color?: string | null;
  description?: string | null;
  genres?: string[];
  tags?: Array<{ id: number; name: string; rank?: number; isMediaSpoiler?: boolean }>;
  studios?: { nodes: Array<{ id: number; name: string; isAnimationStudio?: boolean }> };
  staff?: { edges: Array<{ role: string; node: AniListName }> };
  characters?: {
    edges: Array<{
      role: string;
      node: { id: number; name: AniListName; image?: AniListImage; description?: string | null };
      voiceActors?: Array<AniListName & { id: number; language?: string }>;
    }>;
  };
  relations?: {
    edges: Array<{ relationType: string; node: AniListMedia }>;
  };
  recommendations?: {
    nodes: Array<{ rating: number; mediaRecommendation: AniListMedia | null }>;
  };
  nextAiringEpisode?: { airingAt: number; timeUntilAiring: number; episode: number } | null;
  airingSchedule?: { nodes: AniListAiring[] };
  siteUrl?: string;
}

export interface AniListAiring {
  id: number;
  airingAt: number;
  timeUntilAiring: number;
  episode: number;
  media: Pick<AniListMedia, "id" | "title" | "coverImage" | "format" | "episodes" | "siteUrl">;
}

export interface AniListPage<T> {
  pageInfo: {
    currentPage: number;
    lastPage: number;
    hasNextPage: boolean;
    perPage: number;
    total: number;
  };
  media?: T[];
  airingSchedules?: AniListAiring[];
}

export interface AniListVariables {
  [key: string]: unknown;
}

export class AniListError extends Error {
  readonly status: number;
  readonly errors: Array<{ message: string; status?: number; locations?: unknown }>;

  constructor(status: number, errors: Array<{ message: string; status?: number; locations?: unknown }>) {
    super(errors[0]?.message ?? `AniList request failed (${status})`);
    this.name = "AniListError";
    this.status = status;
    this.errors = errors;
  }
}

interface GraphQLResponse<T> {
  data?: T;
  errors?: Array<{ message: string; status?: number; locations?: unknown }>;
}

export async function anilistRequest<T>(
  query: string,
  variables: AniListVariables = {},
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(ANILIST_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ query, variables }),
    signal,
  });

  const payload = (await response.json()) as GraphQLResponse<T>;
  if (!response.ok || payload.errors?.length || payload.data === undefined) {
    throw new AniListError(response.status, payload.errors ?? [{ message: "AniList returned no data" }]);
  }
  return payload.data;
}

const CARD_FIELDS = `
  id idMal title { romaji english native userPreferred } synonyms
  format status season seasonYear episodes averageScore popularity trending
  coverImage { large extraLarge color } bannerImage siteUrl
`;

export const HOME_QUERY = `
  query Home($season: MediaSeason, $seasonYear: Int, $airingFrom: Int, $airingTo: Int) {
    trending: Page(page: 1, perPage: 12) {
      media(sort: TRENDING_DESC, type: ANIME) { ${CARD_FIELDS} }
    }
    seasonal: Page(page: 1, perPage: 12) {
      media(season: $season, seasonYear: $seasonYear, sort: POPULARITY_DESC, type: ANIME) { ${CARD_FIELDS} }
    }
    topRated: Page(page: 1, perPage: 12) {
      media(sort: SCORE_DESC, type: ANIME) { ${CARD_FIELDS} }
    }
    upcoming: Page(page: 1, perPage: 12) {
      media(status: NOT_YET_RELEASED, sort: START_DATE_DESC, type: ANIME) { ${CARD_FIELDS} }
    }
    airing: Page(page: 1, perPage: 24) {
      airingSchedules(airingAt_greater: $airingFrom, airingAt_lesser: $airingTo, sort: TIME) {
        id airingAt timeUntilAiring episode
        media { id title { romaji english native userPreferred } coverImage { large extraLarge color } format episodes siteUrl }
      }
    }
  }
`;

export const BROWSE_QUERY = `
  query Browse($page: Int, $perPage: Int, $search: String, $genre: String, $format: MediaFormat, $status: MediaStatus, $season: MediaSeason, $seasonYear: Int, $sort: [MediaSort]) {
    Page(page: $page, perPage: $perPage) {
      pageInfo { currentPage lastPage hasNextPage perPage total }
      media(type: ANIME, search: $search, genre: $genre, format: $format, status: $status, season: $season, seasonYear: $seasonYear, sort: $sort) { ${CARD_FIELDS} }
    }
  }
`;

export const SEARCH_SUGGESTIONS_QUERY = `
  query SearchSuggestions($search: String) {
    Page(page: 1, perPage: 6) {
      media(type: ANIME, search: $search, sort: SEARCH_MATCH) { ${CARD_FIELDS} }
    }
  }
`;

export const DETAIL_QUERY = `
  query Detail($id: Int) {
    Media(id: $id, type: ANIME) {
      ${CARD_FIELDS}
      description(asHtml: false) genres source countryOfOrigin duration
      tags { id name rank isMediaSpoiler }
      studios { nodes { id name isAnimationStudio } }
      staff { edges { role node { name { full native alternative } } } }
      characters(sort: ROLE, perPage: 12) { edges { role node { id name { full native } image { large } description } voiceActors { id name { full native } language } } }
      relations { edges { relationType node { ${CARD_FIELDS} } } }
      recommendations(sort: RATING_DESC, perPage: 12) { nodes { rating mediaRecommendation { ${CARD_FIELDS} } } }
      nextAiringEpisode { airingAt timeUntilAiring episode }
      siteUrl
    }
  }
`;

export const AIRING_QUERY = `
  query Schedule($from: Int, $to: Int, $page: Int, $perPage: Int) {
    Page(page: $page, perPage: $perPage) {
      pageInfo { currentPage lastPage hasNextPage perPage total }
      airingSchedules(airingAt_greater: $from, airingAt_lesser: $to, sort: TIME) {
        id airingAt timeUntilAiring episode
        media { id title { romaji english native userPreferred } coverImage { large extraLarge color } format episodes siteUrl }
      }
    }
  }
`;

export const BATCH_MEDIA_QUERY = `
  query BatchMedia($ids: [Int]) {
    Page(page: 1, perPage: 50) {
      media(id_in: $ids, type: ANIME) { ${CARD_FIELDS} }
    }
  }
`;

export async function getMediaById(id: number, signal?: AbortSignal): Promise<AniListMedia> {
  const data = await anilistRequest<{ Media: AniListMedia }>(DETAIL_QUERY, { id }, signal);
  return data.Media;
}

export async function getMediaByIds(ids: number[], signal?: AbortSignal): Promise<AniListMedia[]> {
  if (!ids.length) return [];
  const data = await anilistRequest<{ Page: AniListPage<AniListMedia> }>(BATCH_MEDIA_QUERY, { ids }, signal);
  return data.Page.media ?? [];
}
