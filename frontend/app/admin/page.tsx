"use client";
import { useEffect, useState } from "react";
import { BookOpen, LogIn, Mic2, UsersRound } from "lucide-react";
import SiteShell from "../../components/SiteShell";
import MediaManager from "../../components/admin/MediaManager";
import ContentProgressOverview from "../../components/admin/ContentProgressOverview";
import { adminApi, type AdminOverview } from "../../lib/api";

function formatDate(iso: string) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { weekday: "short" });
}

export default function Admin() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    adminApi
      .overview()
      .then((data) => {
        if (!cancelled) setOverview(data);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Couldn't load admin statistics.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const users = overview?.users;
  const completion = overview?.completion;
  const media = overview?.media;
  const logins = overview?.logins;

  const topStats: [typeof UsersRound, string, string][] = [
    [UsersRound, users ? String(users.active_users) : "\u2014", "Active teachers"],
    [BookOpen, media ? String(media.total_media) : "\u2014", "Media items"],
    [Mic2, completion ? String(completion.practice_attempts_total) : "\u2014", "Speaking attempts"],
    [LogIn, logins ? String(logins.today) : "\u2014", "Logins today"],
  ];

  return (
    <SiteShell requireRole="admin">
      <header className="page-header">
        <div>
          <p className="eyebrow">ADMIN OVERVIEW</p>
          <h1>A clearer view of learning.</h1>
          <p>Monitor the library and teacher practice activity.</p>
        </div>
        <button className="button">Create lesson</button>
      </header>

      {error && (
        <div className="analysis-error" role="alert">
          <b>Couldn&apos;t load statistics</b>
          <p>{error}</p>
        </div>
      )}

      <section className="stat-grid">
        {topStats.map(([Icon, value, label]) => (
          <article className="card stat" key={label}>
            <Icon size={20} />
            <b>{overview ? value : "\u2026"}</b>
            <span>{label}</span>
          </article>
        ))}
      </section>

      <section className="dash-grid">
        <article className="card table-card">
          <p className="eyebrow">USER OVERVIEW</p>
          <h2>Who&apos;s on Verba</h2>
          <table>
            <tbody>
              <tr>
                <td>Total registered users</td>
                <td>{users?.total_users ?? "\u2014"}</td>
              </tr>
              <tr>
                <td>Teachers</td>
                <td>{users?.total_teachers ?? "\u2014"}</td>
              </tr>
              <tr>
                <td>Admins</td>
                <td>{users?.total_admins ?? "\u2014"}</td>
              </tr>
              <tr>
                <td>Active / inactive accounts</td>
                <td>{users ? `${users.active_users} / ${users.inactive_users}` : "\u2014"}</td>
              </tr>
              <tr>
                <td>Have logged in at least once</td>
                <td>{users?.users_logged_in ?? "\u2014"}</td>
              </tr>
              <tr>
                <td>Never logged in</td>
                <td>{users?.users_never_logged_in ?? "\u2014"}</td>
              </tr>
              <tr>
                <td>New users (last 7 / 30 days)</td>
                <td>{users ? `${users.new_users_last_7_days} / ${users.new_users_last_30_days}` : "\u2014"}</td>
              </tr>
            </tbody>
          </table>
        </article>

        <article className="card chart">
          <div>
            <p className="eyebrow">DAILY LOGIN ACTIVITY</p>
            <h2>Last 14 days</h2>
          </div>
          <div className="chart-bars">
            {(logins?.daily_history ?? []).map((point) => {
              const max = Math.max(1, ...(logins?.daily_history ?? []).map((p) => p.count));
              return (
                <div key={point.date}>
                  <i style={{ height: `${Math.max(3, (point.count / max) * 100)}%` }} />
                  <span>{formatDate(point.date)}</span>
                </div>
              );
            })}
          </div>
          <p>
            {logins
              ? `Today: ${logins.today} \u00b7 Yesterday: ${logins.yesterday} \u00b7 Last 7 days: ${logins.last_7_days} \u00b7 Last 30 days: ${logins.last_30_days}`
              : "Loading login history\u2026"}
          </p>
        </article>
      </section>

      <section className="dash-grid">
        <article className="card table-card">
          <p className="eyebrow">LEARNING COMPLETION</p>
          <h2>How far teachers are getting</h2>
          <table>
            <tbody>
              <tr>
                <td>Users who started learning</td>
                <td>{completion?.users_started_learning ?? "\u2014"}</td>
              </tr>
              <tr>
                <td>Users who completed a lesson</td>
                <td>{completion?.users_completed_a_lesson ?? "\u2014"}</td>
              </tr>
              <tr>
                <td>Lessons completed (total)</td>
                <td>{completion?.lessons_completed_total ?? "\u2014"}</td>
              </tr>
              <tr>
                <td>Users who completed practice</td>
                <td>{completion?.users_completed_practice ?? "\u2014"}</td>
              </tr>
              <tr>
                <td>Practice attempts completed / total</td>
                <td>
                  {completion
                    ? `${completion.practice_attempts_completed} / ${completion.practice_attempts_total}`
                    : "\u2014"}
                </td>
              </tr>
              <tr>
                <td>Published lessons</td>
                <td>{completion?.total_published_lessons ?? "\u2014"}</td>
              </tr>
              <tr>
                <td>Completion rate</td>
                <td>
                  {completion?.completion_rate_percent === null || completion?.completion_rate_percent === undefined
                    ? "\u2014"
                    : `${completion.completion_rate_percent}%`}
                </td>
              </tr>
            </tbody>
          </table>
        </article>

        <article className="card table-card">
          <p className="eyebrow">PODCAST / MEDIA USAGE</p>
          <h2>What&apos;s getting used</h2>
          <table>
            <tbody>
              <tr>
                <td>Total media (video / audio / image)</td>
                <td>{media ? `${media.total_videos} / ${media.total_audio} / ${media.total_images}` : "\u2014"}</td>
              </tr>
              <tr>
                <td>Lessons with media attached</td>
                <td>{media?.lessons_with_media ?? "\u2014"}</td>
              </tr>
              <tr>
                <td>Users who accessed video/podcast content</td>
                <td>{media?.users_who_accessed_media ?? "\u2014"}</td>
              </tr>
              <tr>
                <td>Video / podcast plays logged</td>
                <td>{media ? `${media.video_activity_count} / ${media.podcast_activity_count}` : "\u2014"}</td>
              </tr>
            </tbody>
          </table>
          {media && media.most_used_media.length > 0 && (
            <>
              <p className="eyebrow" style={{ marginTop: 18 }}>
                MOST USED
              </p>
              <table>
                <thead>
                  <tr>
                    <th>Lesson</th>
                    <th>Type</th>
                    <th>Times accessed</th>
                  </tr>
                </thead>
                <tbody>
                  {media.most_used_media.map((item) => (
                    <tr key={`${item.lesson_id}-${item.media_type}`}>
                      <td>{item.lesson_title}</td>
                      <td>{item.media_type}</td>
                      <td>{item.times_accessed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </article>
      </section>

      <ContentProgressOverview />

      <section className="card table-card">
        <p className="eyebrow">RECENT ACTIVITY</p>
        <h2>Teacher practice</h2>
        {overview && overview.recent_activity.length === 0 ? (
          <p>No practice activity yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Teacher</th>
                <th>Lesson</th>
                <th>Overall</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {(overview?.recent_activity ?? []).map((item, i) => (
                <tr key={i}>
                  <td>{item.user_name}</td>
                  <td>{item.detail}</td>
                  <td>{item.score === null ? "\u2014" : Math.round(item.score)}</td>
                  <td>{new Date(item.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <MediaManager />
    </SiteShell>
  );
}
