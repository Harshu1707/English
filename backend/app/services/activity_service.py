"""Learning activity, streaks and the activity calendar.

Everything here is derived from rows in `learning_activities` that belong to a single
authenticated user id, so one teacher can never see another teacher's progress and a
brand-new account naturally reads as zero. Nothing is cached in the browser: the streak
is recomputed from the database on every request, which is what makes it survive logout,
refresh and restarting the app.
"""
import calendar as _calendar
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import (
    ActivityType,
    LearningActivity,
    Lesson,
    SpeakingAttempt,
    SpeechFeedback,
    SpeechScore,
    UserLessonProgress,
    UserProgress,
)

logger = logging.getLogger("verba.activity")

try:  # stdlib on 3.9+; the tz database may still be missing on bare Windows installs
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - very old runtimes
    ZoneInfo = None  # type: ignore[assignment]


def app_timezone():
    """The timezone the application counts calendar days in (configurable via APP_TIMEZONE)."""
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo(settings.app_timezone)
    except Exception:  # unknown name, or no tzdata installed
        logger.warning("Unknown APP_TIMEZONE %r; falling back to UTC for day boundaries", settings.app_timezone)
        return None


def today_local() -> date:
    """Today's date in the application's local timezone (never hardcoded)."""
    tz = app_timezone()
    return datetime.now(tz).date() if tz else datetime.utcnow().date()


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------
def record_activity(
    db: Session,
    *,
    user_id: int,
    activity_type: ActivityType | str,
    lesson_id: int | None = None,
    attempt_id: int | None = None,
    when: date | None = None,
) -> LearningActivity | None:
    """Store one qualifying activity for this user. Best-effort: a logging failure must
    never break the video/podcast/practice action the user actually asked for."""
    value = activity_type.value if isinstance(activity_type, ActivityType) else str(activity_type)
    row = LearningActivity(
        user_id=user_id,
        activity_type=value,
        activity_date=when or today_local(),
        lesson_id=lesson_id,
        attempt_id=attempt_id,
    )
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not record %s activity for user %s", value, user_id)
        return None
    _sync_user_progress(db, user_id)
    return row


