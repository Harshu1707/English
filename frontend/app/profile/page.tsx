"use client";
import Link from "next/link";
import { ArrowRight, Flame, LogOut, Mail, Mic2, ShieldCheck, Trophy, UserRound, Video } from "lucide-react";
import SiteShell from "../../components/SiteShell";
import ActivityCalendar from "../../components/ActivityCalendar";
import { useAuth } from "../../components/AuthProvider";
import { useProgress } from "../../components/ProgressProvider";

function initials(name: string) {
  return name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("") || "?";
}

export default function ProfilePage() {
  return (
    <SiteShell>
      <ProfileContent />
    </SiteShell>
  );
}

function ProfileContent() {
  const { user, logout } = useAuth();
  const { summary, loading, error } = useProgress();
  if (!user) return null;

  const stats: [string, string][] = [
    ["Current streak", summary ? `${summary.current_streak} ${summary.current_streak === 1 ? "day" : "days"}` : "—"],
    ["Longest streak", summary ? `${summary.longest_streak} ${summary.longest_streak === 1 ? "day" : "days"}` : "—"],
    ["Progress", summary ? `${summary.progress_percent}%` : "—"],
    ["Completed videos", summary ? String(summary.completed_videos) : "—"],
    ["Completed podcasts", summary ? String(summary.completed_podcasts) : "—"],
    ["Practice activities", summary ? String(summary.practice_activities) : "—"],
    ["Active learning days", summary ? String(summary.active_days) : "—"],
    ["Speaking attempts", summary ? String(summary.speaking_attempts) : "—"],
  ];

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">YOUR PROFILE</p>
          <h1>{user.full_name}</h1>
          <p>Everything here comes from your own account activity.</p>
        </div>
        <button className="outline-button" onClick={logout}>
          <LogOut size={16} /> Sign out
        </button>
      </header>

      <section className="profile-layout">
        <article className="card profile-identity">
          <div className="profile-avatar">{initials(user.full_name)}</div>
          <p className="eyebrow">PERSONAL INFORMATION</p>
          <dl className="profile-details">
            <div>
              <dt>
                <UserRound size={14} /> Full name
              </dt>
              <dd>{user.full_name}</dd>
            </div>
            <div>
              <dt>
                <Mail size={14} /> Email
              </dt>
              <dd>{user.email}</dd>
            </div>
            <div>
              <dt>
                <ShieldCheck size={14} /> Role
              </dt>
              <dd>{user.role === "admin" ? "Admin" : "Teacher"}</dd>
            </div>
            <div>
              <dt>
                <Flame size={14} /> Account status
              </dt>
              <dd>Active</dd>
            </div>
          </dl>
        </article>

        <article className="card profile-stats">
          <p className="eyebrow">LEARNING STATISTICS</p>
          {error && <p className="form-error">{error}</p>}
          {loading && !summary ? (
            <p className="muted">Loading your statistics…</p>
          ) : (
            <dl className="profile-stat-grid">
              {stats.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          )}
          {summary && (
            <div className="profile-progress">
              <div className="bar">
                <i style={{ width: `${summary.progress_percent}%` }} />
              </div>
              <small>
                {summary.lessons_completed} of {summary.lessons_total} published lessons completed
              </small>
            </div>
          )}
        </article>
      </section>

      <section className="profile-secondary">
        <ActivityCalendar />
        <article className="card profile-links">
          <p className="eyebrow">KEEP GOING</p>
          <h3>
            {summary && summary.current_streak > 0
              ? `You're on a ${summary.current_streak}-day streak.`
              : "Start a streak today."}
          </h3>
          <p>One video, podcast or recording marks today as an active learning day.</p>
          <Link className="text-link" href="/practice">
            <Mic2 size={15} /> Record some practice <ArrowRight size={14} />
          </Link>
          <Link className="text-link" href="/lessons">
            <Video size={15} /> Browse lessons <ArrowRight size={14} />
          </Link>
          <Link className="text-link" href="/progress">
            <Trophy size={15} /> See your progress <ArrowRight size={14} />
          </Link>
        </article>
      </section>
    </>
  );
}
