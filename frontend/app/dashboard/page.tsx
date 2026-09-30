"use client";
import Link from "next/link";
import { ArrowRight, Flame, Play, Sparkles } from "lucide-react";
import SiteShell from "../../components/SiteShell";
import ScoreRing from "../../components/ScoreRing";
import ActivityCalendar from "../../components/ActivityCalendar";
import { FirstName } from "../../components/AuthProvider";
import { greeting, todayLabel, useProgress } from "../../components/ProgressProvider";

export default function Dashboard() {
  return (
    <SiteShell>
      <DashboardContent />
    </SiteShell>
  );
}

function DashboardContent() {
  const { summary } = useProgress();
  const streak = summary?.current_streak ?? 0;
  const progress = summary?.progress_percent ?? 0;
  const overall = summary?.overall_score ?? summary?.average_score ?? null;
  const signals = summary?.signals;
  const metrics: [string, number | null][] = [
    ["Pronunciation", signals?.pronunciation ?? null],
    ["Fluency", signals?.fluency ?? null],
    ["Grammar", signals?.grammar ?? null],
    ["Vocabulary", signals?.vocabulary ?? null],
  ];
  const started =
    (summary?.practice_activities ?? 0) + (summary?.completed_videos ?? 0) + (summary?.completed_podcasts ?? 0) > 0;

  return (
    <>
      <header className="page-header">
        <div>
          {/* Today's real date, in the reader's own locale and timezone. */}
          <p className="eyebrow">{todayLabel()}</p>
          <h1>
            {greeting()}, <FirstName />.
          </h1>
          <p>
            {started
              ? "You\u2019re building a clear, confident teaching voice."
              : "Your first lesson or recording starts your learning streak."}
          </p>
        </div>
        <div className="header-streak">
          <Flame size={20} />
          <b>{streak}</b>
          <span>day streak</span>
        </div>
      </header>

      <section className="continue">
        <div>
          <p className="eyebrow">CONTINUE LEARNING</p>
          <h2>Effective classroom communication</h2>
          <p>
            {summary
              ? `${summary.lessons_completed} of ${summary.lessons_total} lessons completed \u00b7 ${summary.practice_activities} practice ${summary.practice_activities === 1 ? "activity" : "activities"}`
              : "Loading your progress\u2026"}
          </p>
          <div className="bar">
            <i style={{ width: `${progress}%` }} />
          </div>
          <small>{progress}% complete</small>
        </div>
        <Link href="/lessons/classroom-communication" className="button">
          Continue <ArrowRight size={16} />
        </Link>
      </section>

      <section className="dash-grid">
        <article className="overall card">
          <p className="eyebrow">YOUR SPEAKING PROFILE</p>
          <ScoreRing score={overall ?? 0} label="Overall" />
          <div>
            <b>{overall === null ? "No recordings yet." : "Thoughtful progress."}</b>
            <p>
              {overall === null
                ? "Record your first practice piece and your speaking profile appears here."
                : `Based on your ${summary?.speaking_attempts} recorded ${summary?.speaking_attempts === 1 ? "attempt" : "attempts"}.`}
            </p>
            <Link href="/progress" className="text-link">
              View progress <ArrowRight size={14} />
            </Link>
          </div>
        </article>
        <article className="card metrics">
          <p className="eyebrow">CURRENT SIGNALS</p>
          {metrics.map(([name, score]) => (
            <div key={name}>
              <span>{name}</span>
              <div className="bar">
                <i style={{ width: `${score ?? 0}%` }} />
              </div>
              <b>{score === null ? "\u2014" : Math.round(score)}</b>
            </div>
          ))}
          <small>Scores come from your own recordings: provider signals plus AI language feedback.</small>
        </article>
      </section>

      <section className="dash-grid calendar-row">
        <ActivityCalendar title="YOUR LEARNING DAYS" />
        <article className="card metrics">
          <p className="eyebrow">THIS ACCOUNT</p>
          <div>
            <span>Videos</span>
            <div className="bar">
              <i style={{ width: `${Math.min(100, (summary?.completed_videos ?? 0) * 10)}%` }} />
            </div>
            <b>{summary?.completed_videos ?? 0}</b>
          </div>
          <div>
            <span>Podcasts</span>
            <div className="bar">
              <i style={{ width: `${Math.min(100, (summary?.completed_podcasts ?? 0) * 10)}%` }} />
            </div>
            <b>{summary?.completed_podcasts ?? 0}</b>
          </div>
          <div>
            <span>Practice</span>
            <div className="bar">
              <i style={{ width: `${Math.min(100, (summary?.practice_activities ?? 0) * 10)}%` }} />
            </div>
            <b>{summary?.practice_activities ?? 0}</b>
          </div>
          <small>
            Longest streak: {summary?.longest_streak ?? 0} {(summary?.longest_streak ?? 0) === 1 ? "day" : "days"}.
          </small>
        </article>
      </section>

      <section className="section-heading">
        <div>
          <p className="eyebrow">RECOMMENDED NEXT</p>
          <h2>Continue your practice</h2>
        </div>
        <Link href="/lessons" className="text-link">
          All lessons <ArrowRight size={15} />
        </Link>
      </section>
      <section className="lesson-row">
        {[
          ["Leading calm conversations", "Video \u00b7 Advanced", "18 min"],
          ["Explaining complex ideas", "Audio \u00b7 Intermediate", "10 min"],
          ["The language of feedback", "Podcast \u00b7 Beginner", "14 min"],
        ].map(([title, meta, time], i) => (
          <article className="lesson-card" key={title}>
            <div className={"lesson-image tone-" + i}>
              <Sparkles size={20} />
              <span>{time}</span>
            </div>
            <p>{meta}</p>
            <h3>{title}</h3>
            <Link className="inline-action" href="/lessons/classroom-communication">
              <Play size={15} />
              Start lesson
            </Link>
          </article>
        ))}
      </section>
    </>
  );
}
