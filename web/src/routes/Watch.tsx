import { useNavigate, useParams, useSearchParams } from "@solidjs/router";
import { createQuery } from "@tanstack/solid-query";
import { createEffect, createMemo, createSignal, For, onCleanup, Show } from "solid-js";
import { type AniListMedia, anilistRequest, DETAIL_QUERY } from "~/api/anilist";
import {
  type ServerItem,
  type StreamItem,
  fetchEpisodes,
  fetchServers,
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

  const media = () => detailQuery.data?.Media;
  const [resolution, setResolution] = createSignal<ResolutionResult | null>(null);
  const [selectedCandidate, setSelectedCandidate] = createSignal<CandidateScore | null>(null);
  const [selectedEpisodeId, setSelectedEpisodeId] = createSignal("");
  const [selectedServerId, setSelectedServerId] = createSignal("");
  const [selectedStream, setSelectedStream] = createSignal<StreamItem | null>(null);
  const [error, setError] = createSignal("");
  const [isResolving, setIsResolving] = createSignal(false);
  const [isLoadingStreams, setIsLoadingStreams] = createSignal(false);
  let controller: AbortController | undefined;

  const sourceId = createMemo(() => resolution()?.sourceId || requestedSource());
  const animeId = createMemo(() => resolution()?.animeId || "");
  const episodeQuery = createQuery(() => ({
    queryKey: ["playback", "episodes", sourceId(), animeId()],
    queryFn: ({ signal }) => fetchEpisodes(sourceId(), animeId(), signal),
    enabled: Boolean(sourceId() && animeId()),
    staleTime: 1000 * 60 * 5,
  }));
  const episodes = () => episodeQuery.data ?? [];
  const currentEpisode = createMemo(() => {
    const target = selectedEpisodeId();
    return episodes().find((episode) => episode.id === target) || episodes().find((episode) => episode.number === requestedEpisode());
  });

  const resolve = async () => {
    const currentMedia = media();
    if (!currentMedia || isResolving()) return;
    controller?.abort();
    controller = new AbortController();
    setIsResolving(true);
    setError("");
    try {
      const result = await resolveAniListToSource(currentMedia, requestedSource() || undefined, controller.signal);
      setResolution(result);
      if (result.status === "not_found") setError("No playable source matched this title.");
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === "AbortError")) {
        setError(cause instanceof Error ? cause.message : "Unable to resolve a playback source.");
      }
    } finally {
      setIsResolving(false);
    }
  };

  createEffect(() => {
    if (media()) void resolve();
  });

  createEffect(() => {
    const list = episodes();
    if (!list.length || selectedEpisodeId()) return;
    const match = list.find((episode) => episode.number === requestedEpisode()) || list[0];
    if (match) setSelectedEpisodeId(match.id);
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

  createEffect(() => {
    const servers = serversQuery.data ?? [];
    if (servers.length && !selectedServerId()) void loadStreams(servers[0]);
  });

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

      <Show when={isResolving()}>
        <div class="inline-loading"><span class="spin" /> Finding a compatible AniSource entry…</div>
      </Show>
      <Show when={error()}><div class="inline-error">{error()}</div></Show>

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
                <h2 class="section-heading">Episodes</h2>
                <span class="muted">{episodes().length}</span>
              </div>
              <div class="episode-list">
                <For each={episodes()}>
                  {(episode) => (
                    <button class={`episode-item ${currentEpisode()?.id === episode.id ? "active" : ""}`} type="button" onClick={() => { setSelectedEpisodeId(episode.id); setSelectedServerId(""); setSelectedStream(null); }}>
                      <span>Episode {episode.number}</span>
                      <Show when={episode.is_filler}><small>Filler</small></Show>
                    </button>
                  )}
                </For>
              </div>
            </section>
          </aside>

          <main class="watch-main">
            <Show when={selectedStream()} fallback={<div class="player-placeholder">Select a server to begin playback.</div>}>
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
              <div class="watch-panel-heading"><h2 class="section-heading">Servers</h2><Show when={isLoadingStreams()}><span class="muted">Loading…</span></Show></div>
              <div class="server-list">
                <For each={serversQuery.data ?? []}>
                  {(server) => <button class={`server-chip ${selectedServerId() === server.id ? "active" : ""}`} type="button" onClick={() => void loadStreams(server)}>{server.name}</button>}
                </For>
              </div>
            </section>
          </main>
        </div>
      </Show>

      <Show when={!isResolving() && resolution()?.status === "not_found"}>
        <div class="empty-state">Try again later or choose another AniList title.</div>
      </Show>
    </div>
  );
}
