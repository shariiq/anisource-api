import { useNavigate, useParams, useSearchParams } from "@solidjs/router";
import { createQuery } from "@tanstack/solid-query";
import { createEffect, createMemo, createSignal, For, Show } from "solid-js";
import { type AniListMedia, anilistRequest, DETAIL_QUERY } from "~/api/anilist";
import {
  fetchEpisodes,
  fetchServers,
  fetchSources,
  fetchStreams,
} from "~/api/anisource";
import { VideoPlayer } from "~/features/playback/VideoPlayer";
import {
  resolveAniListToSource,
  saveResolution,
  type CandidateScore,
  type ResolutionResult,
} from "~/features/playback/resolver";
import { getHistoryForAnime } from "~/features/library/history";
import "./Watch.css";

type AudioPreference = "sub" | "dub";

export default function Watch() {
  const params = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const mediaId = () => Number(params.id);
  const history = () => getHistoryForAnime(mediaId());
  const requestedEpisode = () => Number(searchParams.ep || history()?.episodeNumber || 1);
  const requestedSource = () => String(searchParams.source || history()?.sourceId || "");

  // 1. Manual resolution override (for ambiguous matches)
  const [manualResolution, setManualResolution] = createSignal<ResolutionResult | null>(null);

  // 2. Base Data: Anime Details & Source List
  const detailQuery = createQuery(() => ({
    queryKey: ["anime", "detail", mediaId()],
    queryFn: ({ signal }) => anilistRequest<{ Media: AniListMedia }>(DETAIL_QUERY, { id: mediaId() }, signal),
    enabled: Boolean(mediaId() && !Number.isNaN(mediaId())),
    staleTime: 1000 * 60 * 15,
  }));

  const sourcesQuery = createQuery(() => ({
    queryKey: ["playback", "sources"],
    queryFn: ({ signal }) => fetchSources(signal),
    staleTime: 1000 * 60 * 30,
  }));

  const media = () => detailQuery.data?.Media;

  // 3. Source Selection
  const [selectedSourceId, setSelectedSourceId] = createSignal(requestedSource());

  // Initialize source from history or first available
  createEffect(() => {
    if (!selectedSourceId() && sourcesQuery.data?.length) {
      setSelectedSourceId(requestedSource() || sourcesQuery.data[0].id);
    }
  });

  // 4. Resolution Chain: Map AniList ID + Source ID -> Source Anime ID
  // Uses manualResolution override if present, otherwise uses the query
  const resolutionQuery = createQuery(() => ({
    queryKey: ["playback", "resolution", mediaId(), selectedSourceId()],
    queryFn: async ({ signal }) => {
      const m = media();
      const s = selectedSourceId();
      if (!m || !s) throw new Error("Missing media or source for resolution");
      return await resolveAniListToSource(m, s, signal);
    },
    enabled: Boolean(media() && selectedSourceId()),
    staleTime: 1000 * 60 * 60, // Cache resolution for an hour
  }));

  // Use manual resolution override if present
  const resolution = () => manualResolution() ?? resolutionQuery.data;
  const sourceId = createMemo(() => resolution()?.sourceId || "");
  const animeId = createMemo(() => resolution()?.animeId || "");

  // 5. Episode Chain: Depends on resolution
  const episodeQuery = createQuery(() => ({
    queryKey: ["playback", "episodes", sourceId(), animeId()],
    queryFn: ({ signal }) => fetchEpisodes(sourceId(), animeId(), signal),
    enabled: Boolean(sourceId() && animeId()),
    staleTime: 1000 * 60 * 5,
  }));

  const episodes = () => episodeQuery.data ?? [];
  const [episodeFilter, setEpisodeFilter] = createSignal("");
  const visibleEpisodes = () => {
    const filter = episodeFilter().trim().toLowerCase();
    if (!filter) return episodes();
    return episodes().filter((ep) =>
      String(ep.number).includes(filter) || ep.title.toLowerCase().includes(filter)
    );
  };

  const [selectedEpisodeId, setSelectedEpisodeId] = createSignal("");
  const currentEpisode = createMemo(() => {
    const list = episodes();
    if (!list.length) return null;
    // Priority: selectedEpisodeId signal > requestedEpisode (URL/history) > first episode
    return list.find((ep) => ep.id === selectedEpisodeId()) ||
           list.find((ep) => ep.number === requestedEpisode()) ||
           list[0];
  });

  // Auto-select episode ID to keep signals in sync
  createEffect(() => {
    const ep = currentEpisode();
    if (ep && selectedEpisodeId() !== ep.id) {
      setSelectedEpisodeId(ep.id);
    }
  });

  // 6. Server Chain: Depends on episode
  const [audioPreference, setAudioPreference] = createSignal<AudioPreference>("sub");

  const serversQuery = createQuery(() => ({
    queryKey: ["playback", "servers", sourceId(), currentEpisode()?.id],
    queryFn: ({ signal }) => fetchServers(sourceId(), currentEpisode()!.id, signal),
    enabled: Boolean(sourceId() && currentEpisode()?.id),
    staleTime: 1000 * 30,
  }));

  const servers = () => (serversQuery.data ?? []).filter((s) => s.type.toLowerCase() === audioPreference());

  // 7. Stream Chain: Depends on server
  const [selectedServerId, setSelectedServerId] = createSignal("");

  const streamQuery = createQuery(() => ({
    queryKey: ["playback", "streams", sourceId(), currentEpisode()?.id, selectedServerId()],
    queryFn: ({ signal }) => fetchStreams(sourceId(), currentEpisode()!.id, selectedServerId(), signal),
    enabled: Boolean(sourceId() && currentEpisode()?.id && selectedServerId()),
    staleTime: 1000 * 60 * 5,
  }));

  const selectedStream = () => {
    const streams = streamQuery.data;
    return streams && streams.length > 0 ? streams[0] : null;
  };

  // Helpers
  const languageAvailable = (lang: AudioPreference) => {
    const ep = currentEpisode();
    return lang === "sub" ? Boolean(ep?.has_sub) : Boolean(ep?.has_dub);
  };

  const selectCandidate = (candidate: CandidateScore) => {
    const res = resolutionQuery.data; // Get the base resolution from query
    if (!res) return;
    saveResolution(mediaId(), res.sourceId, candidate.candidate.id, candidate.candidate.title, candidate.score, "manual");
    setManualResolution({
      ...res,
      status: "resolved",
      animeId: candidate.candidate.id,
      title: candidate.candidate.title,
      score: candidate.score,
      provenance: "manual",
    });
  };

  const title = () => media()?.title.english || media()?.title.romaji || media()?.title.userPreferred || "Anime";
  const poster = () => media()?.coverImage.large || media()?.coverImage.extraLarge || "";

  return (
    <div class="watch-page page-shell">
      <div class="watch-topbar">
        <button class="back-link" type="button" onClick={() => navigate(-1)}>← Back</button>
        <div>
          <p class="eyebrow">Playback</p>
          <h1 class="watch-title display-title">{title()}</h1>
        </div>
      </div>

      <section class="watch-panel playback-options">
        <div class="watch-panel-heading"><h2 class="section-heading">Source</h2></div>
        <div class="source-list" aria-label="Anime source">
          <For each={sourcesQuery.data ?? []}>
            {(source) => (
              <button
                class={`source-chip ${selectedSourceId() === source.id ? "active" : ""}`}
                type="button"
                onClick={() => {
                  setSelectedSourceId(source.id);
                  setManualResolution(null); // Clear manual resolution when source changes
                }}
              >
                {source.name}
              </button>
            )}
          </For>
        </div>
      </section>

      <Show when={resolutionQuery.isLoading}>
        <div class="inline-loading"><span class="spin" /> Finding a compatible AniSource entry…</div>
      </Show>

      <Show when={resolutionQuery.isError}>
        <div class="inline-error">
          <span>{resolutionQuery.error instanceof Error ? resolutionQuery.error.message : "Unable to resolve source"}</span>
          <button type="button" onClick={() => resolutionQuery.refetch()}>Retry</button>
        </div>
      </Show>

      <Show when={resolution()?.status === "ambiguous" && !manualResolution()}>
        <section class="watch-panel disambiguation-panel">
          <h2 class="section-heading">Choose the matching title</h2>
          <p class="muted">Several source entries matched. Select the one that represents this AniList title.</p>
          <div class="candidate-list">
            <For each={resolution()?.candidates ?? []}>
              {(candidate) => (
                <button class={`candidate-item ${false}`} type="button" onClick={() => selectCandidate(candidate)}>
                  <strong>{candidate.candidate.title}</strong>
                  <span>{Math.round(candidate.score * 100)}% · {candidate.reason}</span>
                </button>
              )}
            </For>
          </div>
        </section>
      </Show>

      <Show when={resolution()?.status === "resolved" && animeId()}>
        <div class="watch-layout">
          <aside class="watch-sidebar">
            <section class="watch-panel">
              <div class="watch-panel-heading">
                <div>
                  <h2 class="section-heading">Episodes</h2>
                  <p class="episode-summary muted">
                    {currentEpisode() ? `Episode ${currentEpisode()!.number} selected` : "Choose an episode"}
                  </p>
                </div>
                <span class="episode-count">{episodes().length}</span>
              </div>
              <input
                class="episode-search"
                type="search"
                placeholder="Find an episode…"
                value={episodeFilter()}
                aria-label="Filter episodes"
                onInput={(event) => setEpisodeFilter(event.currentTarget.value)}
              />
              <div class="episode-list">
                <For each={visibleEpisodes()}>
                  {(episode) => (
                    <button
                      class={`episode-item ${currentEpisode()?.id === episode.id ? "active" : ""}`}
                      type="button"
                      aria-pressed={currentEpisode()?.id === episode.id}
                      onClick={() => { setSelectedEpisodeId(episode.id); setSelectedServerId(""); }}
                    >
                      <span class="episode-number">EP {episode.number}</span>
                      <span class="episode-label">{episode.title || `Episode ${episode.number}`}</span>
                      <span class="episode-flags">
                        <Show when={episode.has_sub}><small>Sub</small></Show>
                        <Show when={episode.has_dub}><small>Dub</small></Show>
                      </span>
                    </button>
                  )}
                </For>
              </div>
            </section>
          </aside>

          <main class="watch-main">
            <Show when={selectedStream()} fallback={<div class="player-placeholder">Choose a language and server to begin playback.</div>}>
              {(stream) => (
                <div class="player-box">
                  <VideoPlayer
                    stream={stream()}
                    anilistId={mediaId()}
                    title={title()}
                    poster={poster()}
                    sourceId={sourceId()}
                    sourceAnimeId={animeId()}
                    episodeId={currentEpisode()!.id}
                    episodeNumber={currentEpisode()!.number}
                    serverId={selectedServerId()}
                    initialPosition={history()?.positionSeconds}
                    onError={(msg) => console.error("Player error:", msg)}
                  />
                </div>
              )}
            </Show>

            <section class="watch-panel server-panel">
              <div class="watch-panel-heading">
                <h2 class="section-heading">Playback options</h2>
                <Show when={serversQuery.isLoading}><span class="muted">Loading…</span></Show>
              </div>
              <div class="language-list" aria-label="Audio language">
                <button
                  class={`language-chip ${audioPreference() === "sub" ? "active" : ""}`}
                  type="button"
                  disabled={!languageAvailable("sub")}
                  onClick={() => { setAudioPreference("sub"); setSelectedServerId(""); }}
                >Sub</button>
                <button
                  class={`language-chip ${audioPreference() === "dub" ? "active" : ""}`}
                  type="button"
                  disabled={!languageAvailable("dub")}
                  onClick={() => { setAudioPreference("dub"); setSelectedServerId(""); }}
                >Dub</button>
              </div>
              <div class="server-list">
                <For each={servers()}>
                  {(server) => (
                    <button
                      class={`server-chip ${selectedServerId() === server.id ? "active" : ""}`}
                      type="button"
                      onClick={() => setSelectedServerId(server.id)}
                    >
                      {server.name}
                    </button>
                  )}
                </For>
              </div>
              <Show when={!serversQuery.isLoading && currentEpisode() && !servers().length}>
                <p class="muted server-empty">No {audioPreference()} server is available for this episode.</p>
              </Show>
            </section>
          </main>
        </div>
      </Show>

      <Show when={!resolutionQuery.isLoading && resolution()?.status === "not_found"}>
        <div class="empty-state">Choose another source above, then try again.</div>
      </Show>
    </div>
  );
}