"use client";
import { useState } from "react";
import { Check, CircleCheck } from "lucide-react";
import { notifyActivity, progressApi } from "../lib/api";

/**
 * Marks a video/podcast lesson as watched for the signed-in teacher. The activity is stored
 * against their user id in the database, which is what feeds the streak and the calendar.
 */
export default function LessonComplete({
  activityType = "podcast",
  lessonId,
}: {
  activityType?: "video" | "podcast";
  lessonId?: number;
}) {
  const [state, setState] = useState<"idle" | "saving" | "done">("idle");
  const [error, setError] = useState("");

  const mark = async () => {
    setState("saving");
    setError("");
    try {
      await progressApi.logActivity(activityType, lessonId);
      notifyActivity();
      setState("done");
    } catch (e) {
      setError((e as Error).message);
      setState("idle");
    }
  };

  return (
    <article className="card lesson-complete">
      <p className="eyebrow">WHEN YOU&rsquo;VE FINISHED</p>
      <p>Marking this lesson complete records today as an active learning day.</p>
      {error && <p className="form-error">{error}</p>}
      {state === "done" ? (
        <p className="lesson-complete-done">
          <CircleCheck size={17} /> Completed — today is on your calendar.
        </p>
      ) : (
        <button className="outline-button" onClick={mark} disabled={state === "saving"}>
          <Check size={16} /> {state === "saving" ? "Saving…" : "Mark as complete"}
        </button>
      )}
    </article>
  );
}
