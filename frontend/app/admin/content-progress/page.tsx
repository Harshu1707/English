"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import SiteShell from "../../../components/SiteShell";
import ContentProgressCards from "../../../components/admin/ContentProgressCards";
import {
  contentProgressApi,
  type CompletionStatus,
  type ContentKind,
  type ContentProgressDetail,
  type ContentProgressItem,
  type ContentProgressRecordPage,
  type ContentProgressSummary,
  type ContentProgressTeacher,
} from "../../../lib/api";

const PAGE_SIZE = 25;
const NEVER = "\u2014";

// Same look as the inline-styled selects in the existing MediaManager.
const selectStyle = { padding: "9px 12px", border: "1px solid var(--line)", borderRadius: 7, background: "var(--off)", maxWidth: "100%" };

function formatWhen(iso: string | null): string {
  if (!iso) return NEVER;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return NEVER;
  return d.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
}

/** A completed item whose time was never recorded (completed before dates were tracked) says so honestly. */
function completedAt(iso: string | null): string {
  return iso ? formatWhen(iso) : "Date not recorded";
}

const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);

function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

function StatusChip({ done, percent }: { done: boolean; percent?: number }) {
  return (
    <span className={done ? "status-chip completed" : "status-chip"}>
      {done ? "Completed" : percent ? `Not Completed \u00b7 ${percent}%` : "Not Completed"}
    </span>
  );
}

function ErrorBox({ title, text }: { title: string; text: string }) {
  return (
    <div className="analysis-error" role="alert">
      <b>{title}</b>
      <p>{text}</p>
    </div>
  );
}

export default function ContentProgressPage() {
  return (
    <SiteShell requireRole="admin">
      <ContentProgressView />
    </SiteShell>
  );
}

