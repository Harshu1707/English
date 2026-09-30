"""Per-user progress, streak and activity-calendar API.

Every route depends on get_current_user and filters on that user's id, so Teacher A's
progress, streak and calendar can never be returned for Teacher B.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.database.session import get_db
from app.models.models import ActivityType, Lesson, LessonMedia, User, UserLessonProgress
from app.schemas.contracts import (
    ActivityCalendar,
    ActivityRequest,
    LessonProgressOut,
    LessonProgressRequest,
    ProgressSummary,
)
from app.services import activity_service
from app.services import content_progress as content_kinds

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/summary", response_model=ProgressSummary)
def get_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Learning statistics for the signed-in user. A new account reads all zeros."""
    return ProgressSummary(**activity_service.summary(db, user.id))


@router.get("/calendar", response_model=ActivityCalendar)
def get_calendar(
    year: int | None = Query(None, ge=1970, le=2200),
    month: int | None = Query(None, ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Days in the requested month on which this user did at least one qualifying activity.
    Defaults to the current month in the application's timezone."""
    today = activity_service.today_local()
    return ActivityCalendar(**activity_service.month_calendar(db, user.id, year or today.year, month or today.month))


@router.post("/activity", response_model=ProgressSummary, status_code=status.HTTP_201_CREATED)
def log_activity(
    payload: ActivityRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Record a completed video or podcast (practice recordings are logged automatically
    when the attempt is created) and return the user's refreshed statistics."""
    if payload.activity_type == ActivityType.PRACTICE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Practice activity is recorded automatically when a recording is submitted.",
        )
    lesson_id = payload.lesson_id
    if lesson_id is not None:
        if db.get(Lesson, lesson_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
        _mark_lesson_complete(db, user.id, lesson_id)

    activity_service.record_activity(
        db,
        user_id=user.id,
        activity_type=payload.activity_type,
        lesson_id=lesson_id,
    )
    return ProgressSummary(**activity_service.summary(db, user.id))


def _mark_lesson_complete(db: Session, user_id: int, lesson_id: int) -> None:
    row = (
        db.query(UserLessonProgress)
        .filter(UserLessonProgress.user_id == user_id, UserLessonProgress.lesson_id == lesson_id)
        .first()
    )
    if row is None:
        row = UserLessonProgress(user_id=user_id, lesson_id=lesson_id)
        db.add(row)
    was_completed = bool(row.completed)
    row.progress_percent = 100
    row.completed = True
    # Stamp the FIRST completion only. A lesson completed before completed_at existed keeps
    # its (unknown) date rather than getting today's, so admin analytics never invent history.
    if not was_completed:
        row.completed_at = _utc_now()
    db.commit()


def _utc_now() -> datetime:
    """Naive UTC, the convention every timestamp column in this project uses."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_or_create_progress(db: Session, user_id: int, lesson_id: int) -> UserLessonProgress:
    """The single progress row for (teacher, lesson). The unique constraint means two racing
    requests can never create duplicates: the loser rolls back and reads the winner's row."""

    def find() -> UserLessonProgress | None:
        return (
            db.query(UserLessonProgress)
            .filter(UserLessonProgress.user_id == user_id, UserLessonProgress.lesson_id == lesson_id)
            .first()
        )

    row = find()
    if row is None:
        row = UserLessonProgress(user_id=user_id, lesson_id=lesson_id)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            row = find()
            if row is None:
                raise
    return row


@router.post("/lessons/{lesson_id}", response_model=LessonProgressOut)
def report_lesson_progress(
    lesson_id: int,
    payload: LessonProgressRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """A video/podcast player reports how far the signed-in teacher has got (0-100%).

    The lesson is marked completed - once, permanently, with the time - the first time the
    reported value reaches COMPLETION_THRESHOLD_PERCENT (default 90). Progress only moves
    forward, so a teacher who scrubs back or reopens a finished lesson is never un-completed,
    and repeated reports never create duplicate rows or duplicate activity.
    """
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    threshold = max(1, min(100, settings.completion_threshold_percent))
    row = _get_or_create_progress(db, user.id, lesson_id)

    newly_completed = False
    if not row.completed:
        row.progress_percent = max(row.progress_percent or 0, payload.percent)
        if payload.percent >= threshold:
            row.progress_percent = 100
            row.completed = True
            row.completed_at = _utc_now()
            newly_completed = True
    db.commit()
    db.refresh(row)

    if newly_completed:
        # Same effect as the "Mark as complete" button: today becomes an active learning day.
        media_types = [
            m for (m,) in db.query(LessonMedia.media_type).filter(LessonMedia.lesson_id == lesson_id).all()
        ]
        kind = content_kinds.classify(lesson.lesson_type, media_types)
        if kind is not None:
            activity_service.record_activity(
                db,
                user_id=user.id,
                activity_type=ActivityType.VIDEO if kind == content_kinds.VIDEO else ActivityType.PODCAST,
                lesson_id=lesson_id,
            )

    return LessonProgressOut(
        lesson_id=lesson_id,
        progress_percent=row.progress_percent,
        completed=bool(row.completed),
        completed_at=row.completed_at,
    )
