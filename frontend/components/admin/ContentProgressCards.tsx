import { CircleCheck, Headphones, UsersRound, Video } from "lucide-react";
import type { ContentProgressSummary } from "../../lib/api";

/**
 * Summary cards for admin content completion. Uses the same `card stat` markup as the rest of the
 * admin dashboard. `summary === null` means "still loading" and renders a placeholder.
 */
export default function ContentProgressCards({ summary }: { summary: ContentProgressSummary | null }) {
  const n = (value: number | undefined) => (summary && value !== undefined ? String(value) : "\u2026");
  const cards: { Icon: typeof Video; value: string; label: string; note?: string }[] = [
    { Icon: UsersRound, value: n(summary?.total_teachers), label: "Total teachers" },
    { Icon: Video, value: n(summary?.total_videos), label: "Videos" },
    { Icon: Headphones, value: n(summary?.total_podcasts), label: "Podcasts" },
    {
      Icon: CircleCheck,
      value: n(summary?.video_completions),
      label: "Video completions",
      note: summary ? `of ${summary.possible_video_completions} possible` : undefined,
    },
    {
      Icon: CircleCheck,
      value: n(summary?.podcast_completions),
      label: "Podcast completions",
      note: summary ? `of ${summary.possible_podcast_completions} possible` : undefined,
    },
    { Icon: UsersRound, value: n(summary?.teachers_completed_videos), label: "Teachers who completed videos" },
    { Icon: UsersRound, value: n(summary?.teachers_completed_podcasts), label: "Teachers who completed podcasts" },
  ];
  return (
    <section className="stat-grid" aria-label="Content completion summary">
      {cards.map(({ Icon, value, label, note }) => (
        <article className="card stat" key={label}>
          <Icon size={20} />
          <b>{value}</b>
          <span>{label}</span>
          {note && <small style={{ display: "block", marginTop: 2, fontSize: 11, color: "var(--muted)" }}>{note}</small>}
        </article>
      ))}
    </section>
  );
}
