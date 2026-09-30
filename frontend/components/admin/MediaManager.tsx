"use client";
import { useState } from "react";
import { Trash2, Upload, RefreshCw } from "lucide-react";
import { mediaApi, type LessonMedia } from "../../lib/api";

const MEDIA_TYPES = ["video", "audio", "thumbnail"] as const;

export default function MediaManager() {
  const [lessonId, setLessonId] = useState("");
  const [mediaType, setMediaType] = useState<(typeof MEDIA_TYPES)[number]>("video");
  const [items, setItems] = useState<LessonMedia[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadMedia() {
    if (!lessonId) return;
    setError(null);
    try {
      setItems(await mediaApi.list(Number(lessonId)));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function handleUpload(file: File) {
    if (!lessonId) {
      setError("Enter a lesson ID first.");
      return;
    }
    setBusy(true);
    setError(null);
    setStatus("Uploading…");
    try {
      await mediaApi.upload(Number(lessonId), mediaType, file);
      setStatus("Upload complete.");
      await loadMedia();
    } catch (e) {
      setError((e as Error).message);
      setStatus(null);
    } finally {
      setBusy(false);
    }
  }

  async function handleReplace(media: LessonMedia, file: File) {
    setBusy(true);
    setError(null);
    setStatus("Replacing…");
    try {
      await mediaApi.replace(media.id, file);
      setStatus("Replaced.");
      await loadMedia();
    } catch (e) {
      setError((e as Error).message);
      setStatus(null);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(media: LessonMedia) {
    setBusy(true);
    setError(null);
    try {
      await mediaApi.remove(media.id);
      setStatus("Deleted.");
      setItems((prev) => prev.filter((m) => m.id !== media.id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card table-card">
      <p className="eyebrow">MEDIA</p>
      <h2>Lesson media</h2>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", margin: "12px 0" }}>
        <input
          type="number"
          placeholder="Lesson ID"
          value={lessonId}
          onChange={(e) => setLessonId(e.target.value)}
          style={{ width: 110, padding: "9px 12px", border: "1px solid var(--line)", borderRadius: 7 }}
        />
        <select
          value={mediaType}
          onChange={(e) => setMediaType(e.target.value as typeof mediaType)}
          style={{ padding: "9px 12px", border: "1px solid var(--line)", borderRadius: 7 }}
        >
          {MEDIA_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <button className="outline-button compact" onClick={loadMedia} disabled={busy}>
          <RefreshCw size={15} /> Load
        </button>
        <label className="button compact" style={{ cursor: "pointer" }}>
          <Upload size={15} /> Upload file
          <input
            type="file"
            hidden
            disabled={busy}
            onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
          />
        </label>
      </div>

      {status && <p style={{ fontSize: 13, color: "var(--olive2)" }}>{status}</p>}
      {error && <p style={{ fontSize: 13, color: "#a03c2e" }}>{error}</p>}

      {items.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Type</th>
              <th>File</th>
              <th>Format</th>
              <th>Size</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((m) => (
              <tr key={m.id}>
                <td>{m.media_type}</td>
                <td>
                  <a href={m.url} target="_blank" rel="noreferrer">
                    {m.original_filename || m.public_id || m.url}
                  </a>
                </td>
                <td>{m.format || "—"}</td>
                <td>{m.file_size ? `${Math.round(m.file_size / 1024)} KB` : "—"}</td>
                <td style={{ display: "flex", gap: 8 }}>
                  <label className="outline-button compact" style={{ cursor: "pointer" }}>
                    Replace
                    <input
                      type="file"
                      hidden
                      disabled={busy}
                      onChange={(e) => e.target.files?.[0] && handleReplace(m, e.target.files[0])}
                    />
                  </label>
                  <button className="outline-button compact" onClick={() => handleDelete(m)} disabled={busy}>
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
