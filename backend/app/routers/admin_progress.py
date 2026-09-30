"""Admin content-completion analytics API: which teachers finished which videos and podcasts.

Every number is computed from the existing tables on each request (users, lessons,
lesson_media, user_lesson_progress); nothing is cached or hardcoded. Authorization is applied
to the whole router, so every route here requires an authenticated ADMIN and a teacher gets a
403 even when calling the URL directly. Only id, name and email are ever read from `users`:
password hashes are never loaded.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.database.session import get_db
from app.models.models import Lesson, LessonMedia, Role, User, UserLessonProgress
from app.schemas.contracts import (
    ContentProgressDetail,
    ContentProgressItem,
    ContentProgressRecordPage,
    ContentProgressSummary,
    ContentProgressTeacher,
)
from app.services import content_progress as cp

router = APIRouter(
    prefix="/admin/content-progress",
    tags=["admin-content-progress"],
    dependencies=[Depends(require_admin)],
)

ContentKind = Literal["video", "podcast"]
CompletionFilter = Literal["completed", "not_completed"]


def _load_snapshot(db: Session) -> cp.Snapshot:
    """Read the plain rows the analytics need and hand them to the pure logic."""
    teachers = [
        cp.Teacher(id=user_id, name=name, email=email)
        for user_id, name, email in db.query(User.id, User.full_name, User.email).filter(User.role == Role.TEACHER).all()
    ]

    media_types: dict[int, list[str]] = {}
    for lesson_id, media_type in (
        db.query(LessonMedia.lesson_id, LessonMedia.media_type).filter(LessonMedia.media_type.in_(["video", "audio"])).all()
    ):
        media_types.setdefault(lesson_id, []).append(media_type)

    contents = []
    for lesson_id, title, lesson_type, published in db.query(
        Lesson.id, Lesson.title, Lesson.lesson_type, Lesson.published
    ).all():
        kind = cp.classify(lesson_type, media_types.get(lesson_id, ()))
        if kind is not None:
            contents.append(cp.Content(id=lesson_id, title=title, kind=kind, published=bool(published)))

    progress: dict[tuple[int, int], cp.Progress] = {}
    for user_id, lesson_id, percent, completed, completed_at, updated_at in db.query(
        UserLessonProgress.user_id,
        UserLessonProgress.lesson_id,
        UserLessonProgress.progress_percent,
        UserLessonProgress.completed,
        UserLessonProgress.completed_at,
        UserLessonProgress.updated_at,
    ).all():
        progress[(user_id, lesson_id)] = cp.Progress(
            percent=percent or 0,
            completed=bool(completed),
            completed_at=completed_at,
            touched_at=updated_at,
        )
    return cp.make_snapshot(teachers, contents, progress)


@router.get("/summary", response_model=ContentProgressSummary)
def get_summary(db: Session = Depends(get_db)):
    """Headline numbers: teachers, videos, podcasts, completions."""
    return cp.overview(_load_snapshot(db))


@router.get("/teachers", response_model=list[ContentProgressTeacher])
def get_teachers(
    search: str | None = Query(None, max_length=100, description="Match teacher name or email"),
    db: Session = Depends(get_db),
):
    """Every teacher with how many videos/podcasts they have completed and their last activity."""
    return cp.teacher_rows(_load_snapshot(db), search)


@router.get("/content", response_model=list[ContentProgressItem])
def get_content(
    content_type: ContentKind | None = Query(None),
    db: Session = Depends(get_db),
):
    """Every video/podcast lesson with how many teachers have and have not completed it."""
    return cp.content_rows(_load_snapshot(db), content_type)


@router.get("/content/{lesson_id}", response_model=ContentProgressDetail)
def get_content_detail(lesson_id: int, db: Session = Depends(get_db)):
    """One video/podcast: which teachers completed it (with when) and which have not."""
    detail = cp.content_detail(_load_snapshot(db), lesson_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video or podcast not found")
    return detail


@router.get("/records", response_model=ContentProgressRecordPage)
def get_records(
    content_type: ContentKind | None = Query(None),
    completion: CompletionFilter | None = Query(None, alias="status"),
    lesson_id: int | None = Query(None, ge=1),
    search: str | None = Query(None, max_length=100, description="Match teacher name or email"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """One row per teacher per video/podcast, filterable and paged."""
    rows = cp.record_rows(
        _load_snapshot(db),
        kind=content_type,
        status=completion,
        content_id=lesson_id,
        search=search,
    )
    return {"total": len(rows), "limit": limit, "offset": offset, "items": rows[offset : offset + limit]}
