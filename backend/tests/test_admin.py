"""Admin activity analytics: security (role checks) and data accuracy.

Every number in /admin/stats/overview is computed live from real rows written through
the normal application flow (or, where that would require the full Cloudinary/Groq
pipeline, written directly with the same ORM models the app itself uses) — never from
mocked or hardcoded statistics.
"""
from datetime import datetime, timedelta

from app.database.session import SessionLocal
from app.models.models import (
    ActivityType,
    Lesson,
    LessonMedia,
    SpeakingAttempt,
    UserLogin,
)
from app.services import activity_service
from tests.conftest import PASSWORD, auth_headers, register


def _user_id(client, headers) -> int:
    return client.get("/auth/me", headers=headers).json()["id"]


def _admin(client, email="admin@example.com"):
    return auth_headers(client, email, role="admin", admin_invite_code="let-me-in-123")


# ---------------------------------------------------------------------------
# Security: only admins may reach admin analytics
# ---------------------------------------------------------------------------
def test_overview_requires_authentication(client):
    assert client.get("/admin/stats/overview").status_code == 401


def test_teacher_cannot_access_admin_analytics(client):
    teacher = auth_headers(client, "t@example.com")
    res = client.get("/admin/stats/overview", headers=teacher)
    assert res.status_code == 403


def test_admin_can_access_admin_analytics(client):
    admin = _admin(client)
    res = client.get("/admin/stats/overview", headers=admin)
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"users", "logins", "completion", "media", "recent_activity"}


def test_overview_never_exposes_password_fields(client):
    admin = _admin(client)
    res = client.get("/admin/stats/overview", headers=admin)
    assert "password" not in res.text and "password_hash" not in res.text


# ---------------------------------------------------------------------------
# 1. Registered / active user counts
# ---------------------------------------------------------------------------
def test_user_counts_are_accurate(client):
    register(client, "t1@example.com")
    register(client, "t2@example.com")
    admin = _admin(client)  # the admin itself is also a registered user

    stats = client.get("/admin/stats/overview", headers=admin).json()["users"]
    assert stats["total_users"] == 3
    assert stats["total_teachers"] == 2
    assert stats["total_admins"] == 1
    assert stats["active_users"] == 3
    assert stats["inactive_users"] == 0


# ---------------------------------------------------------------------------
# 2. Login activity — must reflect real logins, not just registrations
#
# `auth_headers` (and therefore `_admin`) only calls POST /auth/register, which returns
# its own access token and deliberately does NOT write a UserLogin row (see auth.py) —
# so admins/teachers created that way stay "never logged in" until they actually hit
# POST /auth/login, exactly like a real user would.
# ---------------------------------------------------------------------------
def test_registering_does_not_count_as_a_login(client):
    register(client, "never-logged-in@example.com")
    admin = _admin(client)  # registered, but never logged in via /auth/login

    stats = client.get("/admin/stats/overview", headers=admin).json()["users"]
    assert stats["users_logged_in"] == 0
    assert stats["users_never_logged_in"] == 2


def test_login_is_recorded_and_reflected_today(client):
    register(client, "logger@example.com")
    login = client.post("/auth/login", json={"email": "logger@example.com", "password": PASSWORD})
    assert login.status_code == 200
    admin = _admin(client)

    body = client.get("/admin/stats/overview", headers=admin).json()
    assert body["users"]["users_logged_in"] == 1  # only logger@ actually logged in
    assert body["users"]["users_never_logged_in"] == 1  # the admin itself never called /auth/login
    assert body["logins"]["today"] == 1
    assert body["logins"]["daily_history"][-1]["count"] == 1  # today is the last point in the history


def test_repeat_logins_count_each_time_but_user_counted_once(client):
    register(client, "repeat@example.com")
    for _ in range(3):
        assert client.post(
            "/auth/login", json={"email": "repeat@example.com", "password": PASSWORD}
        ).status_code == 200
    admin = _admin(client)

    body = client.get("/admin/stats/overview", headers=admin).json()
    assert body["users"]["users_logged_in"] == 1  # one distinct user, however many times they logged in
    assert body["logins"]["today"] == 3  # but every login is recorded in the daily count


def test_failed_login_is_not_recorded(client):
    register(client, "wrongpw@example.com")
    client.post("/auth/login", json={"email": "wrongpw@example.com", "password": "not-the-password"})
    admin = _admin(client)

    stats = client.get("/admin/stats/overview", headers=admin).json()["users"]
    assert stats["users_logged_in"] == 0
    assert stats["users_never_logged_in"] == 2  # wrongpw@ never actually logged in successfully


def test_login_history_buckets_by_day(client):
    admin_headers = _admin(client)
    admin_id = _user_id(client, admin_headers)
    db = SessionLocal()
    try:
        yesterday = activity_service.today_local() - timedelta(days=1)
        db.add(UserLogin(user_id=admin_id, login_at=datetime.utcnow() - timedelta(days=1), login_date=yesterday))
        db.commit()
    finally:
        db.close()

    body = client.get("/admin/stats/overview", headers=admin_headers).json()["logins"]
    assert body["yesterday"] >= 1
    assert body["last_7_days"] >= body["yesterday"]


