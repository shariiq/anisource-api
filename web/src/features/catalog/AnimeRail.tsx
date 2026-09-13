import { A } from "@solidjs/router";
import { For, Show } from "solid-js";
import type { AniListMedia } from "~/api/anilist";
import { AnimeCard } from "./AnimeCard";
import "./AnimeRail.css";

export interface AnimeRailProps {
  title: string;
  subtitle?: string;
  items: AniListMedia[];
  viewAllHref?: string;
}

export function AnimeRail(props: AnimeRailProps) {
  let scrollContainer: HTMLDivElement | undefined;

  const scrollLeft = () => {
    if (scrollContainer) {
      scrollContainer.scrollBy({ left: -scrollContainer.clientWidth * 0.75, behavior: "smooth" });
    }
  };

  const scrollRight = () => {
    if (scrollContainer) {
      scrollContainer.scrollBy({ left: scrollContainer.clientWidth * 0.75, behavior: "smooth" });
    }
  };

  return (
    <section class="anime-rail-section">
      <div class="rail-header">
        <div class="rail-title-group">
          <h2 class="rail-title">{props.title}</h2>
          <Show when={props.subtitle}>
            <span class="rail-subtitle">{props.subtitle}</span>
          </Show>
        </div>
        <div class="rail-controls">
          <Show when={props.viewAllHref}>
            <A href={props.viewAllHref!} class="rail-view-all">
              View All →
            </A>
          </Show>
          <div class="rail-arrows">
            <button
              class="rail-arrow"
              onClick={scrollLeft}
              aria-label="Scroll rail left"
            >
              ‹
            </button>
            <button
              class="rail-arrow"
              onClick={scrollRight}
              aria-label="Scroll rail right"
            >
              ›
            </button>
          </div>
        </div>
      </div>
      <div class="rail-track" ref={scrollContainer}>
        <For each={props.items}>
          {(media) => (
            <div class="rail-item">
              <AnimeCard media={media} />
            </div>
          )}
        </For>
      </div>
    </section>
  );
}
