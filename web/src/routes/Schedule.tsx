import { A } from "@solidjs/router";
import { createQuery } from "@tanstack/solid-query";
import { createMemo, createSignal, For, Show } from "solid-js";
import { type AniListAiring, type AniListPage, anilistRequest, AIRING_QUERY } from "~/api/anilist";
import "./Schedule.css";

interface DayTab {
  key: string;
  label: string;
  subLabel: string;
  startSec: number;
  endSec: number;
}

function getWeekDays(): DayTab[] {
  const days: DayTab[] = [];
  const now = new Date();
  const dayNames = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  for (let i = 0; i < 7; i++) {
    const d = new Date(now);
    d.setDate(now.getDate() + i);
    d.setHours(0, 0, 0, 0);

    const startSec = Math.floor(d.getTime() / 1000);
    const endSec = startSec + 86400 - 1;

    let label = dayNames[d.getDay()];
    if (i === 0) label = "Today";
    else if (i === 1) label = "Tomorrow";

    const subLabel = `${monthNames[d.getMonth()]} ${d.getDate()}`;
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;

    days.push({ key, label, subLabel, startSec, endSec });
  }

  return days;
}

export default function Schedule() {
  const weekDays = getWeekDays();
  const [selectedDayKey, setSelectedDayKey] = createSignal(weekDays[0].key);

  const selectedDay = () => weekDays.find((d) => d.key === selectedDayKey()) || weekDays[0];

  // Start & End for the whole 7-day range to fetch in one cached query
  const weekStart = weekDays[0].startSec;
  const weekEnd = weekDays[weekDays.length - 1].endSec;

  const query = createQuery(() => ({
    queryKey: ["anime", "schedule", weekStart, weekEnd],
    queryFn: ({ signal }) =>
      anilistRequest<{ Page: AniListPage<AniListAiring> }>(
        AIRING_QUERY,
        {
          from: weekStart,
          to: weekEnd,
          page: 1,
          perPage: 100,
        },
        signal,
      ),
    staleTime: 1000 * 60 * 5, // 5 minutes
  }));

  const allSchedules = () => query.data?.Page?.airingSchedules ?? [];

  const daySchedules = createMemo(() => {
    const current = selectedDay();
    return allSchedules()
      .filter((s) => s.airingAt >= current.startSec && s.airingAt <= current.endSec)
      .sort((a, b) => a.airingAt - b.airingAt);
  });

  const formatLocalTime = (airingAtSec: number) => {
    const date = new Date(airingAtSec * 1000);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  return (
    <div class="schedule-page page-shell">
      <div class="schedule-header">
        <h1 class="schedule-title display-title">Release Schedule</h1>
        <p class="schedule-subtitle muted">
          Weekly anime broadcasts synced to your local timezone ({Intl.DateTimeFormat().resolvedOptions().timeZone})
        </p>
      </div>

      {/* Day Selector Tabs */}
      <div class="day-tabs">
        <For each={weekDays}>
          {(day) => {
            const isSelected = () => selectedDayKey() === day.key;
            return (
              <button
                class={`day-tab ${isSelected() ? "active" : ""}`}
                onClick={() => setSelectedDayKey(day.key)}
              >
                <span class="day-tab-label">{day.label}</span>
                <span class="day-tab-sub">{day.subLabel}</span>
              </button>
            );
          }}
        </For>
      </div>

      {/* Schedule Items List */}
      <div class="schedule-content">
        <Show when={query.isLoading}>
          <div class="loading-state">Loading broadcast schedule…</div>
        </Show>

        <Show when={daySchedules().length > 0}>
          <div class="schedule-grid">
            <For each={daySchedules()}>
              {(item) => (
                <A href={`/anime/${item.media.id}`} class="schedule-card">
                  <div class="schedule-card-time">
                    <span class="time-badge">{formatLocalTime(item.airingAt)}</span>
                    <span class="ep-badge">EP {item.episode}</span>
                  </div>
                  <div class="schedule-poster-wrap">
                    <img
                      src={item.media.coverImage?.large}
                      alt={item.media.title?.english || item.media.title?.romaji || "Anime"}
                      class="schedule-poster"
                      loading="lazy"
                    />
                  </div>
                  <div class="schedule-info">
                    <h3 class="schedule-anime-title">
                      {item.media.title?.english ||
                        item.media.title?.romaji ||
                        item.media.title?.userPreferred}
                    </h3>
                    <div class="schedule-card-meta">
                      <span>{item.media.format?.replace(/_/g, " ")}</span>
                    </div>
                  </div>
                </A>
              )}
            </For>
          </div>
        </Show>

        <Show when={!query.isLoading && daySchedules().length === 0}>
          <div class="empty-state">No anime broadcasts scheduled for this day.</div>
        </Show>
      </div>
    </div>
  );
}
