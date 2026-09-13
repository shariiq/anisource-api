import { createEffect, onCleanup, onMount } from "solid-js";
import type { StreamItem } from "~/api/anisource";
import { savePlaybackProgress } from "~/features/library/history";

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
  let latestPosition = props.initialPosition ?? 0;
  let latestDuration = 0;

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

  const handlePause = () => {
    handleTimeUpdate();
    persistProgress();
  };

  const handleVisibilityChange = () => {
    if (document.visibilityState === "hidden") {
      handleTimeUpdate();
      persistProgress();
    }
  };

  async function attachStream(stream: StreamItem) {
    clearMedia();
    latestPosition = props.initialPosition ?? 0;

    if (stream.is_hls && !video.canPlayType("application/vnd.apple.mpegurl")) {
      try {
        const module = await import("./hls-engine");
        if (!video.isConnected) return;
        if (!module.isHlsSupported()) {
          props.onError?.("This browser cannot play this HLS stream.");
          return;
        }
        hls = module.initializeHls({
          video,
          url: stream.url,
          onError: (_, details, fatal) => {
            if (fatal) props.onError?.(`Playback failed: ${details}`);
          },
        });
      } catch (error) {
        props.onError?.(error instanceof Error ? error.message : "Unable to load the HLS player.");
      }
    } else {
      video.src = stream.url;
      video.load();
    }

    video.currentTime = latestPosition;
    progressTimer = window.setInterval(() => {
      handleTimeUpdate();
      persistProgress();
    }, 3000);
  }

  onMount(() => {
    document.addEventListener("visibilitychange", handleVisibilityChange);
  });

  createEffect(() => {
    const stream = props.stream;
    if (stream && video) {
      void attachStream(stream);
    }
  });

  onCleanup(() => {
    document.removeEventListener("visibilitychange", handleVisibilityChange);
    handleTimeUpdate();
    persistProgress();
    clearMedia();
  });

  return (
    <video
      ref={video}
      controls
      playsinline
      preload="metadata"
      poster={props.poster}
      onTimeUpdate={handleTimeUpdate}
      onPause={handlePause}
      onEnded={() => {
        handleTimeUpdate();
        persistProgress();
        props.onEnded?.();
      }}
      onError={() => props.onError?.("The selected stream could not be played.")}
    >
      <track kind="captions" default />
      Your browser does not support the video element.
    </video>
  );
}
