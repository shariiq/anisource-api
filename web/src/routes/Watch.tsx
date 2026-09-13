import { useNavigate, useParams, useSearchParams } from "@solidjs/router";
import { createQuery } from "@tanstack/solid-query";
import { createEffect, createMemo, createSignal, For, on, onCleanup, Show } from "solid-js";
import { type AniListMedia, anilistRequest, DETAIL_QUERY } from "~/api/anilist";
import {
  type ServerItem,
  type StreamItem,
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

  const detailQuery = createQuery(() => ({
    queryKey: ["anime", "detail", mediaId()],
    queryFn: ({ signal }) =>
      anilistRequest<{ Media: AniListMedia }>(DETAIL_QUERY, { id: mediaId() }, signal),
    enabled: Boolean(mediaId() && !Number.isNaN(mediaId())),
    staleTime: 1000 * 60 * 15,
  }));
  const sourcesQuery = createQuery(() => ({
    queryKey: ["playback", "sources"],
    queryFn: ({ signal }) => fetchSources(signal),
    staleTime: 1000 * 60 * 30,
  }));

  const media = () => detailQuery.data?.Media;
  const [selectedSourceId, setSelectedSourceId] = createSignal(requestedSource());
  const [resolution, setResolution] = createSignal<ResolutionResult | null>(null);
  const [selectedCandidate, setSelectedCandidate] = createSignal<CandidateScore | null>(null);
  const [selectedEpisodeId, setSelectedEpisodeId] = createSignal("");
  const [selectedServerId, setSelectedServerId] = createSignal("");
  const [selectedStream, setSelectedStream] = createSignal<StreamItem | null>(null);
  const [audioPreference, setAudioPreference] = createSignal<AudioPreference>("sub");
  const [episodeFilter, setEpisodeFilter] = createSignal("");
  const [error, setError] = createSignal("");
  const [isResolving, setIsResolving] = createSignal(false);
  const [isLoadingStreams, setIsLoadingStreams] = createSignal(false);
  let controller: AbortController | undefined;

  const sourceId = createMemo(() => resolution()?.sourceId || "");
  const animeId = createMemo(() => resolution()?.animeId || "");
  const episodeQuery = createQuery(() => ({
    queryKey: ["playback", "episodes", sourceId(), animeId()],
    queryFn: ({ signal }) => fetchEpisodes(sourceId(), animeId(), signal),
    enabled: Boolean(sourceId() && animeId()),
    staleTime: 1000 * 60 * 5,
  }));
  const episodes = () => episodeQuery.data ?? [];
  const visibleEpisodes = () => {
    const filter = episodeFilter().trim().toLowerCase();
    if (!filter) return episodes();
    return episodes().filter((episode) =>
      String(episode.number).includes(filter) || episode.title.toLowerCase().includes(filter),
    );
  };
  const currentEpisode = createMemo(() => {
    const target = selectedEpisodeId();
    return episodes().find((episode) => episode.id === target) || episodes().find((episode) => episode.number === requestedEpisode());
  });
  const languageAvailable = (language: AudioPreference) => {
    const episode = currentEpisode();
    return language === "sub" ? Boolean(episode?.has_sub) : Boolean(episode?.has_dub);
  };

  const resolve = async (source = selectedSourceId() || undefined) => {
    const currentMedia = media();
    if (!currentMedia || isResolving()) return;
    controller?.abort();
    controller = new AbortController();
    setResolution(null);
    setSelectedCandidate(null);
    setSelectedEpisodeId("");
    setSelectedServerId("");
    setSelectedStream(null);
    setIsResolving(true);
    setError("");
    try {
      const result = await resolveAniListToSource(currentMedia, source, controller.signal);
      setResolution(result);
      if (result.status === "not_found") setError("No playable source matched this title. Choose another source and try again.");
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === "AbortError")) {
        setError(cause instanceof Error ? cause.message : "Unable to resolve a playback source.");
      }
    } finally {
      setIsResolving(false);
    }
  };

  createEffect(() => {
    if (!selectedSourceId() && sourcesQuery.data?.length) {
      setSelectedSourceId(requestedSource() || sourcesQuery.data[0].id);
    }
  });

  createEffect(on(selectedSourceId, (source) => {
    if (media() && source) void resolve(source);
  }, { defer: true }));

  createEffect(on(media, () => {
    if (selectedSourceId()) void resolve(selectedSourceId());
  }));

  createEffect(() => {
    const list = episodes();
    if (!list.length || selectedEpisodeId()) return;
    const match = list.find((episode) => episode.number === requestedEpisode()) || list[0];
    if (match) setSelectedEpisodeId(match.id);
  });

  createEffect(() => {
    if (!languageAvailable(audioPreference()) && languageAvailable(audioPreference() === "sub" ? "dub" : "sub")) {
      setAudioPreference(audioPreference() === "sub" ? "dub" : "sub");
    }
  });

  const selectCandidate = (candidate: CandidateScore) => {
    const result = resolution();
    if (!result) return;
    saveResolution(mediaId(), result.sourceId, candidate.candidate.id, candidate.candidate.title, candidate.score, "manual");
    setSelectedCandidate(candidate);
    setResolution({
      ...result,
      status: "resolved",
      animeId: candidate.candidate.id,
      title: candidate.candidate.title,
      score: candidate.score,
      provenance: "manual",
    });
  };

  const loadStreams = async (server: ServerItem) => {
    const episode = currentEpisode();
    if (!episode || !sourceId()) return;
    setSelectedServerId(server.id);
    setIsLoadingStreams(true);
    setError("");
    try {
      const streams = await fetchStreams(sourceId(), episode.id, server.id);
      if (!streams.length) throw new Error("This server returned no playable streams.");
      setSelectedStream(streams[0]);
    } catch (cause) {
      setSelectedStream(null);
      setError(cause instanceof Error ? cause.message : "Unable to load this server.");
    } finally {
      setIsLoadingStreams(false);
    }
  };

  const serversQuery = createQuery(() => ({
    queryKey: ["playback", "servers", sourceId(), currentEpisode()?.id],
    queryFn: ({ signal }) => fetchServers(sourceId(), currentEpisode()!.id, signal),
    enabled: Boolean(sourceId() && currentEpisode()?.id),
    staleTime: 1000 * 30,
  }));
  const servers = () => (serversQuery.data ?? []).filter((server) => server.type.toLowerCase() === audioPreference());

  onCleanup(() => controller?.abort());

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
                onClick={() => setSelectedSourceId(source.id)}
              >
                {source.name}
              </button>
            )}
          </For>
        </div>
      </section>

      <Show when={isResolving()}>
        <div class="inline-loading"><span class="spin" /> Finding a compatible AniSource entry…</div>
      </Show>
      <Show when={error()}>
        <div class="inline-error">
          <span>{error()}</span>
          <button type="button" onClick={() => void resolve()}>Retry</button>
        </div>
      </Show>

      <Show when={resolution()?.status === "ambiguous"}>
        <section class="watch-panel disambiguation-panel">
          <h2 class="section-heading">Choose the matching title</h2>
          <p class="muted">Several source entries matched. Select the one that represents this AniList title.</p>
          <div class="candidate-list">
            <For each={resolution()?.candidates ?? []}>
              {(candidate) => (
                <button class={`candidate-item ${selectedCandidate()?.candidate.id === candidate.candidate.id ? "active" : ""}`} type="button" onClick={() => selectCandidate(candidate)}>
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
                      onClick={() => { setSelectedEpisodeId(episode.id); setSelectedServerId(""); setSelectedStream(null); }}
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
                    onError={setError}
                  />
                </div>
              )}
            </Show>

            <section class="watch-panel server-panel">
              <div class="watch-panel-heading"><h2 class="section-heading">Playback options</h2><Show when={isLoadingStreams()}><span class="muted">Loading…</span></Show></div>
              <div class="language-list" aria-label="Audio language">
                <button class={`language-chip ${audioPreference() === "sub" ? "active" : ""}`} type="button" aria-pressed={audioPreference() === "sub"} disabled={!languageAvailable("sub")} onClick={() => { setAudioPreference("sub"); setSelectedServerId(""); setSelectedStream(null); }}>Sub</button>
                <button class={`language-chip ${audioPreference() === "dub" ? "active" : ""}`} type="button" aria-pressed={audioPreference() === "dub"} disabled={!languageAvailable("dub")} onClick={() => { setAudioPreference("dub"); setSelectedServerId(""); setSelectedStream(null); }}>Dub</button>
              </div>
              <div class="server-list">
                <For each={servers()}>
                  {(server) => <button class={`server-chip ${selectedServerId() === server.id ? "active" : ""}`} type="button" aria-pressed={selectedServerId() === server.id} onClick={() => void loadStreams(server)}>{server.name}</button>}
                </For>
              </div>
              <Show when={!serversQuery.isLoading && currentEpisode() && !servers().length}>
                <p class="muted server-empty">No {audioPreference()} server is available for this episode.</p>
              </Show>
            </section>
          </main>
        </div>
      </Show>

      <Show when={!isResolving() && resolution()?.status === "not_found"}>
        <div class="empty-state">Choose another source above, then try again.</div>
      </Show>
    </div>
  );
}
