import { A } from "@solidjs/router";
import { createQuery } from "@tanstack/solid-query";
import { Show } from "solid-js";
import { anilistRequest, HOME_QUERY } from "~/api/anilist";
import { AnimeRail } from "~/features/catalog/AnimeRail";
import { ContinueWatchingRail } from "~/features/catalog/ContinueWatchingRail";
import "./Home.css";

function getCurrentSeason() {
  const month = new Date().getMonth();
  if (month >= 0 && month <= 2) return "WINTER";
  if (month >= 3 && month <= 5) return "SPRING";
  if (month >= 6 && month <= 8) return "SUMMER";
  return "FALL";
}

export default function Home() {
  const now = Math.floor(Date.now() / 1000);
  const nextWeek = now + 7 * 24 * 60 * 60;
  const currentYear = new Date().getFullYear();
  const currentSeason = getCurrentSeason();

  const query = createQuery(() => ({
    queryKey: ["anime", "home"],
    queryFn: ({ signal }) =>
      anilistRequest<any>(
        HOME_QUERY,
        {
          season: currentSeason,
          seasonYear: currentYear,
          airingFrom: now,
          airingTo: nextWeek,
        },
        signal,
      ),
    staleTime: 1000 * 60 * 10, // 10 minutes
  }));

  const trendingMedias = () => query.data?.trending?.media ?? [];
  const seasonalMedias = () => query.data?.seasonal?.media ?? [];
  const topRatedMedias = () => query.data?.topRated?.media ?? [];
  const upcomingMedias = () => query.data?.upcoming?.media ?? [];
  const heroMedia = () => trendingMedias()[0];

  return (
    <div class="home-page">
      <Show when={heroMedia()}>
        {(media) => (
          <section class="hero-section">
            <div
              class="hero-backdrop"
              style={{
                "background-image": `url(${media().bannerImage || media().coverImage?.extraLarge})`,
              }}
            />
            <div class="hero-overlay" />
            <div class="hero-content page-shell">
              <div class="hero-badges">
                <span class="badge format-badge">{media().format?.replace(/_/g, " ")}</span>
                <span class="badge hero-trending-badge">#1 Trending</span>
              </div>
              <h1 class="hero-title display-title">
                {media().title.english || media().title.romaji || media().title.userPreferred}
              </h1>
              <div class="hero-meta">
                <Show when={media().seasonYear}><span>{media().seasonYear}</span></Show>
                <Show when={media().episodes}><span>{media().episodes} Episodes</span></Show>
                <Show when={media().averageScore}><span>{media().averageScore}% Score</span></Show>
              </div>
              <div class="hero-actions">
                <A href={`/anime/${media().id}`} class="btn primary-btn">
                  View Details
                </A>
              </div>
            </div>
          </section>
        )}
      </Show>

      <div class="page-shell rails-container">
        <ContinueWatchingRail />

        <Show when={query.isLoading}>
          <div class="loading-state">Loading catalog...</div>
        </Show>

        <Show when={trendingMedias().length > 0}>
           <AnimeRail title="Trending Now" items={trendingMedias()} />
        </Show>

        <Show when={seasonalMedias().length > 0}>
           <AnimeRail
             title="Popular this Season"
             subtitle={`${currentSeason} ${currentYear}`}
             items={seasonalMedias()}
           />
        </Show>

        <Show when={topRatedMedias().length > 0}>
           <AnimeRail title="Top Rated All Time" items={topRatedMedias()} />
        </Show>

        <Show when={upcomingMedias().length > 0}>
           <AnimeRail title="Highly Anticipated" items={upcomingMedias()} />
        </Show>
      </div>
    </div>
  );
}
