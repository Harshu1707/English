"use client";
import { ArrowUpRight, Clock3, Flame, Mic2, Trophy } from "lucide-react";
import SiteShell from "../../components/SiteShell";
import ScoreRing from "../../components/ScoreRing";
import ActivityCalendar from "../../components/ActivityCalendar";
import { useProgress } from "../../components/ProgressProvider";

function minutes(seconds: number) {
  if (!seconds) return "0 min";
  if (seconds < 60) return `${Math.round(seconds)} sec`;
  return `${Math.round(seconds / 60)} min`;
}

export default function Progress() {
  return (
    <SiteShell>
      <ProgressContent />
    </SiteShell>
  );
}

function ProgressContent() {
  const { summary, error } = useProgress();
  const overall = summary?.overall_score ?? summary?.average_score ?? null;
  const signals = summary?.signals;

  const stats: [typeof Trophy, string, string][] = [
    [Trophy, String(summary?.lessons_completed ?? 0), "Lessons completed"],
    [Mic2, String(summary?.speaking_attempts ?? 0), "Speaking attempts"],
    [Clock3, minutes(summary?.speaking_seconds ?? 0), "Speaking time"],
    [Flame, `${summary?.current_streak ?? 0}`, "Current streak (days)"],
  ];

  const profile: [string, number | null][] = [
    ["Pronunciation", signals?.pronunciation ?? null],
    ["Fluency", signals?.fluency ?? null],
    ["Grammar", signals?.grammar ?? null],
    ["Vocabulary", signals?.vocabulary ?? null],
  ];

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">YOUR PROGRESS</p>
          <h1>A steady, visible climb.</h1>
          <p>Progress is a record of your own practice&mdash;not a promise of fluency.</p>
        </div>
        <div className="header-streak">
          <Flame size={20} />
          <b>{summary?.current_streak ?? 0}</b>
          <span>day streak</span>
        </div>
      </header>

      {error && <p className="form-error">{error}</p>}

      <section className="stat-grid">
        {stats.map(([Icon, value, label]) => (
          <article className="card stat" key={label}>
            <Icon size={20} />
            <b>{value}</b>
            <span>{label}</span>
          </article>
        ))}
      </section>

      <section className="progress-layout">
        <ActivityCalendar />
        <article className="card profile">
          <p className="eyebrow">CURRENT PROFILE</p>
          <ScoreRing score={overall ?? 0} label="Overall" small />
          <div className="profile-list">
            {profile.map(([name, score]) => (
              <p key={name}>
                <span>{name}</span>
                <b>{score === null ? "\u2014" : Math.round(score)}</b>
              </p>
            ))}
          </div>
        </article>
      </section>

      <section className="progress-layout">
        <article className="card chart">
          <div>
            <p className="eyebrow">YOUR ACTIVITY</p>
            <h2>Where your days come from</h2>
          </div>
          <div className="chart-bars">
            {([
              ["Videos", summary?.completed_videos ?? 0],
              ["Podcasts", summary?.completed_podcasts ?? 0],
              ["Practice", summary?.practice_activities ?? 0],
              ["Active days", summary?.active_days ?? 0],
            ] as [string, number][]).map(([label, value], i, all) => {
              const max = Math.max(1, ...all.map(([, v]) => v));
              return (
                <div key={label}>
                  <i style={{ height: `${Math.max(3, (value / max) * 100)}%` }} />
                  <span>
                    {label} ({value})
                  </span>
                </div>
              );
            })}
          </div>
          <p>
            <b>{summary?.progress_percent ?? 0}% of the published library complete</b> &middot; longest streak{" "}
            {summary?.longest_streak ?? 0} {(summary?.longest_streak ?? 0) === 1 ? "day" : "days"}.
          </p>
        </article>
        <article className="card profile-links">
          <p className="eyebrow">ARROW OF TRAVEL</p>
          <h3>
            <ArrowUpRight size={18} />{" "}
            {overall === null ? "No score yet" : `${Math.round(overall)} overall`}
          </h3>
          <p>
            {summary && summary.speaking_attempts > 0
              ? `Averaged across your ${summary.speaking_attempts} recorded ${summary.speaking_attempts === 1 ? "attempt" : "attempts"}.`
              : "Record a practice piece to see your speaking profile."}
          </p>
        </article>
      </section>
    </>
  );
}
