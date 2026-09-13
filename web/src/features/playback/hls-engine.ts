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
  const hls = new Hls({
    enableWorker: true,
    lowLatencyMode: false,
    backBufferLength: 120,
    maxBufferLength: 30,
    maxMaxBufferLength: 60,
    startFragPrefetch: true,
  });

  hls.on(Hls.Events.MANIFEST_PARSED, (_, data) => {
    if (options.onManifestParsed) {
      options.onManifestParsed(data.levels);
    }
  });

  let networkRecoveryUsed = false;
  let mediaRecoveryUsed = false;

  hls.on(Hls.Events.ERROR, (_, data) => {
    if (!data.fatal) {
      options.onError?.(data.type, data.details, false);
      return;
    }

    if (data.type === Hls.ErrorTypes.NETWORK_ERROR && !networkRecoveryUsed) {
      networkRecoveryUsed = true;
      hls.startLoad();
      options.onError?.(data.type, `${data.details}; retrying once`, false);
      return;
    }

    if (data.type === Hls.ErrorTypes.MEDIA_ERROR && !mediaRecoveryUsed) {
      mediaRecoveryUsed = true;
      hls.recoverMediaError();
      options.onError?.(data.type, `${data.details}; recovering once`, false);
      return;
    }

    options.onError?.(data.type, data.details, true);
    hls.destroy();
  });

  hls.loadSource(options.url);
  hls.attachMedia(options.video);

  return { destroy: () => hls.destroy() };
}
