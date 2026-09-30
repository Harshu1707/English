"use client";
import { useCallback, useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { ACTIVE_STATUSES, practiceApi, type AttemptDetail, type AttemptSummary } from "../lib/api";
import AnalysisResult from "./AnalysisResult";

const STATUS_LABEL: Record<string, string> = { pending: "Processing", processing: "Processing", transcribing: "Transcribing", analyzing: "Analysing", completed: "Completed", failed: "Failed" };
const formatDate = (iso: string) => new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

export default function PracticeHistory() {
  const [items, setItems] = useState<AttemptSummary[] | null>(null);
  const [error, setError] = useState("");
  const [openId, setOpenId] = useState<number | null>(null);
  const [detail, setDetail] = useState<AttemptDetail | null>(null);
  const [detailError, setDetailError] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await practiceApi.listAttempts(20, 0);
      setItems(res.items);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load your practice history.");
    }
  }, []);

  useEffect(() => {
    void load();
    const onChange = () => void load();
    window.addEventListener("verba:attempts-changed", onChange);
    return () => window.removeEventListener("verba:attempts-changed", onChange);
  }, [load]);

  // While something is still being analysed, keep the list fresh.
  const anyActive = items?.some((i) => ACTIVE_STATUSES.includes(i.status)) ?? false;
  useEffect(() => {
    if (!anyActive) return;
    const id = setInterval(() => void load(), 4000);
    return () => clearInterval(id);
  }, [anyActive, load]);

  async function toggle(item: AttemptSummary) {
    if (openId === item.id) { setOpenId(null); setDetail(null); return; }
    setOpenId(item.id); setDetail(null); setDetailError("");
    try { setDetail(await practiceApi.getAttempt(item.id)); }
    catch (e) { setDetailError(e instanceof Error ? e.message : "Couldn't load this attempt."); }
  }

  async function retry(id: number) {
    try { await practiceApi.retry(id); setOpenId(null); setDetail(null); await load(); }
    catch (e) { setDetailError(e instanceof Error ? e.message : "Couldn't restart the analysis."); }
  }

  return (
    <section className="card history" aria-labelledby="history-title">
      <p className="eyebrow">YOUR PRACTICE</p>
      <h2 id="history-title">Practice history</h2>
      {error && <p className="form-error" role="alert">{error}</p>}
      {items === null && !error && <p className="muted">Loading…</p>}
      {items?.length === 0 && <p className="muted">No practice attempts yet. Record your first response above and your results will appear here.</p>}
      <ul className="history-list">
        {items?.map((item) => {
          const open = openId === item.id;
          return (
            <li key={item.id}>
              <button className="history-row" onClick={() => void toggle(item)} aria-expanded={open}>
                <span className="history-title">Practice #{item.number ?? item.id}</span>
                <span className="history-date">{formatDate(item.created_at)}</span>
                <span className={`status-chip ${item.status}`}>{STATUS_LABEL[item.status] ?? item.status}</span>
                <b className="history-score">{item.overall_score != null ? `Score: ${Math.round(item.overall_score)}` : "—"}</b>
                <ChevronDown size={16} className={open ? "chevron open" : "chevron"} aria-hidden="true" />
              </button>
              {open && (
                <div className="history-detail">
                  {detailError && <p className="form-error" role="alert">{detailError}</p>}
                  {!detail && !detailError && <p className="muted">Loading…</p>}
                  {detail?.status === "completed" && <AnalysisResult attempt={detail} />}
                  {detail?.status === "failed" && <div className="analysis-error"><b>This recording couldn’t be analysed</b><p>{detail.error_message}</p><button className="secondary" onClick={() => void retry(detail.id)}>Retry analysis</button></div>}
                  {detail && ACTIVE_STATUSES.includes(detail.status) && <p className="muted">Still being analysed — this page will update automatically.</p>}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
