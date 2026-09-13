import { A, useSearchParams } from "@solidjs/router";
import { createQuery } from "@tanstack/solid-query";
import { createEffect, createSignal, For, Show } from "solid-js";
import {
  ANILIST_FORMATS,
  ANILIST_SEASONS,
  ANILIST_SORTS,
  ANILIST_STATUSES,
  type AniListFormat,
  type AniListMedia,
  type AniListPage,
  type AniListSeason,
  type AniListSort,
  type AniListStatus,
  anilistRequest,
  BROWSE_QUERY,
  SEARCH_SUGGESTIONS_QUERY,
} from "~/api/anilist";
import { AnimeCard } from "~/features/catalog/AnimeCard";
import "./Browse.css";

const GENRES = [
  "Action",
  "Adventure",
  "Comedy",
  "Drama",
  "Ecchi",
  "Fantasy",
  "Horror",
  "Mahou Shoujo",
  "Mecha",
  "Music",
  "Mystery",
  "Psychological",
  "Romance",
  "Sci-Fi",
  "Slice of Life",
  "Sports",
  "Supernatural",
  "Thriller",
];

export default function Browse() {
  const [params, setParams] = useSearchParams();

  const search = () => (params.q ? String(params.q) : "");
  const genre = () => (params.genre ? String(params.genre) : "");
  const format = () => (params.format as AniListFormat) || undefined;
  const status = () => (params.status as AniListStatus) || undefined;
  const season = () => (params.season as AniListSeason) || undefined;
  const seasonYear = () => (params.year ? Number(params.year) : undefined);
  const sort = () => ((params.sort as AniListSort) || "POPULARITY_DESC") as AniListSort;
  const page = () => (params.page ? Number(params.page) : 1);

  const [searchInput, setSearchInput] = createSignal(search());
  let debounceTimer: number | undefined;

  createEffect(() => {
    setSearchInput(search());
  });

  const handleSearchInput = (val: string) => {
    setSearchInput(val);
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => {
      setParams({ q: val.trim() || undefined, page: undefined });
    }, 300);
  };

  const setFilter = (key: string, value: string | undefined) => {
    setParams({ [key]: value || undefined, page: undefined });
  };

  // Main Browse Query
  const browseQuery = createQuery(() => ({
    queryKey: [
      "anime",
      "browse",
      {
        search: search() || undefined,
        genre: genre() || undefined,
        format: format(),
        status: status(),
        season: season(),
        seasonYear: seasonYear(),
        sort: sort(),
        page: page(),
      },
    ],
    queryFn: ({ signal }) =>
      anilistRequest<{ Page: AniListPage<AniListMedia> }>(
        BROWSE_QUERY,
        {
          search: search() || undefined,
          genre: genre() || undefined,
          format: format(),
          status: status(),
          season: season(),
          seasonYear: seasonYear(),
          sort: [sort()],
          page: page(),
          perPage: 24,
        },
        signal,
      ),
    staleTime: 1000 * 60 * 5, // 5 minutes
    placeholderData: (prev) => prev,
  }));

  // Debounced search suggestions query when typing actively
  const suggestionQuery = createQuery(() => ({
    queryKey: ["anime", "suggestions", searchInput().trim()],
    queryFn: ({ signal }) =>
      anilistRequest<{ Page: AniListPage<AniListMedia> }>(
        SEARCH_SUGGESTIONS_QUERY,
        { search: searchInput().trim() },
        signal,
      ),
    enabled: searchInput().trim().length >= 2 && searchInput().trim() !== search(),
    staleTime: 1000 * 60 * 2,
  }));

  const items = () => browseQuery.data?.Page?.media ?? [];
  const pageInfo = () => browseQuery.data?.Page?.pageInfo;

  return (
    <div class="browse-page page-shell">
      <div class="browse-header">
        <h1 class="browse-title display-title">Catalog</h1>
        <p class="browse-subtitle muted">Explore and search the complete anime directory</p>
      </div>

      <div class="browse-search-bar">
        <span class="search-icon">⌕</span>
        <input
          type="search"
          class="search-input"
          placeholder="Search by title, synonyms, or keywords…"
          value={searchInput()}
          onInput={(e) => handleSearchInput(e.currentTarget.value)}
        />
        <Show when={search()}>
          <button class="clear-search-btn" onClick={() => handleSearchInput("")}>
            ×
          </button>
        </Show>
      </div>

      <Show when={suggestionQuery.data?.Page?.media && suggestionQuery.data.Page.media.length > 0}>
        <div class="search-suggestions-dropdown">
          <For each={suggestionQuery.data!.Page.media}>
            {(item) => (
              <A href={`/anime/${item.id}`} class="suggestion-item">
                <img
                  src={item.coverImage.large}
                  alt={item.title.english || item.title.romaji}
                  class="suggestion-thumb"
                />
                <div class="suggestion-info">
                  <div class="suggestion-title">
                    {item.title.english || item.title.romaji || item.title.userPreferred}
                  </div>
                  <div class="suggestion-meta">
                    <span>{item.format?.replace(/_/g, " ")}</span>
                    <Show when={item.seasonYear}>
                      <span>{item.seasonYear}</span>
                    </Show>
                  </div>
                </div>
              </A>
            )}
          </For>
        </div>
      </Show>

      {/* Filter Toolbar */}
      <div class="filter-toolbar">
        <div class="filter-group">
          <label class="filter-label">Genre</label>
          <select
            class="filter-select"
            value={genre()}
            onChange={(e) => setFilter("genre", e.currentTarget.value)}
          >
            <option value="">All Genres</option>
            <For each={GENRES}>{(g) => <option value={g}>{g}</option>}</For>
          </select>
        </div>

        <div class="filter-group">
          <label class="filter-label">Format</label>
          <select
            class="filter-select"
            value={format() || ""}
            onChange={(e) => setFilter("format", e.currentTarget.value)}
          >
            <option value="">All Formats</option>
            <For each={ANILIST_FORMATS}>
              {(f) => <option value={f}>{f.replace(/_/g, " ")}</option>}
            </For>
          </select>
        </div>

        <div class="filter-group">
          <label class="filter-label">Status</label>
          <select
            class="filter-select"
            value={status() || ""}
            onChange={(e) => setFilter("status", e.currentTarget.value)}
          >
            <option value="">All Statuses</option>
            <For each={ANILIST_STATUSES}>
              {(s) => <option value={s}>{s.replace(/_/g, " ")}</option>}
            </For>
          </select>
        </div>

        <div class="filter-group">
          <label class="filter-label">Season</label>
          <select
            class="filter-select"
            value={season() || ""}
            onChange={(e) => setFilter("season", e.currentTarget.value)}
          >
            <option value="">All Seasons</option>
            <For each={ANILIST_SEASONS}>{(s) => <option value={s}>{s}</option>}</For>
          </select>
        </div>

        <div class="filter-group">
          <label class="filter-label">Sort</label>
          <select
            class="filter-select"
            value={sort()}
            onChange={(e) => setFilter("sort", e.currentTarget.value)}
          >
            <For each={ANILIST_SORTS}>
              {(s) => (
                <option value={s}>
                  {s.replace(/_/g, " ").replace("DESC", "↓").replace("ASC", "↑")}
                </option>
              )}
            </For>
          </select>
        </div>
      </div>

      {/* Grid Content */}
      <div class="browse-grid-container">
        <Show when={browseQuery.isLoading && !browseQuery.data}>
          <div class="loading-state">Loading catalogue…</div>
        </Show>

        <Show when={items().length > 0}>
          <div class="browse-grid">
            <For each={items()}>{(media) => <AnimeCard media={media} />}</For>
          </div>
        </Show>

        <Show when={!browseQuery.isLoading && items().length === 0}>
          <div class="empty-state">No anime found matching the selected filters.</div>
        </Show>
      </div>

      {/* Pagination */}
      <Show when={pageInfo() && (pageInfo()!.hasNextPage || page() > 1)}>
        <div class="pagination">
          <button
            class="btn pagination-btn"
            disabled={page() <= 1}
            onClick={() => setParams({ page: page() > 2 ? String(page() - 1) : undefined })}
          >
            Previous
          </button>
          <span class="pagination-current">
            Page {page()} {pageInfo()?.total ? `of ${Math.ceil(pageInfo()!.total / 24)}` : ""}
          </span>
          <button
            class="btn pagination-btn"
            disabled={!pageInfo()?.hasNextPage}
            onClick={() => setParams({ page: String(page() + 1) })}
          >
            Next
          </button>
        </div>
      </Show>
    </div>
  );
}
