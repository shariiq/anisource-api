import type { QueryClient } from "@tanstack/solid-query";
import { getMediaById } from "~/api/anilist";

const timers = new Map<number, number>();

export function scheduleDetailPrefetch(
  queryClient: QueryClient,
  mediaId: number,
  delayMs = 120,
): void {
  cancelDetailPrefetch(mediaId);

  const timer = window.setTimeout(() => {
    timers.delete(mediaId);
    void queryClient.prefetchQuery({
      queryKey: ["anime", "detail", mediaId],
      queryFn: ({ signal }) => getMediaById(mediaId, signal),
      staleTime: 1000 * 60 * 15, // 15 minutes
    });
  }, delayMs);

  timers.set(mediaId, timer);
}

export function cancelDetailPrefetch(mediaId: number): void {
  const timer = timers.get(mediaId);
  if (timer !== undefined) {
    clearTimeout(timer);
    timers.delete(mediaId);
  }
}
