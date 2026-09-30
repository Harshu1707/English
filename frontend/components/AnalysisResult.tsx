"use client";
import { Fragment } from "react";
import ScoreRing from "./ScoreRing";
import type { AttemptDetail, GrammarError, PronunciationIssue } from "../lib/api";

const CATEGORIES: { key: keyof AttemptDetail["scores"]; label: string }[] = [
  { key: "pronunciation", label: "Pronunciation" },
  { key: "fluency", label: "Fluency" },
  { key: "grammar", label: "Grammar" },
  { key: "vocabulary", label: "Vocabulary" },
  { key: "sentence_structure", label: "Sentence Structure" },
  { key: "pace", label: "Speaking Pace" },
];
const IDEAL_WPM = [120, 160];

function paceVerdict(wpm: number): string {
  if (wpm < IDEAL_WPM[0]) return "a little slow";
  if (wpm > IDEAL_WPM[1]) return "a little fast";
  return "comfortable";
}

type Mark = { start: number; end: number; kind: "grammar" | "pron"; note: string };
const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Find the first occurrence of each flagged phrase in the transcript; skip overlaps. */
export function findMarks(transcript: string, grammar: GrammarError[], pron: PronunciationIssue[]): Mark[] {
  const marks: Mark[] = [];
  for (const g of grammar) {
    if (!g.original.trim()) continue;
    const m = new RegExp(escapeRegExp(g.original.trim()), "i").exec(transcript);
    if (m) marks.push({ start: m.index, end: m.index + m[0].length, kind: "grammar", note: `Suggested: ${g.correction}` });
  }
  for (const p of pron) {
    if (!p.word.trim()) continue;
    const m = new RegExp(`\\b${escapeRegExp(p.word.trim())}\\b`, "i").exec(transcript);
    if (m) marks.push({ start: m.index, end: m.index + m[0].length, kind: "pron", note: p.note || "Pronunciation" });
  }
  marks.sort((a, b) => a.start - b.start);
  const clean: Mark[] = [];
  for (const m of marks) if (!clean.length || m.start >= clean[clean.length - 1].end) clean.push(m);
  return clean;
}