# ---------------------------------------------------------------------------
# 3. Practice / audio recording activity — failed attempts must not count
# ---------------------------------------------------------------------------
def _make_lesson(db, created_by_id: int) -> Lesson:
    lesson = Lesson(
        title="Ordering coffee",
        description="A short roleplay",
        lesson_type="video",
        difficulty="beginner",
        duration_seconds=120,
        published=True,
        created_by_id=created_by_id,
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return lesson


def test_recording_stats_exclude_failed_and_pending_attempts(client):
    teacher = auth_headers(client, "recorder@example.com")
    admin = _admin(client)
    uid = _user_id(client, teacher)
    admin_id = _user_id(client, admin)

    db = SessionLocal()
    try:
        lesson = _make_lesson(db, admin_id)
        db.add_all(
            [
                SpeakingAttempt(
                    user_id=uid,
                    lesson_id=lesson.id,
                    audio_url="https://res.cloudinary.com/demo/a.webm",
                    reference_text="Hello there",
                    analysis_status="completed",
                    overall_score=80.0,
                ),
                SpeakingAttempt(
                    user_id=uid,
                    lesson_id=lesson.id,
                    audio_url="https://res.cloudinary.com/demo/b.webm",
                    reference_text="Hello there",
                    analysis_status="completed",
                    overall_score=90.0,
                ),
                SpeakingAttempt(
                    user_id=uid,
                    lesson_id=lesson.id,
                    audio_url="https://res.cloudinary.com/demo/c.webm",
                    reference_text="Hello there",
                    analysis_status="failed",
                    error_message="Transcription failed",
                ),
                SpeakingAttempt(
                    user_id=uid,
                    lesson_id=lesson.id,
                    audio_url="https://res.cloudinary.com/demo/d.webm",
                    reference_text="Hello there",
                    analysis_status="processing",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    completion = client.get("/admin/stats/overview", headers=admin).json()["completion"]
    assert completion["users_completed_practice"] == 1
    assert completion["practice_attempts_completed"] == 2  # only the 2 "completed" rows
    assert completion["practice_attempts_total"] == 4  # completed + failed + processing

    recent = client.get("/admin/stats/overview", headers=admin).json()["recent_activity"]
    assert len(recent) == 4
    assert recent[0]["user_name"] == "Test Teacher"


def test_user_who_never_recorded_is_not_counted_as_completed(client):
    auth_headers(client, "idle@example.com")
    admin = _admin(client)
    completion = client.get("/admin/stats/overview", headers=admin).json()["completion"]
    assert completion["users_completed_practice"] == 0
    assert completion["practice_attempts_total"] == 0


# ---------------------------------------------------------------------------
# 4. Video / podcast watching activity
# ---------------------------------------------------------------------------
def test_video_activity_counts_only_users_who_watched(client):
    watcher = auth_headers(client, "watcher@example.com")
    auth_headers(client, "bystander@example.com")  # never watches anything
    admin = _admin(client)

    res = client.post("/progress/activity", json={"activity_type": "video"}, headers=watcher)
    assert res.status_code == 201

    media = client.get("/admin/stats/overview", headers=admin).json()["media"]
    assert media["users_who_accessed_media"] == 1
    assert media["video_activity_count"] == 1
    assert media["podcast_activity_count"] == 0


def test_video_activity_can_reference_a_lesson_for_top_media(client):
    teacher = auth_headers(client, "lesson-watcher@example.com")
    admin = _admin(client)
    admin_id = _user_id(client, admin)

    db = SessionLocal()
    try:
        lesson = _make_lesson(db, admin_id)
        db.add(LessonMedia(lesson_id=lesson.id, url="https://res.cloudinary.com/demo/vid.mp4", media_type="video"))
        db.commit()
        lesson_id = lesson.id
    finally:
        db.close()

    res = client.post("/progress/activity", json={"activity_type": "video", "lesson_id": lesson_id}, headers=teacher)
    assert res.status_code == 201

    media = client.get("/admin/stats/overview", headers=admin).json()["media"]
    assert media["total_videos"] == 1
    assert media["lessons_with_media"] == 1
    assert any(item["lesson_id"] == lesson_id and item["times_accessed"] == 1 for item in media["most_used_media"])


def test_practice_activity_is_not_counted_as_video_or_podcast_activity(client):
    """Recording audio must not inflate the video/podcast 'watched' numbers."""
    teacher = auth_headers(client, "speaker-only@example.com")
    admin = _admin(client)
    uid = _user_id(client, teacher)
    admin_id = _user_id(client, admin)

    db = SessionLocal()
    try:
        lesson = _make_lesson(db, admin_id)
        activity_service.record_activity(db, user_id=uid, activity_type=ActivityType.PRACTICE, lesson_id=lesson.id)
    finally:
        db.close()

    media = client.get("/admin/stats/overview", headers=admin).json()["media"]
    assert media["users_who_accessed_media"] == 0
    assert media["video_activity_count"] == 0
