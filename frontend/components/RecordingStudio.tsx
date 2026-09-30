"use client";
import { useEffect, useRef, useState } from "react";
import { Mic, RotateCcw, Square, Upload, Volume2 } from "lucide-react";
import { practiceApi, type AttemptDetail, type AttemptStatus } from "../lib/api";
import { useReferenceVoice } from "../lib/referenceVoice";
import AnalysisResult from "./AnalysisResult";

const REFERENCE = "Good morning everyone. Today we’re going to discuss effective classroom management.";
const MAX_UPLOAD_MB = 50;
const MIN_RECORDING_SECONDS = 2;

type Phase = "idle" | "recording" | "uploading" | Exclude<AttemptStatus, "pending">;
const BUSY: Phase[] = ["uploading", "processing", "transcribing", "analyzing"];
const STEPS: { key: Phase; label: string }[] = [
  { key: "uploading", label: "Uploading" },
  { key: "processing", label: "Processing" },
  { key: "transcribing", label: "Transcribing" },
  { key: "analyzing", label: "Analysing" },
  { key: "completed", label: "Completed" },
];
const HEADLINES: Partial<Record<Phase, string>> = {
  uploading: "Uploading your recording…",
  processing: "Processing your recording…",
  transcribing: "Transcribing what you said…",
  analyzing: "Analysing your speaking…",
};

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"].find((t) => MediaRecorder.isTypeSupported(t));
}
function extensionFor(type: string): string {
  if (type.includes("mp4")) return "mp4";
  if (type.includes("ogg")) return "ogg";
  return "webm";
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const notifyHistory = () => window.dispatchEvent(new Event("verba:attempts-changed"));

export default function RecordingStudio() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [seconds, setSeconds] = useState(0);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState<AttemptDetail | null>(null);
  const stream = useRef<MediaStream | undefined>(undefined);
  const recorder = useRef<MediaRecorder | undefined>(undefined);
  const chunks = useRef<Blob[]>([]);
  const startedAt = useRef(0);
  const poll = useRef({ cancelled: false });
  const fileInput = useRef<HTMLInputElement>(null);

  const recording = phase === "recording";
  const busy = BUSY.includes(phase);
  const referenceVoice = useReferenceVoice(REFERENCE);

  useEffect(() => {
    if (!recording) return;
    const id = setInterval(() => setSeconds((v) => v + 1), 1000);
    return () => clearInterval(id);
  }, [recording]);

  useEffect(() => () => {
    poll.current.cancelled = true;
    stream.current?.getTracks().forEach((t) => t.stop());
  }, []);

  function reset() {
    poll.current.cancelled = true;
    setPhase("idle"); setSeconds(0); setMessage(""); setError(""); setAttempt(null);
  }

  async function start() {
    reset();
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = pickMimeType();
      const rec = new MediaRecorder(stream.current, mimeType ? { mimeType } : undefined);
      chunks.current = [];
      rec.ondataavailable = (e) => { if (e.data.size > 0) chunks.current.push(e.data); };
      rec.onstop = () => {
        const type = rec.mimeType || mimeType || "audio/webm";
        void finishRecording(new Blob(chunks.current, { type }), (Date.now() - startedAt.current) / 1000);
      };
      recorder.current = rec;
      rec.start();
      startedAt.current = Date.now();
      setSeconds(0);
      setPhase("recording");
      setMessage("Your microphone is active. Speak naturally.");
    } catch {
      setMessage("Microphone access is needed to record. Please allow it in your browser settings.");
    }
  }

  function stop() {
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
    stream.current?.getTracks().forEach((t) => t.stop());
    setPhase("idle");
  }

  async function finishRecording(blob: Blob, elapsed: number) {
    if (blob.size === 0 || elapsed < MIN_RECORDING_SECONDS) {
      setMessage("That recording was too short. Try speaking for at least ten seconds.");
      return;
    }
    await submit(blob, `recording.${extensionFor(blob.type)}`, elapsed);
  }

  function onFilePicked(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    reset();
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) { setMessage(`That file is larger than ${MAX_UPLOAD_MB}MB. Please choose a shorter recording.`); return; }
    void submit(file, file.name);
  }

  async function submit(file: Blob, filename: string, durationSeconds?: number) {
    setPhase("uploading"); setMessage(""); setError(""); setAttempt(null);
    try {
      const created = await practiceApi.createAttempt(file, { filename, referenceText: REFERENCE, durationSeconds });
      notifyHistory();
      setPhase(created.status === "pending" ? "processing" : created.status);
      void track(created.id);
    } catch (e) {
      setPhase("idle");
      setError(e instanceof Error ? e.message : "Upload failed. Please try again.");
    }
  }

  async function track(id: number) {
    const token = { cancelled: false };
    poll.current = token;
    let failures = 0;
    while (!token.cancelled) {
      try {
        const detail = await practiceApi.getAttempt(id);
        if (token.cancelled) return;
        failures = 0;
        setPhase(detail.status === "pending" ? "processing" : detail.status);
        if (detail.status === "completed" || detail.status === "failed") {
          setAttempt(detail);
          if (detail.status === "failed") setError(detail.error_message || "We couldn't analyse that recording.");
          notifyHistory();
          return;
        }
      } catch {
        if (++failures >= 5) {
          setPhase("idle");
          setError("We lost contact with the server while analysing. Your recording is saved; check your practice history in a moment.");
          return;
        }
      }
      await sleep(2000);
    }
  }

  async function retry() {
    if (!attempt) return;
    setError("");
    try {
      await practiceApi.retry(attempt.id);
      setPhase("processing");
      notifyHistory();
      void track(attempt.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't restart the analysis.");
    }
  }

  const stepIndex = STEPS.findIndex((s) => s.key === phase);

  return <section className="studio"><div className="studio-top"><div><p className="eyebrow">SPEAKING PRACTICE</p><h2>Say it with confidence.</h2></div><button type="button" className="reference-voice-btn" onClick={referenceVoice.speak} aria-label={referenceVoice.state==="speaking"?"Replay reference voice (British English)":"Play reference voice (British English)"}><Volume2 size={18}/>{referenceVoice.state==="speaking"?"Playing…":"Reference Voice"}</button></div><blockquote>“{REFERENCE}”</blockquote>{referenceVoice.error && <p className="tts-note" role="alert">{referenceVoice.error}</p>}<div className={recording?"wave recording":"wave"} aria-label={recording?"Recording in progress":"Recording idle"}>{[...Array(13)].map((_,i)=><i key={i} style={{height:`${18+(i%5)*10}px`}}/>)}</div><div className="record-actions"><button className="secondary" onClick={reset} disabled={recording}><RotateCcw size={17}/>Try again</button>{recording?<button className="record stop" onClick={stop}><Square size={18}/>Stop · {String(Math.floor(seconds/60)).padStart(2,"0")}:{String(seconds%60).padStart(2,"0")}</button>:<button className="record" onClick={start} disabled={busy}><Mic size={19}/>Start recording</button>}<button className="secondary" onClick={()=>fileInput.current?.click()} disabled={busy||recording}><Upload size={17}/>Upload audio</button><input ref={fileInput} type="file" hidden accept="audio/*,.webm,.mp3,.wav,.m4a,.ogg,.mp4" onChange={onFilePicked}/></div>
    {busy && <div className="analysis-progress"><div className="analysis-status" role="status" aria-live="polite"><span className="spinner" aria-hidden="true"/><div><b>{HEADLINES[phase]}</b><small>This usually takes under a minute. You can keep this page open.</small></div></div><ol className="analysis-steps">{STEPS.map((s,i)=><li key={s.key} className={i<stepIndex?"done":i===stepIndex?"active":""}>{s.label}</li>)}</ol></div>}
    {error && <div className="analysis-error" role="alert"><b>{error === "Not matched. Please try again." ? "Not matched" : attempt ? "We couldn’t analyse that recording" : "Something went wrong"}</b><p>{error === "Not matched. Please try again." ? "Please try again." : error}</p><div className="record-actions">{attempt && error !== "Not matched. Please try again." && <button className="secondary" onClick={retry}>Retry analysis</button>}<button className="secondary" onClick={reset}>Record again</button></div></div>}
    {message&&<p className="studio-message" role="status">{message}</p>}
    {phase==="completed"&&attempt&&<AnalysisResult attempt={attempt}/>}
  </section>}