function Transcript({ attempt }: { attempt: AttemptDetail }) {
  const text = attempt.transcript ?? "";
  const marks = findMarks(text, attempt.grammar_errors, attempt.pronunciation_issues);
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  marks.forEach((m, i) => {
    if (m.start > cursor) parts.push(<Fragment key={`t${i}`}>{text.slice(cursor, m.start)}</Fragment>);
    parts.push(<mark key={`m${i}`} className={`mark-${m.kind}`} title={m.note}>{text.slice(m.start, m.end)}</mark>);
    cursor = m.end;
  });
  parts.push(<Fragment key="tail">{text.slice(cursor)}</Fragment>);
  return (
    <>
      <p className="transcript-text">{parts}</p>
      {marks.length > 0 && <p className="transcript-legend"><mark className="mark-grammar">Grammar</mark> <mark className="mark-pron">Pronunciation</mark> Hover a highlight for details.</p>}
    </>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return <div><b>{title}</b><ul>{items.map((x, i) => <li key={i}>{x}</li>)}</ul></div>;
}

export default function AnalysisResult({ attempt }: { attempt: AttemptDetail }) {
  const s = attempt.scores;
  const overall = s.overall == null ? null : Math.round(s.overall);
  return (
    <div className="analysis-result">
      <div className="result-head">
        {overall != null ? <ScoreRing score={overall} label="Overall" /> : null}
        <div>
          <p className="eyebrow">OVERALL SPEAKING SCORE</p>
          <h3>{overall != null ? `${overall} / 100` : "No score available"}</h3>
          {attempt.overall_feedback && <p>{attempt.overall_feedback}</p>}
          {attempt.words_per_minute != null && <p className="result-pace">Speaking pace: <b>{Math.round(attempt.words_per_minute)} words per minute</b> — {paceVerdict(attempt.words_per_minute)} (comfortable range {IDEAL_WPM[0]}–{IDEAL_WPM[1]}).</p>}
        </div>
      </div>

      <div className="score-rows">
        {CATEGORIES.map(({ key, label }) => {
          const v = s[key];
          return <div key={key} className="score-row"><span>{label}</span><div className="bar"><i style={{ width: `${v ?? 0}%` }} /></div><b>{v == null ? "—" : `${Math.round(v)}/100`}</b></div>;
        })}
      </div>

      <div className="feedback-columns">
        <div className="feedback-box"><p className="eyebrow">STRENGTHS</p>{attempt.strengths.length ? <ul>{attempt.strengths.map((x, i) => <li key={i}>{x}</li>)}</ul> : <p className="muted">Nothing highlighted this time.</p>}</div>
        <div className="feedback-box"><p className="eyebrow">AREAS TO IMPROVE</p>{attempt.areas_to_improve.length ? <ul>{attempt.areas_to_improve.map((x, i) => <li key={i}>{x}</li>)}</ul> : <p className="muted">Nothing highlighted this time.</p>}</div>
      </div>

      {attempt.grammar_errors.length > 0 && (
        <div className="feedback-box"><p className="eyebrow">GRAMMAR CORRECTIONS</p>
          {attempt.grammar_errors.map((g, i) => (
            <div key={i} className="correction"><small>You said</small><q>{g.original}</q><small>Suggested</small><q className="fix">{g.correction}</q>{(g.explanation || g.category) && <p className="muted">{[g.category, g.explanation].filter(Boolean).join(" — ")}</p>}</div>
          ))}
        </div>
      )}

      {(attempt.pronunciation_issues.length > 0 || attempt.filler_words.length > 0) && (
        <div className="feedback-columns">
          {attempt.pronunciation_issues.length > 0 && <div className="feedback-box"><p className="eyebrow">PRONUNCIATION NOTES</p><ul>{attempt.pronunciation_issues.map((p, i) => <li key={i}><b>{p.word}</b>{p.note ? ` — ${p.note}` : ""}</li>)}</ul></div>}
          {attempt.filler_words.length > 0 && <div className="feedback-box"><p className="eyebrow">FILLER WORDS</p><div className="chips">{attempt.filler_words.map((f) => <span key={f.word} className="chip">{f.word} × {f.count}</span>)}</div><p className="muted">Counts are approximate.</p></div>}
        </div>
      )}

      {(attempt.vocabulary_suggestions.length > 0 || attempt.repeated_words.length > 0 || attempt.sentence_structure_notes.length > 0) && (
        <div className="feedback-box"><p className="eyebrow">VOCABULARY & SENTENCE STRUCTURE</p>
          {attempt.vocabulary_suggestions.length > 0 && <ul>{attempt.vocabulary_suggestions.map((v, i) => <li key={i}><b>{v.word}</b> → {v.suggestion}{v.note ? ` (${v.note})` : ""}</li>)}</ul>}
          <List title="Repeated words" items={attempt.repeated_words} />
          <List title="Sentence structure" items={attempt.sentence_structure_notes} />
        </div>
      )}

      {(attempt.recommendations.length > 0 || attempt.practice_words.length > 0) && (
        <div className="feedback-box"><p className="eyebrow">NEXT STEPS</p><List title="" items={attempt.recommendations} />
          {attempt.practice_words.length > 0 && <div className="chips">{attempt.practice_words.map((w) => <span key={w} className="chip">{w}</span>)}</div>}</div>
      )}

      <div className="feedback-box"><p className="eyebrow">TRANSCRIPT</p><p className="muted">What the system heard:</p><Transcript attempt={attempt} />
        {attempt.audio_url && <audio controls preload="none" src={attempt.audio_url} className="result-audio" />}</div>

      {Object.keys(attempt.assessment).length > 0 && (
        <details className="assessment-note"><summary>How was this assessed?</summary><ul>{Object.entries(attempt.assessment).map(([k, v]) => <li key={k}>{v}</li>)}</ul></details>
      )}
    </div>
  );
}
