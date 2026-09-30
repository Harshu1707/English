"use client";
import { Volume2 } from "lucide-react";
import { useReferenceVoice } from "../lib/referenceVoice";
import { getDailyWordFocus } from "../lib/wordFocus";

export default function WordFocus() {
  // Computed client-side (on every page load) rather than in the server
  // component, so the word can't get "frozen" by static page caching — it's
  // recalculated from today's date each time this renders, the same way
  // RecordingStudio already runs entirely client-side.
  const item = getDailyWordFocus();

  // Reuses the same British-English speech hook as the practice script's
  // Reference Voice button — just given the single focus word instead of
  // the full script. No separate/duplicate TTS implementation.
  const pronunciation = useReferenceVoice(item.word);

  return (
    <aside className="card word-card">
      <p className="eyebrow">WORD FOCUS</p>
      <h2>
        {item.word}{" "}
        <button
          type="button"
          className="icon-button word-listen-btn"
          onClick={pronunciation.speak}
          title="Listen to pronunciation"
          aria-label={pronunciation.state === "speaking" ? `Replaying pronunciation of ${item.word}` : `Listen to pronunciation of ${item.word}`}
        >
          <Volume2 size={16} />
        </button>
      </h2>
      <p className="phonetic">{item.phonetic}</p>
      {pronunciation.error && <p className="tts-note" role="alert">{pronunciation.error}</p>}
      <hr />
      <b>Helpful cue</b>
      <p>{item.cue}</p>
    </aside>
  );
}
