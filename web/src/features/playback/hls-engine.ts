import Hls from "hls.js";
import type { Level } from "hls.js";

interface InitHlsOptions {
  video: HTMLVideoElement;
  url: string;
  onManifestParsed?: (levels: Level[]) => void;
  onError?: (type: string, details: string, f: boolean) => void;
}

export function isHlsSupported(): boolean {
  return Hls.isSupported();
}

export function isNativeHlsSupported(video: HTMLVideoElement): boolean {
  return Boolean(video.canPlayType("application/vnd.apple.mpegurl"));
}

export function initializeHls(options: InitHlsOptions): Hls {
  const hls = new Hls({
    enableWorker: true,
    lowLatencyMode: true,
    backBufferLength: 90,
  });

  hls.loadSource(options.url);
  hls.attachMedia(options.video);

  hls.on(Hls.Events.MANIFEST_PARSED, (_, data) => {
    if (options.onManifestParsed) {
      options.onManifestParsed(data.levels);
    }
  });

  hls.on(Hls.Events.ERROR, (_, data) => {
    if (options.onError) {
      options.onError(data.type, data.details, data.fatal);
    }
    if (data.fatal) {
      switch (data.type) {
        case Hls.ErrorTypes.NETWORK_ERROR:
          hls.startLoad();
          break;
        case Hls.ErrorTypes.MEDIA_ERROR:
          hls.recoverMediaError();
          break;
        default:
          hls.destroy();
          break;
      }
    }
  });

  return hls;
}
