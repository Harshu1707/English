"use client";
import { useCallback, useEffect, useState } from "react";
import { ACTIVITY_EVENT, progressApi, type ProgressSummary } from "../lib/api";
import { useAuth } from "./AuthProvider";

/**
 * The signed-in teacher's learning statistics, always fetched from the backend for the
 * authenticated user. Nothing is read from localStorage, so the streak is identical after a
 * refresh, a new login or a restart of the app, and one teacher never sees another's data.
 */
export function useProgress() {
  const { user } = useAuth();
  const [summary, setSummary] = useState<ProgressSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    if (!user) {
      setSummary(null);
      setLoading(false);
      return;
    }
    progressApi
      .summary()
      .then((s) => {
        setSummary(s);
        setError("");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [user]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  // A finished recording or a completed lesson should move the streak straight away.
  useEffect(() => {
    const refresh = () => load();
    window.addEventListener(ACTIVITY_EVENT, refresh);
    window.addEventListener("verba:attempts-changed", refresh);
    return () => {
      window.removeEventListener(ACTIVITY_EVENT, refresh);
      window.removeEventListener("verba:attempts-changed", refresh);
    };
  }, [load]);

  return { summary, loading, error, reload: load };
}

/** Today's date, rendered in the reader's own locale and timezone (never hardcoded). */
export function todayLabel(now: Date = new Date()) {
  return now
    .toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })
    .toUpperCase();
}

export function greeting(now: Date = new Date()) {
  const hour = now.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}
