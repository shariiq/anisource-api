import Hls from "hls.js";
import type { Level } from "hls.js";

interface InitHlsOptions {
  video: HTMLVideoElement;
  url: string;
  onManifestParsed?: (levels: Level[]) => void;
  onError?: (type: string, details: string, fatal: boolean) => void;
}

export interface HlsController {
  destroy: () => void;
}

export function isHlsSupported(): boolean {
  return Hls.isSupported();
}

export function isNativeHlsSupported(video: HTMLVideoElement): boolean {
  return Boolean(video.canPlayType("application/vnd.apple.mpegurl"));
}

export function initializeHls(options: InitHlsOptions): HlsController {
  // Keep this initialization deliberately aligned with the known-good standalone
  // player. Provider playlists can be sensitive to speculative fragment loading
  // and recovery attempts while the media element is still attaching.
  const hls = new Hls();

  hls.on(Hls.Events.MANIFEST_PARSED, (_, data) => {
    options.onManifestParsed?.(data.levels);
  });

  hls.on(Hls.Events.ERROR, (_, data) => {
    options.onError?.(data.type, data.details, data.fatal);
    if (data.fatal) hls.destroy();
  });

  hls.loadSource(options.url);
  hls.attachMedia(options.video);

  return { destroy: () => hls.destroy() };
}
