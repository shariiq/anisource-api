const HISTORY_STORAGE_KEY = "anisource_continue_watching_v1";

export interface PlaybackHistoryEntry {
  anilistId: number;
  title: string;
  poster: string;
  episodeNumber: number;
  episodeId: string;
  sourceId: string;
  sourceAnimeId: string;
  serverId?: string;
  positionSeconds: number;
  durationSeconds: number;
  progressPercent: number;
  updatedAt: number;
}

function readStorage(): Record<string, PlaybackHistoryEntry> {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return {};
    return parsed;
  } catch {
    return {};
  }
}

function writeStorage(data: Record<string, PlaybackHistoryEntry>): void {
  try {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(data));
    window.dispatchEvent(new CustomEvent("anisource_history_change"));
  } catch {
    // Storage quota or disabled
  }
}

export function getAllHistory(): PlaybackHistoryEntry[] {
  const map = readStorage();
  return Object.values(map).sort((a, b) => b.updatedAt - a.updatedAt);
}

export function getHistoryForAnime(anilistId: number): PlaybackHistoryEntry | null {
  const map = readStorage();
  return map[String(anilistId)] ?? null;
}

export function savePlaybackProgress(entry: Omit<PlaybackHistoryEntry, "updatedAt" | "progressPercent">): void {
  if (!entry.anilistId || !entry.sourceId) return;

  const map = readStorage();
  const duration = entry.durationSeconds > 0 ? entry.durationSeconds : 1;
  const progressPercent = Math.min(100, Math.max(0, (entry.positionSeconds / duration) * 100));

  map[String(entry.anilistId)] = {
    ...entry,
    progressPercent: Number(progressPercent.toFixed(1)),
    updatedAt: Date.now(),
  };

  writeStorage(map);
}

export function removeHistoryEntry(anilistId: number): void {
  const map = readStorage();
  delete map[String(anilistId)];
  writeStorage(map);
}

export function clearAllHistory(): void {
  writeStorage({});
}
