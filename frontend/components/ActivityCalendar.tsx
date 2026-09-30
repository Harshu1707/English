"use client";
import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { ACTIVITY_EVENT, progressApi, type ActivityCalendar as CalendarData } from "../lib/api";

const WEEKDAYS = ["M", "T", "W", "T", "F", "S", "S"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/** Parse the API's YYYY-MM-DD without letting the browser shift it by a timezone. */
function parts(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  return { year: y, month: m, day: d };
}

/**
 * The signed-in teacher's active learning days for one month.
 *
 * A day is highlighted when that teacher completed at least one qualifying activity
 * (video, podcast or practice recording) on it; several activities on one day are still
 * one highlighted day. Month lengths, leap years and year changes come from the backend,
 * which derives them from the real calendar — no dates are hardcoded here.
 */
export default function ActivityCalendar({ title = "ACTIVITY CALENDAR" }: { title?: string }) {
  const [view, setView] = useState<{ year: number; month: number } | null>(null);
  const [data, setData] = useState<CalendarData | null>(null);
  const [error, setError] = useState("");

  const load = useCallback((target: { year: number; month: number } | null) => {
    progressApi
      .calendar(target?.year, target?.month)
      .then((res) => {
        setData(res);
        setError("");
        setView((current) => current ?? { year: res.year, month: res.month });
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    load(view);
  }, [load, view]);

  useEffect(() => {
    const refresh = () => load(view);
    window.addEventListener(ACTIVITY_EVENT, refresh);
    window.addEventListener("verba:attempts-changed", refresh);
    return () => {
      window.removeEventListener(ACTIVITY_EVENT, refresh);
      window.removeEventListener("verba:attempts-changed", refresh);
    };
  }, [load, view]);

  const shift = (step: number) => {
    const base = view ?? (data ? { year: data.year, month: data.month } : null);
    if (!base) return;
    const index = base.month - 1 + step; // handles December -> January and back
    setView({ year: base.year + Math.floor(index / 12), month: ((index % 12) + 12) % 12 + 1 });
  };

  if (error) {
    return (
      <article className="card calendar-card">
        <p className="eyebrow">{title}</p>
        <p className="muted">{error}</p>
      </article>
    );
  }
  if (!data) {
    return (
      <article className="card calendar-card">
        <p className="eyebrow">{title}</p>
        <p className="muted">Loading your activity…</p>
      </article>
    );
  }

  const today = parts(data.today);
  const active = new Set(data.active_days);
  const leading = Array.from({ length: data.first_weekday }, (_, i) => `blank-${i}`);
  const days = Array.from({ length: data.days_in_month }, (_, i) => i + 1);

  return (
    <article className="card calendar-card">
      <div className="calendar-head">
        <div>
          <p className="eyebrow">{title}</p>
          <h3>
            {MONTHS[data.month - 1]} {data.year}
          </h3>
        </div>
        <div className="calendar-nav">
          <button onClick={() => shift(-1)} aria-label="Previous month">
            <ChevronLeft size={16} />
          </button>
          <button onClick={() => shift(1)} aria-label="Next month">
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
      <div className="calendar-grid" role="grid" aria-label="Activity calendar">
        {WEEKDAYS.map((d, i) => (
          <span className="calendar-weekday" key={`${d}-${i}`} aria-hidden="true">
            {d}
          </span>
        ))}
        {leading.map((key) => (
          <span className="calendar-day empty" key={key} />
        ))}
        {days.map((day) => {
          const isToday = day === today.day && data.month === today.month && data.year === today.year;
          const isActive = active.has(day);
          const classes = ["calendar-day", isActive ? "active" : "", isToday ? "today" : ""].filter(Boolean).join(" ");
          const label = `${day} ${MONTHS[data.month - 1]} ${data.year}${isActive ? " — active learning day" : ""}`;
          return (
            <span className={classes} key={day} title={label} aria-label={label}>
              {day}
            </span>
          );
        })}
      </div>
      <div className="calendar-legend">
        <span>
          <i className="dot active" /> Active day
        </span>
        <span>
          <i className="dot today" /> Today
        </span>
        <small>
          {data.active_days.length} active {data.active_days.length === 1 ? "day" : "days"} this month
        </small>
      </div>
    </article>
  );
}
