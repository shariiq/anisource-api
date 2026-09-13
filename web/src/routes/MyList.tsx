import { createQuery } from "@tanstack/solid-query";
import { createMemo, For, Show } from "solid-js";
import { type AniListMedia, type AniListPage, anilistRequest, BATCH_MEDIA_QUERY } from "~/api/anilist";
import { AnimeCard } from "~/features/catalog/AnimeCard";
import { myListSignal, removeFromMyList } from "~/features/library/my-list";
import "./MyList.css";

export default function MyList() {
  const records = myListSignal;
  const ids = createMemo(() => records().map((record) => record.anilistId));

  const query = createQuery(() => ({
    queryKey: ["anime", "my-list", ids()],
    queryFn: ({ signal }) =>
      anilistRequest<{ Page: AniListPage<AniListMedia> }>(
        BATCH_MEDIA_QUERY,
        { ids: ids() },
        signal,
      ),
    enabled: ids().length > 0,
    staleTime: 1000 * 60 * 30,
  }));

  const media = createMemo(() => {
    const byId = new Map((query.data?.Page.media ?? []).map((item) => [item.id, item]));
    return records()
      .map((record) => byId.get(record.anilistId))
      .filter((item): item is AniListMedia => Boolean(item));
  });

  return (
    <div class="my-list-page page-shell">
      <header class="my-list-header">
        <p class="eyebrow">Personal collection</p>
        <h1 class="my-list-title display-title">My List</h1>
        <p class="muted">Anime saved locally in this browser.</p>
      </header>

      <Show when={records().length > 0} fallback={<EmptyList />}>
        <Show when={query.isLoading && !query.data}>
          <div class="loading-state">Loading your saved anime…</div>
        </Show>

        <Show when={media().length > 0}>
          <div class="my-list-grid">
            <For each={media()}>
              {(item) => (
                <div class="my-list-card">
                  <AnimeCard media={item} />
                  <button
                    class="remove-list-item"
                    type="button"
                    aria-label={`Remove ${item.title.english || item.title.romaji} from My List`}
                    onClick={() => removeFromMyList(item.id)}
                  >
                    Remove
                  </button>
                </div>
              )}
            </For>
          </div>
        </Show>

        <Show when={!query.isLoading && media().length === 0}>
          <div class="empty-state">Saved titles could not be loaded right now. Try again shortly.</div>
        </Show>
      </Show>
    </div>
  );
}

function EmptyList() {
  return (
    <div class="my-list-empty">
      <span class="my-list-empty-mark">＋</span>
      <h2 class="section-heading">Your list is ready when you are.</h2>
      <p class="muted">Add a title from any anime detail page to keep it close at hand.</p>
    </div>
  );
}
