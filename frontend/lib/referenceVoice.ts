"use client";
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Reference Voice ("Listen to reference") support.
 *
 * The backend has no text-to-speech provider configured (only Groq
 * Whisper speech-to-TEXT for scoring attempts — see app/core/config.py).
 * Adding a new server-side TTS provider/API key would be a much larger,
 * unrelated change, so the smallest correct fix is to speak the exact
 * practice script client-side with the Web Speech API
 * (window.speechSynthesis), which every modern browser ships for free
 * and which supports real British English voices.
 *
 * This never falls back to an American voice: if the browser has no
 * en-GB voice installed, we surface a friendly error instead of
 * speaking in the wrong accent.
 */

export type ReferenceVoiceState = "idle" | "speaking" | "unsupported" | "error";

function isSpeechSupported() {
  return typeof window !== "undefined" && "speechSynthesis" in window && typeof window.SpeechSynthesisUtterance !== "undefined";
}

function pickBritishVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | undefined {
  const gb = voices.filter((v) => v.lang?.toLowerCase() === "en-gb");
  if (gb.length === 0) return undefined;
  // If several en-GB voices are installed, prefer one that's clearly labelled British/UK.
  return gb.find((v) => /uk|british|gb/i.test(v.name)) ?? gb[0];
}

export function useReferenceVoice(script: string) {
  const [state, setState] = useState<ReferenceVoiceState>(isSpeechSupported() ? "idle" : "unsupported");
  const [error, setError] = useState("");
  const voices = useRef<SpeechSynthesisVoice[]>([]);

  useEffect(() => {
    if (!isSpeechSupported()) return;
    const loadVoices = () => { voices.current = window.speechSynthesis.getVoices(); };
    loadVoices();
    window.speechSynthesis.addEventListener("voiceschanged", loadVoices);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", loadVoices);
  }, []);

  const speak = useCallback(() => {
    setError("");
    if (!isSpeechSupported()) {
      setState("unsupported");
      setError("Reference voice needs a browser with speech support, like Chrome or Edge.");
      return;
    }
    const available = voices.current.length ? voices.current : window.speechSynthesis.getVoices();
    const voice = pickBritishVoice(available);
    if (!voice) {
      // Never speak with an American (or other) voice as a silent substitute.
      setState("error");
      setError("No British English voice is installed in this browser, so the reference audio can't play. Try Chrome on desktop, which ships one by default.");
      return;
    }
    try {
      window.speechSynthesis.cancel(); // stop any previous playback so "replay" restarts cleanly
      const utterance = new SpeechSynthesisUtterance(script); // spoken exactly as written, unedited
      utterance.lang = "en-GB";
      utterance.voice = voice;
      utterance.rate = 0.95;
      utterance.onstart = () => setState("speaking");
      utterance.onend = () => setState("idle");
      utterance.onerror = () => {
        setState("error");
        setError("Couldn't play the reference voice. Please try again.");
      };
      window.speechSynthesis.speak(utterance);
    } catch {
      setState("error");
      setError("Couldn't play the reference voice. Please try again.");
    }
  }, [script]);

  const stop = useCallback(() => {
    if (isSpeechSupported()) window.speechSynthesis.cancel();
    setState("idle");
  }, []);

  return { state, error, speak, stop };
}
