"""Progress, streak, calendar and user-isolation behaviour."""
from datetime import timedelta

from app.database.session import SessionLocal
from app.models.models import ActivityType, User
from app.services import activity_service


def _user_id(client, headers) -> int:
    return client.get("/auth/me", headers=headers).json()["id"]


def _seed(user_id: int, *offsets_in_days: int, activity_type=ActivityType.PRACTICE):
    """Write activity rows directly, so 'yesterday'/'tomorrow' cases are testable."""
    today = activity_service.today_local()
    db = SessionLocal()
    try:
        for offset in offsets_in_days:
            activity_service.record_activity(
                db,
                user_id=user_id,
                activity_type=activity_type,
                when=today + timedelta(days=offset),
            )
    finally:
        db.close()


def test_new_teacher_starts_from_zero(client, teacher):
    body = client.get("/progress/summary", headers=teacher).json()
    assert body["current_streak"] == 0
    assert body["longest_streak"] == 0
    assert body["progress_percent"] == 0
    assert body["completed_videos"] == 0
    assert body["completed_podcasts"] == 0
    assert body["practice_activities"] == 0

    calendar = client.get("/progress/calendar", headers=teacher).json()
    assert calendar["active_days"] == []


def test_first_activity_gives_streak_of_one(client, teacher):
    _seed(_user_id(client, teacher), 0)
    body = client.get("/progress/summary", headers=teacher).json()
    assert body["current_streak"] == 1
    assert body["longest_streak"] == 1

    calendar = client.get("/progress/calendar", headers=teacher).json()
    assert calendar["today"] in str(activity_service.today_local())
    assert activity_service.today_local().day in calendar["active_days"]


def test_several_activities_on_one_day_count_once(client, teacher):
    uid = _user_id(client, teacher)
    _seed(uid, 0, activity_type=ActivityType.VIDEO)
    _seed(uid, 0, activity_type=ActivityType.PODCAST)
    _seed(uid, 0, activity_type=ActivityType.PRACTICE)

    body = client.get("/progress/summary", headers=teacher).json()
    assert body["current_streak"] == 1
    assert body["active_days"] == 1
    assert body["completed_videos"] == 1
    assert body["completed_podcasts"] == 1
    assert body["practice_activities"] == 1

    calendar = client.get("/progress/calendar", headers=teacher).json()
    assert calendar["active_days"].count(activity_service.today_local().day) == 1


def test_consecutive_days_increase_the_streak(client, teacher):
    _seed(_user_id(client, teacher), -1, 0)
    assert client.get("/progress/summary", headers=teacher).json()["current_streak"] == 2


def test_a_missed_day_restarts_the_streak(client, teacher):
    # active three days ago, nothing since -> the run is broken
    _seed(_user_id(client, teacher), -3)
    broken = client.get("/progress/summary", headers=teacher).json()
    assert broken["current_streak"] == 0
    assert broken["longest_streak"] == 1

    _seed(_user_id(client, teacher), 0)  # a new activity today starts again at 1
    restarted = client.get("/progress/summary", headers=teacher).json()
    assert restarted["current_streak"] == 1


def test_streak_survives_a_new_session(client, teacher):
    _seed(_user_id(client, teacher), -1, 0)
    first = client.get("/progress/summary", headers=teacher).json()["current_streak"]
    # A fresh login (new token, nothing carried over from the browser) sees the same streak.
    login = client.post("/auth/login", json={"email": "teacher@example.com", "password": "correct-horse-battery-staple"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/progress/summary", headers=headers).json()["current_streak"] == first == 2


def test_teacher_a_never_sees_teacher_b_data(client, teacher, other_teacher):
    _seed(_user_id(client, teacher), -1, 0)
    other = client.get("/progress/summary", headers=other_teacher).json()
    assert other["current_streak"] == 0
    assert other["active_days"] == 0
    assert client.get("/progress/calendar", headers=other_teacher).json()["active_days"] == []


def test_logging_a_video_updates_the_summary(client, teacher):
    res = client.post("/progress/activity", json={"activity_type": "video"}, headers=teacher)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["completed_videos"] == 1
    assert body["current_streak"] == 1


def test_progress_requires_authentication(client):
    assert client.get("/progress/summary").status_code == 401
    assert client.get("/progress/calendar").status_code == 401
    assert client.post("/progress/activity", json={"activity_type": "video"}).status_code == 401


def test_calendar_handles_leap_years_and_month_lengths(client, teacher):
    february = client.get("/progress/calendar?year=2024&month=2", headers=teacher).json()
    assert february["days_in_month"] == 29
    non_leap = client.get("/progress/calendar?year=2023&month=2", headers=teacher).json()
    assert non_leap["days_in_month"] == 28
    december = client.get("/progress/calendar?year=2023&month=12", headers=teacher).json()
    assert december["days_in_month"] == 31


def test_user_row_is_untouched(client, teacher):
    db = SessionLocal()
    try:
        assert db.query(User).count() == 1
    finally:
        db.close()
