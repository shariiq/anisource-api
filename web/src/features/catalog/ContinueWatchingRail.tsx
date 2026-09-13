import { A } from "@solidjs/router";
import { createSignal, For, onCleanup, onMount, Show } from "solid-js";
import {
  type PlaybackHistoryEntry,
  getAllHistory,
  removeHistoryEntry,
} from "~/features/library/history";
import "./ContinueWatchingRail.css";

export function ContinueWatchingRail() {
  const [history, setHistory] = createSignal<PlaybackHistoryEntry[]>([]);

  const load = () => {
    setHistory(getAllHistory());
  };

  onMount(() => {
    load();
    window.addEventListener("anisource_history_change", load);
  });

  onCleanup(() => {
    window.removeEventListener("anisource_history_change", load);
  });

  const handleRemove = (e: MouseEvent, anilistId: number) => {
    e.preventDefault();
    e.stopPropagation();
    removeHistoryEntry(anilistId);
    load();
  };

  return (
    <Show when={history().length > 0}>
      <section class="continue-watching-section">
        <div class="continue-header">
          <h2 class="continue-title">Continue Watching</h2>
          <span class="continue-count">{history().length} in progress</span>
        </div>
        <div class="continue-track">
          <For each={history()}>
            {(item) => (
              <div class="continue-card-wrap">
                <A
                  href={`/watch/${item.anilistId}?ep=${item.episodeNumber}&source=${item.sourceId}`}
                  class="continue-card"
                >
                  <div class="continue-poster-wrap">
                    <img
                      class="continue-poster"
                      src={item.poster}
                      alt={item.title}
                      loading="lazy"
                    />
                    <div class="continue-play-overlay">
                      <div class="play-circle">▶</div>
                    </div>
                    <div class="continue-progress-bar-bg">
                      <div
                        class="continue-progress-bar-fill"
                        style={{ width: `${item.progressPercent}%` }}
                      />
                    </div>
                  </div>
                  <div class="continue-info">
                    <div class="continue-ep-badge">EP {item.episodeNumber}</div>
                    <h3 class="continue-title-text" title={item.title}>
                      {item.title}
                    </h3>
                    <div class="continue-subtext">
                      {item.progressPercent}% completed
                    </div>
                  </div>
                </A>
                <button
                  class="continue-remove-btn"
                  onClick={(e) => handleRemove(e, item.anilistId)}
                  title="Remove from history"
                  aria-label="Remove from history"
                >
                  ×
                </button>
              </div>
            )}
          </For>
        </div>
      </section>
    </Show>
  );
}
