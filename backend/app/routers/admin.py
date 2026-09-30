"""Admin analytics API.

Every number here is computed from the existing database on each request — nothing is
hardcoded and nothing is cached. Every route requires an authenticated admin
(`require_admin`); a teacher gets a 403 even if they somehow reach the URL directly.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.database.session import get_db
from app.models.models import (
    ActivityType,
    LearningActivity,
    Lesson,
    LessonMedia,
    Role,
    SpeakingAttempt,
    User,
    UserLessonProgress,
    UserLogin,
)
from app.schemas.contracts import (
    AdminCompletionStats,
    AdminLoginStats,
    AdminMediaStats,
    AdminOverview,
    AdminUserStats,
    DailyLoginPoint,
    RecentActivityItem,
    TopMediaItem,
)
from app.services.activity_service import today_local

router = APIRouter(prefix="/admin/stats", tags=["admin-stats"])

LOGIN_HISTORY_DAYS = 14  # how many days of daily-login history to return
RECENT_ACTIVITY_LIMIT = 10
TOP_MEDIA_LIMIT = 5


# ---------------------------------------------------------------------------
# 1. User statistics
# ---------------------------------------------------------------------------
def _user_stats(db: Session) -> AdminUserStats:
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_teachers = db.query(func.count(User.id)).filter(User.role == Role.TEACHER).scalar() or 0
    total_admins = db.query(func.count(User.id)).filter(User.role == Role.ADMIN).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0
    inactive_users = db.query(func.count(User.id)).filter(User.is_active.is_(False)).scalar() or 0

    users_logged_in = db.query(func.count(func.distinct(UserLogin.user_id))).scalar() or 0
    users_never_logged_in = max(0, total_users - users_logged_in)

    now = datetime.utcnow()
    new_7 = db.query(func.count(User.id)).filter(User.created_at >= now - timedelta(days=7)).scalar() or 0
    new_30 = db.query(func.count(User.id)).filter(User.created_at >= now - timedelta(days=30)).scalar() or 0

    return AdminUserStats(
        total_users=total_users,
        total_teachers=total_teachers,
        total_admins=total_admins,
        active_users=active_users,
        inactive_users=inactive_users,
        users_logged_in=users_logged_in,
        users_never_logged_in=users_never_logged_in,
        new_users_last_7_days=new_7,
        new_users_last_30_days=new_30,
    )


# ---------------------------------------------------------------------------
# 2. Daily login statistics
# ---------------------------------------------------------------------------
def _login_stats(db: Session) -> AdminLoginStats:
    today = today_local()
    yesterday = today - timedelta(days=1)
    since_7 = today - timedelta(days=6)  # inclusive of today = 7 days
    since_30 = today - timedelta(days=29)
    since_history = today - timedelta(days=LOGIN_HISTORY_DAYS - 1)

    def count_since(start_date):
        return (
            db.query(func.count(UserLogin.id))
            .filter(UserLogin.login_date >= start_date, UserLogin.login_date <= today)
            .scalar()
            or 0
        )

    today_count = db.query(func.count(UserLogin.id)).filter(UserLogin.login_date == today).scalar() or 0
    yesterday_count = db.query(func.count(UserLogin.id)).filter(UserLogin.login_date == yesterday).scalar() or 0

    rows = (
        db.query(UserLogin.login_date, func.count(UserLogin.id))
        .filter(UserLogin.login_date >= since_history, UserLogin.login_date <= today)
        .group_by(UserLogin.login_date)
        .all()
    )
    counts_by_day = {d: c for d, c in rows}
    history = [
        DailyLoginPoint(date=since_history + timedelta(days=i), count=counts_by_day.get(since_history + timedelta(days=i), 0))
        for i in range(LOGIN_HISTORY_DAYS)
    ]

    return AdminLoginStats(
        today=today_count,
        yesterday=yesterday_count,
        last_7_days=count_since(since_7),
        last_30_days=count_since(since_30),
        daily_history=history,
    )


# ---------------------------------------------------------------------------
# 3. Learning completion statistics
# ---------------------------------------------------------------------------
def _completion_stats(db: Session) -> AdminCompletionStats:
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_published_lessons = db.query(func.count(Lesson.id)).filter(Lesson.published.is_(True)).scalar() or 0

    users_started = db.query(func.count(func.distinct(LearningActivity.user_id))).scalar() or 0

    users_completed_lesson = (
        db.query(func.count(func.distinct(UserLessonProgress.user_id)))
        .filter(UserLessonProgress.completed.is_(True))
        .scalar()
        or 0
    )
    lessons_completed_total = (
        db.query(func.count(UserLessonProgress.id)).filter(UserLessonProgress.completed.is_(True)).scalar() or 0
    )

    users_completed_practice = (
        db.query(func.count(func.distinct(SpeakingAttempt.user_id)))
        .filter(SpeakingAttempt.analysis_status == "completed")
        .scalar()
        or 0
    )
    practice_attempts_completed = (
        db.query(func.count(SpeakingAttempt.id)).filter(SpeakingAttempt.analysis_status == "completed").scalar() or 0
    )
    practice_attempts_total = db.query(func.count(SpeakingAttempt.id)).scalar() or 0

    completion_rate = None
    if total_users:
        completion_rate = round(users_completed_lesson / total_users * 100, 1)

    return AdminCompletionStats(
        users_started_learning=users_started,
        users_completed_a_lesson=users_completed_lesson,
        lessons_completed_total=lessons_completed_total,
        users_completed_practice=users_completed_practice,
        practice_attempts_completed=practice_attempts_completed,
        practice_attempts_total=practice_attempts_total,
        total_published_lessons=total_published_lessons,
        completion_rate_percent=completion_rate,
    )


# ---------------------------------------------------------------------------
# 4. Podcast / media statistics
# ---------------------------------------------------------------------------
def _media_stats(db: Session) -> AdminMediaStats:
    total_media = db.query(func.count(LessonMedia.id)).scalar() or 0
    total_videos = db.query(func.count(LessonMedia.id)).filter(LessonMedia.media_type == "video").scalar() or 0
    total_audio = db.query(func.count(LessonMedia.id)).filter(LessonMedia.media_type == "audio").scalar() or 0
    total_images = (
        db.query(func.count(LessonMedia.id))
        .filter(LessonMedia.media_type.in_(["image", "thumbnail"]))
        .scalar()
        or 0
    )
    lessons_with_media = db.query(func.count(func.distinct(LessonMedia.lesson_id))).scalar() or 0

    # "Accessed" media = a logged video/podcast learning activity (the only reliable,
    # already-tracked signal for media engagement in the existing schema).
    users_accessed = (
        db.query(func.count(func.distinct(LearningActivity.user_id)))
        .filter(LearningActivity.activity_type.in_([ActivityType.VIDEO.value, ActivityType.PODCAST.value]))
        .scalar()
        or 0
    )
    video_activity = (
        db.query(func.count(LearningActivity.id))
        .filter(LearningActivity.activity_type == ActivityType.VIDEO.value)
        .scalar()
        or 0
    )
    podcast_activity = (
        db.query(func.count(LearningActivity.id))
        .filter(LearningActivity.activity_type == ActivityType.PODCAST.value)
        .scalar()
        or 0
    )

    top_rows = (
        db.query(LearningActivity.lesson_id, LearningActivity.activity_type, func.count(LearningActivity.id).label("n"))
        .filter(
            LearningActivity.activity_type.in_([ActivityType.VIDEO.value, ActivityType.PODCAST.value]),
            LearningActivity.lesson_id.isnot(None),
        )
        .group_by(LearningActivity.lesson_id, LearningActivity.activity_type)
        .order_by(func.count(LearningActivity.id).desc())
        .limit(TOP_MEDIA_LIMIT)
        .all()
    )
    lesson_ids = [r[0] for r in top_rows]
    titles = {}
    if lesson_ids:
        titles = {lid: title for lid, title in db.query(Lesson.id, Lesson.title).filter(Lesson.id.in_(lesson_ids)).all()}
    most_used = [
        TopMediaItem(
            lesson_id=lesson_id,
            lesson_title=titles.get(lesson_id, f"Lesson #{lesson_id}"),
            media_type=activity_type,
            times_accessed=count,
        )
        for lesson_id, activity_type, count in top_rows
    ]

    return AdminMediaStats(
        total_media=total_media,
        total_videos=total_videos,
        total_audio=total_audio,
        total_images=total_images,
        lessons_with_media=lessons_with_media,
        users_who_accessed_media=users_accessed,
        video_activity_count=video_activity,
        podcast_activity_count=podcast_activity,
        most_used_media=most_used,
    )


# ---------------------------------------------------------------------------
# 5. Recent activity (real practice attempts, not sample data)
# ---------------------------------------------------------------------------
def _recent_activity(db: Session) -> list[RecentActivityItem]:
    rows = (
        db.query(SpeakingAttempt, User, Lesson)
        .join(User, SpeakingAttempt.user_id == User.id)
        .outerjoin(Lesson, SpeakingAttempt.lesson_id == Lesson.id)
        .order_by(SpeakingAttempt.created_at.desc(), SpeakingAttempt.id.desc())
        .limit(RECENT_ACTIVITY_LIMIT)
        .all()
    )
    return [
        RecentActivityItem(
            user_name=user.full_name,
            activity="Practice recording",
            detail=lesson.title if lesson else "Free practice",
            score=attempt.overall_score,
            created_at=attempt.created_at,
        )
        for attempt, user, lesson in rows
    ]


@router.get("/overview", response_model=AdminOverview)
def get_overview(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    """Every statistic on the admin dashboard, computed live from the database."""
    return AdminOverview(
        users=_user_stats(db),
        logins=_login_stats(db),
        completion=_completion_stats(db),
        media=_media_stats(db),
        recent_activity=_recent_activity(db),
    )
