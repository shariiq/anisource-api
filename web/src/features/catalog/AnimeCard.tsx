import { A } from "@solidjs/router";
import { useQueryClient } from "@tanstack/solid-query";
import type { AniListMedia } from "~/api/anilist";
import { cancelDetailPrefetch, scheduleDetailPrefetch } from "~/lib/intent-prefetch";
import "./AnimeCard.css";

export interface AnimeCardProps {
  media: AniListMedia;
  showScore?: boolean;
}

export function AnimeCard(props: AnimeCardProps) {
  const queryClient = useQueryClient();

  const title = () =>
    props.media.title.english ||
    props.media.title.userPreferred ||
    props.media.title.romaji ||
    "Unknown Title";

  const poster = () => props.media.coverImage?.extraLarge || props.media.coverImage?.large || "";
  const format = () => props.media.format?.replace(/_/g, " ") || "";
  const score = () => (props.media.averageScore ? `${props.media.averageScore}%` : null);

  const handlePointerEnter = () => {
    scheduleDetailPrefetch(queryClient, props.media.id);
  };

  const handlePointerLeave = () => {
    cancelDetailPrefetch(props.media.id);
  };

  const handleFocus = () => {
    scheduleDetailPrefetch(queryClient, props.media.id);
  };

  const handleBlur = () => {
    cancelDetailPrefetch(props.media.id);
  };

  return (
    <A
      href={`/anime/${props.media.id}`}
      class="anime-card"
      onPointerEnter={handlePointerEnter}
      onPointerLeave={handlePointerLeave}
      onFocus={handleFocus}
      onBlur={handleBlur}
    >
      <div class="card-poster-wrap">
        <img
          class="card-poster"
          src={poster()}
          alt={title()}
          loading="lazy"
          decoding="async"
        />
        <div class="card-badges">
          {format() && <span class="badge format-badge">{format()}</span>}
          {props.showScore !== false && score() && (
            <span class="badge score-badge">★ {score()}</span>
          )}
        </div>
      </div>
      <div class="card-info">
        <h3 class="card-title" title={title()}>
          {title()}
        </h3>
        <div class="card-meta">
          {props.media.seasonYear && <span>{props.media.seasonYear}</span>}
          {props.media.episodes && <span>{props.media.episodes} eps</span>}
        </div>
      </div>
    </A>
  );
}