function ContentProgressView() {
  // ---- summary + content list (loaded once) ----------------------------------------------
  const [summary, setSummary] = useState<ContentProgressSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [contents, setContents] = useState<ContentProgressItem[]>([]);

  useEffect(() => {
    let cancelled = false;
    contentProgressApi
      .summary()
      .then((d) => !cancelled && setSummary(d))
      .catch((e) => !cancelled && setSummaryError(message(e, "Couldn't load the summary.")));
    contentProgressApi
      .contents()
      .then((d) => !cancelled && setContents(d))
      .catch(() => undefined); // the filters still work without the lesson dropdown
    return () => {
      cancelled = true;
    };
  }, []);

  // ---- teacher table ---------------------------------------------------------------------
  const [teacherSearch, setTeacherSearch] = useState("");
  const debouncedTeacherSearch = useDebounced(teacherSearch);
  const [teachers, setTeachers] = useState<ContentProgressTeacher[] | null>(null);
  const [teachersError, setTeachersError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    contentProgressApi
      .teachers(debouncedTeacherSearch)
      .then((d) => {
        if (cancelled) return;
        setTeachers(d);
        setTeachersError(null);
      })
      .catch((e) => !cancelled && setTeachersError(message(e, "Couldn't load teachers.")));
    return () => {
      cancelled = true;
    };
  }, [debouncedTeacherSearch]);

  // ---- content progress: filters + records -----------------------------------------------
  const [kind, setKind] = useState<ContentKind | "">("");
  const [status, setStatus] = useState<CompletionStatus | "">("");
  const [lessonId, setLessonId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search);
  const [offset, setOffset] = useState(0);
  const [records, setRecords] = useState<ContentProgressRecordPage | null>(null);
  const [recordsError, setRecordsError] = useState<string | null>(null);
  const [recordsLoading, setRecordsLoading] = useState(true);

  const chooseKind = (next: ContentKind | "") => {
    setKind(next);
    setOffset(0);
    const chosen = contents.find((c) => c.content_id === lessonId);
    if (next && chosen && chosen.content_type !== next) setLessonId(null); // don't keep a lesson that no longer matches
  };
  const chooseStatus = (next: CompletionStatus | "") => {
    setStatus(next);
    setOffset(0);
  };
  const chooseLesson = (next: number | null) => {
    setLessonId(next);
    setOffset(0);
  };

  useEffect(() => {
    let cancelled = false;
    setRecordsLoading(true);
    contentProgressApi
      .records({ contentType: kind, status, lessonId: lessonId ?? "", search: debouncedSearch, limit: PAGE_SIZE, offset })
      .then((d) => {
        if (cancelled) return;
        setRecords(d);
        setRecordsError(null);
      })
      .catch((e) => !cancelled && setRecordsError(message(e, "Couldn't load progress.")))
      .finally(() => !cancelled && setRecordsLoading(false));
    return () => {
      cancelled = true;
    };
  }, [kind, status, lessonId, debouncedSearch, offset]);

  // ---- one video/podcast in detail ------------------------------------------------------
  const [detail, setDetail] = useState<ContentProgressDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    if (lessonId === null) {
      setDetail(null);
      setDetailError(null);
      return;
    }
    let cancelled = false;
    setDetail(null);
    contentProgressApi
      .content(lessonId)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        setDetailError(null);
      })
      .catch((e) => !cancelled && setDetailError(message(e, "Couldn't load this item.")));
    return () => {
      cancelled = true;
    };
  }, [lessonId]);

  const lessonOptions = contents.filter((c) => !kind || c.content_type === kind);
  const total = records?.total ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, total);

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">CONTENT PROGRESS</p>
          <h1>Who has finished what.</h1>
          <p>See which teachers have completed each video and podcast.</p>
        </div>
        <Link className="outline-button" href="/admin">
          Back to admin
        </Link>
      </header>

      {summaryError && <ErrorBox title="Couldn't load the summary" text={summaryError} />}
      <ContentProgressCards summary={summary} />

      {/* ---------------------------- Teacher progress ---------------------------- */}
      <section className="card table-card">
        <p className="eyebrow">TEACHER PROGRESS</p>
        <h2>Teachers</h2>
        <div className="library-controls">
          <label>
            <Search size={18} />
            <input
              value={teacherSearch}
              onChange={(e) => setTeacherSearch(e.target.value)}
              placeholder="Search teacher name or email"
              aria-label="Search teachers"
            />
          </label>
        </div>
        {teachersError && <ErrorBox title="Couldn't load teachers" text={teachersError} />}
        {teachers && teachers.length === 0 && !teachersError ? (
          <p>{debouncedTeacherSearch ? "No teachers match your search." : "No teachers have registered yet."}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>TEACHER</th>
                <th>EMAIL</th>
                <th style={{ textAlign: "right" }}>VIDEOS COMPLETED</th>
                <th style={{ textAlign: "right" }}>PODCASTS COMPLETED</th>
                <th style={{ textAlign: "right" }}>TOTAL COMPLETED</th>
                <th>LAST ACTIVITY</th>
              </tr>
            </thead>
            <tbody>
              {(teachers ?? []).map((t) => (
                <tr key={t.teacher_id}>
                  <td>{t.name}</td>
                  <td>{t.email}</td>
                  <td style={{ textAlign: "right" }}>{t.videos_completed}</td>
                  <td style={{ textAlign: "right" }}>{t.podcasts_completed}</td>
                  <td style={{ textAlign: "right" }}>
                    <b>{t.total_completed}</b>
                  </td>
                  <td>{formatWhen(t.last_activity)}</td>
                </tr>
              ))}
              {!teachers && !teachersError && (
                <tr>
                  <td colSpan={6}>Loading&hellip;</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </section>

      {/* ---------------------------- Content progress ---------------------------- */}
      <section className="card table-card">
        <p className="eyebrow">CONTENT PROGRESS</p>
        <h2>Video &amp; podcast completion</h2>

        <div className="library-controls">
          <label>
            <Search size={18} />
            <input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setOffset(0);
              }}
              placeholder="Search teacher name or email"
              aria-label="Search teachers in content progress"
            />
          </label>
          <div className="filters" role="group" aria-label="Content type">
            {(
              [
                ["", "All"],
                ["video", "Videos"],
                ["podcast", "Podcasts"],
              ] as [ContentKind | "", string][]
            ).map(([value, label]) => (
              <button
                key={label}
                type="button"
                className={kind === value ? "selected" : ""}
                aria-pressed={kind === value}
                onClick={() => chooseKind(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "0 0 20px" }}>
          <select
            aria-label="Filter by status"
            value={status}
            onChange={(e) => chooseStatus(e.target.value as CompletionStatus | "")}
            style={selectStyle}
          >
            <option value="">All statuses</option>
            <option value="completed">Completed</option>
            <option value="not_completed">Not completed</option>
          </select>
          <select
            aria-label="Filter by video or podcast"
            value={lessonId ?? ""}
            onChange={(e) => chooseLesson(e.target.value ? Number(e.target.value) : null)}
            style={selectStyle}
          >
            <option value="">All videos &amp; podcasts</option>
            {lessonOptions.map((c) => (
              <option key={c.content_id} value={c.content_id}>
                {c.title} ({c.content_type}
                {c.published ? "" : ", draft"}) &mdash; {c.completed_count}/{c.total_teachers} completed
              </option>
            ))}
          </select>
        </div>

        {recordsError && <ErrorBox title="Couldn't load progress" text={recordsError} />}

        {lessonId !== null && (
          <div style={{ marginBottom: 24 }}>
            {detailError && <ErrorBox title="Couldn't load this item" text={detailError} />}
            {detail && (
              <>
                <h3 style={{ margin: "0 0 4px" }}>
                  {detail.title} <small style={{ color: "var(--muted)", fontWeight: 400 }}>({detail.content_type})</small>
                </h3>
                <p style={{ margin: "0 0 14px", fontSize: 13, color: "var(--muted)" }}>
                  {detail.completed.length} of {detail.total_teachers} teachers have completed this {detail.content_type}.
                </p>
                <div className="dash-grid">
                  <PeopleList title={`Completed (${detail.completed.length})`} empty="Nobody has completed this yet." people={detail.completed} done />
                  <PeopleList
                    title={`Not completed (${detail.not_completed.length})`}
                    empty="Every teacher has completed this."
                    people={detail.not_completed}
                    done={false}
                  />
                </div>
              </>
            )}
            {!detail && !detailError && <p>Loading&hellip;</p>}
          </div>
        )}

        {records && records.items.length === 0 && !recordsError ? (
          <p>{recordsLoading ? "Loading\u2026" : "No records match these filters."}</p>
        ) : (
          <table className="cp-table" style={{ opacity: recordsLoading ? 0.6 : 1 }}>
            <thead>
              <tr>
                <th>TEACHER</th>
                <th>EMAIL</th>
                <th>VIDEO / PODCAST</th>
                <th>TYPE</th>
                <th>STATUS</th>
                <th>COMPLETED AT</th>
              </tr>
            </thead>
            <tbody>
              {(records?.items ?? []).map((r) => (
                <tr key={`${r.teacher_id}-${r.content_id}`}>
                  <td>{r.teacher_name}</td>
                  <td>{r.teacher_email}</td>
                  <td>{r.content_title}</td>
                  <td style={{ textTransform: "capitalize" }}>{r.content_type}</td>
                  <td>
                    <StatusChip done={r.status === "completed"} percent={r.progress_percent} />
                  </td>
                  <td>{r.status === "completed" ? completedAt(r.completed_at) : NEVER}</td>
                </tr>
              ))}
              {!records && !recordsError && (
                <tr>
                  <td colSpan={6}>Loading&hellip;</td>
                </tr>
              )}
            </tbody>
          </table>
        )}

        {records && total > 0 && (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginTop: 16, fontSize: 13, color: "var(--muted)" }}>
            <span>
              Showing {from}&ndash;{to} of {total}
            </span>
            <span style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="outline-button"
                style={{ minHeight: 36, padding: "6px 14px" }}
                disabled={offset === 0 || recordsLoading}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </button>
              <button
                type="button"
                className="outline-button"
                style={{ minHeight: 36, padding: "6px 14px" }}
                disabled={offset + PAGE_SIZE >= total || recordsLoading}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </button>
            </span>
          </div>
        )}
      </section>
    </>
  );
}

function PeopleList({
  title,
  empty,
  people,
  done,
}: {
  title: string;
  empty: string;
  people: ContentProgressDetail["completed"];
  done: boolean;
}) {
  return (
    <article className="card">
      <p className="eyebrow">{title.toUpperCase()}</p>
      {people.length === 0 ? (
        <p style={{ fontSize: 13, color: "var(--muted)", margin: 0 }}>{empty}</p>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {people.map((p) => (
            <li key={p.teacher_id} style={{ padding: "10px 0", borderBottom: "1px solid var(--line)", fontSize: 13 }}>
              <b>{p.name}</b>
              <div style={{ color: "var(--muted)", fontSize: 12, wordBreak: "break-word" }}>{p.email}</div>
              <div style={{ marginTop: 4, fontSize: 12 }}>
                {done ? completedAt(p.completed_at) : p.progress_percent > 0 ? `${p.progress_percent}% watched/listened` : "Not started"}
              </div>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