def _sync_user_progress(db: Session, user_id: int) -> None:
    """Keep the pre-existing user_progress row in step with the activity log."""
    try:
        current, _ = streaks(db, user_id)
        row = db.get(UserProgress, user_id)
        if row is None:
            row = UserProgress(user_id=user_id)
            db.add(row)
        row.current_streak = current
        row.lessons_completed = (
            db.query(func.count(UserLessonProgress.id))
            .filter(UserLessonProgress.user_id == user_id, UserLessonProgress.completed.is_(True))
            .scalar()
            or 0
        )
        row.speaking_seconds = int(
            db.query(func.coalesce(func.sum(SpeakingAttempt.duration_seconds), 0))
            .filter(SpeakingAttempt.user_id == user_id)
            .scalar()
            or 0
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not sync user_progress for user %s", user_id)


# ---------------------------------------------------------------------------
# Streaks
# ---------------------------------------------------------------------------
def active_dates(db: Session, user_id: int, *, start: date | None = None, end: date | None = None) -> list[date]:
    """Distinct days on which THIS user did at least one qualifying activity, ascending."""
    q = db.query(LearningActivity.activity_date).filter(LearningActivity.user_id == user_id)
    if start is not None:
        q = q.filter(LearningActivity.activity_date >= start)
    if end is not None:
        q = q.filter(LearningActivity.activity_date <= end)
    rows = q.distinct().all()
    out = []
    for (value,) in rows:
        if isinstance(value, datetime):
            value = value.date()
        out.append(value)
    return sorted(out)


def streaks(db: Session, user_id: int, *, today: date | None = None) -> tuple[int, int]:
    """(current streak, longest streak) in days.

    * no activity at all -> (0, 0)
    * several activities on one day -> that day counts once
    * a missed day ends the run; the next activity starts again at 1
    """
    today = today or today_local()
    days = active_dates(db, user_id)
    if not days:
        return 0, 0

    longest = run = 1
    for previous, current in zip(days, days[1:]):
        run = run + 1 if current - previous == timedelta(days=1) else 1
        longest = max(longest, run)

    last = days[-1]
    if last != today and last != today - timedelta(days=1):
        return 0, longest  # the run was broken; the next activity starts a new streak at 1

    current_streak = 1
    for previous, nxt in zip(reversed(days[:-1]), reversed(days[1:])):
        if nxt - previous == timedelta(days=1):
            current_streak += 1
        else:
            break
    return current_streak, max(longest, current_streak)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
def _type_counts(db: Session, user_id: int) -> dict[str, int]:
    rows = (
        db.query(LearningActivity.activity_type, func.count(LearningActivity.id))
        .filter(LearningActivity.user_id == user_id)
        .group_by(LearningActivity.activity_type)
        .all()
    )
    return {str(kind): int(count) for kind, count in rows}


def _average(values: list[float | None]) -> float | None:
    real = [v for v in values if v is not None]
    return round(sum(real) / len(real), 1) if real else None


def summary(db: Session, user_id: int) -> dict:
    """Every learning statistic shown in the UI, for this user only."""
    today = today_local()
    current, longest = streaks(db, user_id, today=today)
    counts = _type_counts(db, user_id)
    days = active_dates(db, user_id)

    total_lessons = db.query(func.count(Lesson.id)).filter(Lesson.published.is_(True)).scalar() or 0
    completed_lessons = (
        db.query(func.count(UserLessonProgress.id))
        .filter(UserLessonProgress.user_id == user_id, UserLessonProgress.completed.is_(True))
        .scalar()
        or 0
    )
    if total_lessons:
        progress_percent = min(100, round(completed_lessons / total_lessons * 100))
    else:
        # No published library yet: show effort actually recorded rather than a fake number.
        progress_percent = 0

    attempts = db.query(SpeakingAttempt).filter(SpeakingAttempt.user_id == user_id)
    attempt_count = attempts.with_entities(func.count(SpeakingAttempt.id)).scalar() or 0
    speaking_seconds = int(
        attempts.with_entities(func.coalesce(func.sum(SpeakingAttempt.duration_seconds), 0)).scalar() or 0
    )
    completed_attempts = (
        db.query(SpeakingAttempt)
        .filter(SpeakingAttempt.user_id == user_id, SpeakingAttempt.analysis_status == "completed")
        .order_by(SpeakingAttempt.created_at.desc(), SpeakingAttempt.id.desc())
        .limit(10)
        .all()
    )
    ids = [a.id for a in completed_attempts]
    scores = db.query(SpeechScore).filter(SpeechScore.attempt_id.in_(ids)).all() if ids else []
    feedback = db.query(SpeechFeedback).filter(SpeechFeedback.attempt_id.in_(ids)).all() if ids else []

    latest = completed_attempts[0].overall_score if completed_attempts else None
    return {
        "today": today,
        "current_streak": current,
        "longest_streak": longest,
        "active_days": len(days),
        "progress_percent": progress_percent,
        "completed_videos": counts.get(ActivityType.VIDEO.value, 0),
        "completed_podcasts": counts.get(ActivityType.PODCAST.value, 0),
        "practice_activities": counts.get(ActivityType.PRACTICE.value, 0),
        "lessons_completed": completed_lessons,
        "lessons_total": total_lessons,
        "speaking_attempts": attempt_count,
        "speaking_seconds": speaking_seconds,
        "overall_score": round(latest, 1) if latest is not None else None,
        "average_score": _average([a.overall_score for a in completed_attempts]),
        "signals": {
            "pronunciation": _average([s.pronunciation for s in scores]),
            "fluency": _average([s.fluency for s in scores]),
            "grammar": _average([f.grammar_score for f in feedback]),
            "vocabulary": _average([f.vocabulary_score for f in feedback]),
        },
    }


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------
def month_calendar(db: Session, user_id: int, year: int, month: int) -> dict:
    """Active days for one month. `calendar.monthrange` handles month lengths,
    leap years and year changes for us."""
    first = date(year, month, 1)
    last = date(year, month, _calendar.monthrange(year, month)[1])
    active = active_dates(db, user_id, start=first, end=last)
    return {
        "year": year,
        "month": month,
        "days_in_month": last.day,
        # Monday = 0 … Sunday = 6, matching the weekday header the UI renders.
        "first_weekday": first.weekday(),
        "today": today_local(),
        "active_days": sorted({d.day for d in active}),
    }
