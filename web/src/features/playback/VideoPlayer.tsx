import { createEffect, createSignal, For, onCleanup, onMount } from "solid-js";
import type { StreamItem } from "~/api/anisource";
import { savePlaybackProgress } from "~/features/library/history";

type PlayerState = "loading" | "ready" | "playing" | "buffering" | "paused" | "error";

export interface VideoPlayerProps {
  stream: StreamItem;
  anilistId: number;
  title: string;
  poster: string;
  sourceId: string;
  sourceAnimeId: string;
  episodeId: string;
  episodeNumber: number;
  serverId?: string;
  initialPosition?: number;
  onEnded?: () => void;
  onError?: (message: string) => void;
}

export function VideoPlayer(props: VideoPlayerProps) {
  let video!: HTMLVideoElement;
  let hls: { destroy: () => void } | undefined;
  let progressTimer: number | undefined;
  let generation = 0;
  let latestPosition = props.initialPosition ?? 0;
  let latestDuration = 0;
  const [state, setState] = createSignal<PlayerState>("loading");
  const [message, setMessage] = createSignal("Preparing stream…");
  const [selectedSubtitle, setSelectedSubtitle] = createSignal(-1);

  const persistProgress = () => {
    if (!latestDuration || latestPosition < 0) return;
    savePlaybackProgress({
      anilistId: props.anilistId,
      title: props.title,
      poster: props.poster,
      sourceId: props.sourceId,
      sourceAnimeId: props.sourceAnimeId,
      episodeId: props.episodeId,
      episodeNumber: props.episodeNumber,
      serverId: props.serverId,
      positionSeconds: latestPosition,
      durationSeconds: latestDuration,
    });
  };

  const clearMedia = () => {
    generation += 1;
    if (progressTimer !== undefined) {
      clearInterval(progressTimer);
      progressTimer = undefined;
    }
    hls?.destroy();
    hls = undefined;
    video?.pause();
    if (video) {
      video.removeAttribute("src");
      video.load();
    }
  };

  const handleTimeUpdate = () => {
    latestPosition = video.currentTime;
    latestDuration = Number.isFinite(video.duration) ? video.duration : 0;
  };

  const applySubtitle = (index: number) => {
    setSelectedSubtitle(index);
    Array.from(video.textTracks).forEach((track, trackIndex) => {
      track.mode = trackIndex === index ? "showing" : "disabled";
    });
  };

  const retryPlayback = () => {
    setState("loading");
    setMessage("Retrying stream…");
    void attachStream(props.stream);
  };

  async function attachStream(stream: StreamItem) {
    clearMedia();
    const currentGeneration = generation;
    latestPosition = props.initialPosition ?? 0;
    setSelectedSubtitle(-1);
    setState("loading");
    setMessage("Preparing stream…");

    const isCurrent = () => currentGeneration === generation && video.isConnected;
    const seekAfterMetadata = () => {
      if (isCurrent() && latestPosition > 0) video.currentTime = latestPosition;
    };

    video.addEventListener("loadedmetadata", seekAfterMetadata, { once: true });

    if (stream.is_hls && !video.canPlayType("application/vnd.apple.mpegurl")) {
      try {
        const module = await import("./hls-engine");
        if (!isCurrent()) return;
        if (!module.isHlsSupported()) {
          const error = "This browser cannot play this HLS stream.";
          setState("error");
          setMessage(error);
          props.onError?.(error);
          return;
        }
        hls = module.initializeHls({
          video,
          url: stream.url,
          onManifestParsed: () => {
            if (isCurrent()) {
              setState("ready");
              setMessage("Ready to play");
            }
          },
          onError: (_, details, fatal) => {
            if (!isCurrent()) return;
            if (fatal) {
              const error = `Playback failed: ${details}. Try another server or source.`;
              setState("error");
              setMessage(error);
              props.onError?.(error);
            } else if (details.includes("retrying") || details.includes("recovering")) {
              setState("buffering");
              setMessage("Reconnecting stream…");
            }
          },
        });
      } catch (error) {
        if (!isCurrent()) return;
        const message = error instanceof Error ? error.message : "Unable to load the HLS player.";
        setState("error");
        setMessage(message);
        props.onError?.(message);
      }
    } else {
      video.src = stream.url;
      video.load();
    }

    progressTimer = window.setInterval(() => {
      handleTimeUpdate();
      persistProgress();
    }, 3000);
  }

  onMount(() => {
    const persistOnHide = () => {
      if (document.visibilityState === "hidden") {
        handleTimeUpdate();
        persistProgress();
      }
    };
    document.addEventListener("visibilitychange", persistOnHide);
    onCleanup(() => document.removeEventListener("visibilitychange", persistOnHide));
  });

  createEffect(() => {
    const stream = props.stream;
    if (stream && video) void attachStream(stream);
  });

  onCleanup(() => {
    handleTimeUpdate();
    persistProgress();
    clearMedia();
  });

  return (
    <div class="video-player">
      <video
        ref={video}
        controls
        playsinline
        preload="auto"
        poster={props.poster}
        onCanPlay={() => {
          if (state() !== "playing") {
            setState("ready");
            setMessage("Ready to play");
          }
        }}
        onPlaying={() => {
          setState("playing");
          setMessage("Playing");
        }}
        onWaiting={() => {
          setState("buffering");
          setMessage("Buffering…");
        }}
        onPause={() => {
          handleTimeUpdate();
          persistProgress();
          if (!video.ended && state() !== "buffering") {
            setState("paused");
            setMessage("Paused");
          }
        }}
        onTimeUpdate={handleTimeUpdate}
        onEnded={() => {
          handleTimeUpdate();
          persistProgress();
          setState("ready");
          setMessage("Episode finished");
          props.onEnded?.();
        }}
        onError={() => {
          const error = "The selected stream could not be played. Try another server or source.";
          setState("error");
          setMessage(error);
          props.onError?.(error);
        }}
      >
        <For each={props.stream.subtitles}>
          {(subtitle) => (
            <track
              kind="subtitles"
              src={subtitle.url}
              srclang={subtitle.language.slice(0, 2).toLowerCase() || "und"}
              label={subtitle.label}
            />
          )}
        </For>
        Your browser does not support the video element.
      </video>

      <div class="player-toolbar">
        <span class={`player-status ${state()}`}>{message()}</span>
        <ShowSubtitleControls
          subtitles={props.stream.subtitles}
          selectedSubtitle={selectedSubtitle()}
          onSelect={applySubtitle}
        />
        <button class="player-retry" type="button" onClick={retryPlayback}>
          Retry stream
        </button>
      </div>
    </div>
  );
}

interface SubtitleControlsProps {
  subtitles: StreamItem["subtitles"];
  selectedSubtitle: number;
  onSelect: (index: number) => void;
}

function ShowSubtitleControls(props: SubtitleControlsProps) {
  if (!props.subtitles.length) return null;

  return (
    <label class="subtitle-select">
      <span>Subtitles</span>
      <select value={props.selectedSubtitle} onChange={(event) => props.onSelect(Number(event.currentTarget.value))}>
        <option value={-1}>Off</option>
        <For each={props.subtitles}>{(subtitle, index) => <option value={index()}>{subtitle.label}</option>}</For>
      </select>
    </label>
  );
}
