"""Admin content-completion analytics: the pure logic.

Deliberately free of database, web and third-party imports. The routers load plain rows from
the existing tables (users, lessons, lesson_media, user_lesson_progress) into a `Snapshot`, and
everything the admin dashboard shows is derived from it here, so the rules are easy to read and
to test on their own.

Rules (nothing is invented):
* A "content item" is a lesson that is a video or a podcast/audio lesson. Lesson.lesson_type
  decides; if it is something else, the lesson's uploaded media decides (video media -> video,
  audio media -> podcast). Lessons that are neither are not part of this report.
* Only TEACHER accounts are counted. Admins are never listed as "not completed".
* A teacher has completed a content item only if their user_lesson_progress row says
  completed. No row at all means "not completed" - never a guessed history.
* completed_at is whatever the database recorded (None when it was never recorded).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

VIDEO = "video"
PODCAST = "podcast"
CONTENT_KINDS = (VIDEO, PODCAST)

COMPLETED = "completed"
NOT_COMPLETED = "not_completed"

_LESSON_TYPE_KIND = {"video": VIDEO, "podcast": PODCAST, "audio": PODCAST}
_MEDIA_TYPE_KIND = {"video": VIDEO, "audio": PODCAST}


def classify(lesson_type: str | None, media_types: Iterable[str | None] = ()) -> str | None:
    """'video', 'podcast', or None when the lesson is neither."""
    kind = _LESSON_TYPE_KIND.get((lesson_type or "").strip().lower())
    if kind:
        return kind
    kinds = {_MEDIA_TYPE_KIND[m] for m in ((x or "").strip().lower() for x in media_types) if m in _MEDIA_TYPE_KIND}
    if VIDEO in kinds:
        return VIDEO
    if PODCAST in kinds:
        return PODCAST
    return None


@dataclass(frozen=True)
class Teacher:
    id: int
    name: str
    email: str


@dataclass(frozen=True)
class Content:
    id: int
    title: str
    kind: str  # VIDEO | PODCAST
    published: bool


@dataclass(frozen=True)
class Progress:
    percent: int
    completed: bool
    completed_at: datetime | None
    touched_at: datetime | None  # the row's updated_at: the last time this teacher interacted


@dataclass
class Snapshot:
    teachers: list[Teacher] = field(default_factory=list)
    contents: list[Content] = field(default_factory=list)
    progress: dict[tuple[int, int], Progress] = field(default_factory=dict)  # (teacher_id, content_id)


def make_snapshot(
    teachers: Iterable[Teacher],
    contents: Iterable[Content],
    progress: dict[tuple[int, int], Progress],
) -> Snapshot:
    """Sort for stable output and drop progress rows that belong to non-teachers or to lessons
    that are not video/podcast content."""
    ordered_teachers = sorted(teachers, key=lambda t: (t.name.lower(), t.email.lower(), t.id))
    ordered_contents = sorted(contents, key=lambda c: (c.title.lower(), c.id))
    teacher_ids = {t.id for t in ordered_teachers}
    content_ids = {c.id for c in ordered_contents}
    kept = {key: p for key, p in progress.items() if key[0] in teacher_ids and key[1] in content_ids}
    return Snapshot(ordered_teachers, ordered_contents, kept)


def _needle(search: str | None) -> str | None:
    value = (search or "").strip().lower()
    return value or None


def _matches(teacher: Teacher, needle: str | None) -> bool:
    return needle is None or needle in teacher.name.lower() or needle in teacher.email.lower()


def _percent(p: Progress | None) -> int:
    if p is None:
        return 0
    if p.completed:
        return 100
    return max(0, min(100, int(p.percent or 0)))


# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------
def overview(snap: Snapshot) -> dict:
    total_teachers = len(snap.teachers)
    out: dict = {"total_teachers": total_teachers}
    for kind, plural in ((VIDEO, "videos"), (PODCAST, "podcasts")):
        ids = {c.id for c in snap.contents if c.kind == kind}
        done_pairs = 0
        teachers_done: set[int] = set()
        for (teacher_id, content_id), p in snap.progress.items():
            if content_id in ids and p.completed:
                done_pairs += 1
                teachers_done.add(teacher_id)
        out[f"total_{plural}"] = len(ids)
        out[f"{kind}_completions"] = done_pairs
        out[f"possible_{kind}_completions"] = len(ids) * total_teachers
        out[f"teachers_completed_{plural}"] = len(teachers_done)
    return out


# ---------------------------------------------------------------------------
# Teacher list
# ---------------------------------------------------------------------------
def teacher_rows(snap: Snapshot, search: str | None = None) -> list[dict]:
    kind_of = {c.id: c.kind for c in snap.contents}
    stats = {t.id: {"videos": 0, "podcasts": 0, "last": None} for t in snap.teachers}
    for (teacher_id, content_id), p in snap.progress.items():
        entry = stats[teacher_id]
        if p.completed:
            entry["videos" if kind_of[content_id] == VIDEO else "podcasts"] += 1
        when = p.completed_at or p.touched_at
        if when is not None and (entry["last"] is None or when > entry["last"]):
            entry["last"] = when
    needle = _needle(search)
    rows = [
        {
            "teacher_id": t.id,
            "name": t.name,
            "email": t.email,
            "videos_completed": stats[t.id]["videos"],
            "podcasts_completed": stats[t.id]["podcasts"],
            "total_completed": stats[t.id]["videos"] + stats[t.id]["podcasts"],
            "last_activity": stats[t.id]["last"],
        }
        for t in snap.teachers
        if _matches(t, needle)
    ]
    rows.sort(key=lambda r: -r["total_completed"])  # stable: ties stay in name order
    return rows


# ---------------------------------------------------------------------------
# Content list and content detail
# ---------------------------------------------------------------------------
def content_rows(snap: Snapshot, kind: str | None = None) -> list[dict]:
    done_by_content: dict[int, int] = {}
    for (_, content_id), p in snap.progress.items():
        if p.completed:
            done_by_content[content_id] = done_by_content.get(content_id, 0) + 1
    total = len(snap.teachers)
    rows = []
    for c in snap.contents:
        if kind and c.kind != kind:
            continue
        done = done_by_content.get(c.id, 0)
        rows.append(
            {
                "content_id": c.id,
                "title": c.title,
                "content_type": c.kind,
                "published": c.published,
                "completed_count": done,
                "not_completed_count": total - done,
                "total_teachers": total,
            }
        )
    return rows


def content_detail(snap: Snapshot, content_id: int) -> dict | None:
    content = next((c for c in snap.contents if c.id == content_id), None)
    if content is None:
        return None
    completed, not_completed = [], []
    for t in snap.teachers:
        p = snap.progress.get((t.id, content_id))
        person = {
            "teacher_id": t.id,
            "name": t.name,
            "email": t.email,
            "progress_percent": _percent(p),
            "completed_at": p.completed_at if p is not None and p.completed else None,
        }
        (completed if p is not None and p.completed else not_completed).append(person)
    # Most recent completion first; completions with no recorded time go last (name order kept).
    completed.sort(key=lambda r: r["completed_at"] or datetime.min, reverse=True)
    completed.sort(key=lambda r: r["completed_at"] is None)
    return {
        "content_id": content.id,
        "title": content.title,
        "content_type": content.kind,
        "published": content.published,
        "total_teachers": len(snap.teachers),
        "completed": completed,
        "not_completed": not_completed,
    }


# ---------------------------------------------------------------------------
# Flat teacher x content records (filterable table)
# ---------------------------------------------------------------------------
def record_rows(
    snap: Snapshot,
    *,
    kind: str | None = None,
    status: str | None = None,
    content_id: int | None = None,
    search: str | None = None,
) -> list[dict]:
    needle = _needle(search)
    teachers = [t for t in snap.teachers if _matches(t, needle)]
    rows: list[dict] = []
    for c in snap.contents:
        if kind and c.kind != kind:
            continue
        if content_id is not None and c.id != content_id:
            continue
        for t in teachers:
            p = snap.progress.get((t.id, c.id))
            done = p is not None and p.completed
            if status == COMPLETED and not done:
                continue
            if status == NOT_COMPLETED and done:
                continue
            rows.append(
                {
                    "teacher_id": t.id,
                    "teacher_name": t.name,
                    "teacher_email": t.email,
                    "content_id": c.id,
                    "content_title": c.title,
                    "content_type": c.kind,
                    "status": COMPLETED if done else NOT_COMPLETED,
                    "progress_percent": _percent(p),
                    "completed_at": p.completed_at if done else None,
                }
            )
    return rows
