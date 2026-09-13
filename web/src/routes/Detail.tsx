import { A, useParams } from "@solidjs/router";
import { createQuery } from "@tanstack/solid-query";
import { createSignal, For, onCleanup, onMount, Show } from "solid-js";
import { type AniListMedia, anilistRequest, DETAIL_QUERY } from "~/api/anilist";
import { AnimeRail } from "~/features/catalog/AnimeRail";
import { getHistoryForAnime } from "~/features/library/history";
import { isInMyList, toggleMyList } from "~/features/library/my-list";
import "./Detail.css";

export default function Detail() {
  const params = useParams();
  const mediaId = () => Number(params.id);

  const [inList, setInList] = createSignal(false);
  const [historyEntry, setHistoryEntry] = createSignal(getHistoryForAnime(mediaId()));

  const syncState = () => {
    setInList(isInMyList(mediaId()));
    setHistoryEntry(getHistoryForAnime(mediaId()));
  };

  onMount(() => {
    syncState();
    window.addEventListener("anisource_history_change", syncState);
    window.addEventListener("anisource_list_change", syncState);
  });

  onCleanup(() => {
    window.removeEventListener("anisource_history_change", syncState);
    window.removeEventListener("anisource_list_change", syncState);
  });

  const query = createQuery(() => ({
    queryKey: ["anime", "detail", mediaId()],
    queryFn: ({ signal }) =>
      anilistRequest<{ Media: AniListMedia }>(DETAIL_QUERY, { id: mediaId() }, signal),
    enabled: Boolean(mediaId() && !Number.isNaN(mediaId())),
    staleTime: 1000 * 60 * 15, // 15 minutes
  }));

  const media = () => query.data?.Media;

  const handleListToggle = () => {
    toggleMyList(mediaId());
    setInList(isInMyList(mediaId()));
  };

  const cleanDescription = (raw?: string | null) => {
    if (!raw) return "";
    return raw.replace(/<br\s*[\/]?>/gi, "\n").replace(/<[^>]+>/g, "");
  };

  const relations = () =>
    (media()?.relations?.edges ?? [])
      .map((edge) => edge.node)
      .filter((n): n is AniListMedia => Boolean(n));

  const recommendations = () =>
    (media()?.recommendations?.nodes ?? [])
      .map((node) => node.mediaRecommendation)
      .filter((m): m is AniListMedia => Boolean(m));

  return (
    <div class="detail-page">
      <Show when={query.isLoading}>
        <div class="loading-state page-shell">Loading anime details…</div>
      </Show>

      <Show when={query.isError}>
        <div class="empty-state page-shell detail-error">
          <strong>Unable to load this anime.</strong>
          <span>{query.error instanceof Error ? query.error.message : "AniList did not return the details."}</span>
          <button class="btn primary-btn" type="button" onClick={() => void query.refetch()}>
            Try again
          </button>
        </div>
      </Show>

      <Show when={media()}>
        {(item) => (
          <>
            {/* Backdrop Banner */}
            <div class="detail-hero">
              <div
                class="detail-backdrop"
                style={{
                  "background-image": `url(${item().bannerImage || item().coverImage.extraLarge})`,
                }}
              />
              <div class="detail-backdrop-overlay" />
            </div>

            <div class="detail-main page-shell">
              <div class="detail-layout">
                {/* Poster & Action Sidebar */}
                <div class="detail-sidebar">
                  <div class="detail-poster-wrap">
                    <img
                      src={item().coverImage.extraLarge || item().coverImage.large}
                      alt={item().title.english || item().title.romaji}
                      class="detail-poster"
                      loading="eager"
                      decoding="async"
                    />
                  </div>

                  <div class="detail-actions">
                    <Show
                      when={historyEntry()}
                      fallback={
                        <A href={`/watch/${item().id}`} class="btn primary-btn detail-watch-btn">
                          ▶ Watch Now
                        </A>
                      }
                    >
                      {(hist) => (
                        <A
                          href={`/watch/${item().id}?ep=${hist().episodeNumber}&source=${hist().sourceId}`}
                          class="btn primary-btn detail-watch-btn"
                        >
                          ▶ Resume Ep {hist().episodeNumber} ({hist().progressPercent}%)
                        </A>
                      )}
                    </Show>

                    <button
                      class={`btn list-btn ${inList() ? "active" : ""}`}
                      onClick={handleListToggle}
                    >
                      {inList() ? "✓ In My List" : "+ Add to My List"}
                    </button>
                  </div>

                  <div class="detail-facts">
                    <h3 class="facts-title">Information</h3>
                    <div class="fact-row">
                      <span class="fact-label">Format</span>
                      <span class="fact-val">{item().format?.replace(/_/g, " ") || "—"}</span>
                    </div>
                    <div class="fact-row">
                      <span class="fact-label">Status</span>
                      <span class="fact-val">{item().status?.replace(/_/g, " ") || "—"}</span>
                    </div>
                    <div class="fact-row">
                      <span class="fact-label">Episodes</span>
                      <span class="fact-val">{item().episodes || "—"}</span>
                    </div>
                    <div class="fact-row">
                      <span class="fact-label">Duration</span>
                      <span class="fact-val">
                        {item().duration ? `${item().duration} min` : "—"}
                      </span>
                    </div>
                    <div class="fact-row">
                      <span class="fact-label">Season</span>
                      <span class="fact-val">
                        {item().season ? `${item().season} ${item().seasonYear || ""}` : "—"}
                      </span>
                    </div>
                    <div class="fact-row">
                      <span class="fact-label">Studio</span>
                      <span class="fact-val">
                        {item().studios?.nodes?.find((s) => s.isAnimationStudio)?.name ||
                          item().studios?.nodes?.[0]?.name ||
                          "—"}
                      </span>
                    </div>
                    <div class="fact-row">
                      <span class="fact-label">AniList Score</span>
                      <span class="fact-val">
                        {item().averageScore ? `${item().averageScore}%` : "—"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Main Content Area */}
                <div class="detail-content">
                  <div class="detail-header-info">
                    <div class="detail-badges">
                      <Show when={item().format}>
                        <span class="badge format-badge">{item().format?.replace(/_/g, " ")}</span>
                      </Show>
                      <Show when={item().status}>
                        <span class="badge">{item().status?.replace(/_/g, " ")}</span>
                      </Show>
                      <Show when={item().averageScore}>
                        <span class="badge score-badge">★ {item().averageScore}%</span>
                      </Show>
                    </div>

                    <h1 class="detail-title display-title">
                      {item().title.english || item().title.romaji || item().title.userPreferred}
                    </h1>

                    <Show when={item().title.native}>
                      <div class="detail-native-title">{item().title.native}</div>
                    </Show>

                    <Show when={item().genres && item().genres!.length > 0}>
                      <div class="detail-genres">
                        <For each={item().genres}>
                          {(g) => (
                            <A href={`/browse?genre=${encodeURIComponent(g)}`} class="genre-pill">
                              {g}
                            </A>
                          )}
                        </For>
                      </div>
                    </Show>
                  </div>

                  <div class="detail-synopsis-section">
                    <h2 class="section-heading">Synopsis</h2>
                    <p class="detail-synopsis-text">{cleanDescription(item().description)}</p>
                  </div>

                  {/* Characters */}
                  <Show when={item().characters?.edges && item().characters!.edges.length > 0}>
                    <div class="detail-characters-section">
                      <h2 class="section-heading">Characters & Cast</h2>
                      <div class="characters-grid">
                        <For each={item().characters!.edges.slice(0, 8)}>
                          {(charEdge) => (
                            <div class="character-card">
                              <img
                                src={charEdge.node.image?.large}
                                alt={charEdge.node.name.full}
                                class="character-avatar"
                                loading="lazy"
                              />
                              <div class="character-names">
                                <div class="character-name">{charEdge.node.name.full}</div>
                                <div class="character-role">{charEdge.role}</div>
                                <Show when={charEdge.voiceActors?.[0]}>
                                  <div class="va-name">VA: {charEdge.voiceActors![0].full}</div>
                                </Show>
                              </div>
                            </div>
                          )}
                        </For>
                      </div>
                    </div>
                  </Show>

                  {/* Relations */}
                  <Show when={relations().length > 0}>
                    <div class="detail-rail-section">
                      <AnimeRail title="Related Works" items={relations()} />
                    </div>
                  </Show>

                  {/* Recommendations */}
                  <Show when={recommendations().length > 0}>
                    <div class="detail-rail-section">
                      <AnimeRail title="Recommended" items={recommendations()} />
                    </div>
                  </Show>
                </div>
              </div>
            </div>
          </>
        )}
      </Show>
    </div>
  );
}
