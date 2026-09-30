"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { contentProgressApi, type ContentProgressSummary } from "../../lib/api";
import ContentProgressCards from "./ContentProgressCards";

/** The "Content completion" section of the existing admin dashboard: headline numbers + a link to the detail page. */
export default function ContentProgressOverview() {
  const [summary, setSummary] = useState<ContentProgressSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    contentProgressApi
      .summary()
      .then((data) => {
        if (!cancelled) setSummary(data);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Couldn't load content completion.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section style={{ marginTop: 25 }}>
      <div className="section-heading" style={{ marginTop: 0 }}>
        <div>
          <p className="eyebrow">CONTENT COMPLETION</p>
          <h2>Who has finished the videos and podcasts</h2>
        </div>
        <Link className="outline-button" href="/admin/content-progress">
          View teacher progress <ArrowRight size={16} />
        </Link>
      </div>
      {error && (
        <div className="analysis-error" role="alert">
          <b>Couldn&apos;t load content completion</b>
          <p>{error}</p>
        </div>
      )}
      <ContentProgressCards summary={summary} />
    </section>
  );
}
