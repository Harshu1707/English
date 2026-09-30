"""Admin content-completion analytics: security, completion rules and data accuracy.

Completions are created through the real teacher-facing endpoints (`POST /progress/activity`
and `POST /progress/lessons/{id}`), then read back through the admin endpoints, so the whole
path is exercised. Lessons are inserted with the same ORM models the app uses.
"""
from app.database.session import SessionLocal
from app.models.models import Lesson, LessonMedia, UserLessonProgress
from tests.conftest import auth_headers

BASE = "/admin/content-progress"
ADMIN_ROUTES = ["/summary", "/teachers", "/content", "/content/1", "/records"]


def _admin(client, email="admin@example.com"):
    return auth_headers(client, email, role="admin", admin_invite_code="let-me-in-123")


def _user_id(client, headers) -> int:
    return client.get("/auth/me", headers=headers).json()["id"]


def _lesson(title, lesson_type, admin_id, *, published=True, media_type=None) -> int:
    db = SessionLocal()
    try:
        lesson = Lesson(
            title=title,
            description="d",
            lesson_type=lesson_type,
            difficulty="beginner",
            duration_seconds=120,
            published=published,
            created_by_id=admin_id,
        )
        db.add(lesson)
        db.commit()
        db.refresh(lesson)
        if media_type:
            db.add(
                LessonMedia(
                    lesson_id=lesson.id,
                    url="https://res.cloudinary.com/demo/x",
                    media_type=media_type,
                    provider="cloudinary",
                )
            )
            db.commit()
        return lesson.id
    finally:
        db.close()


def _progress_row(user_id, lesson_id):
    db = SessionLocal()
    try:
        return db.query(UserLessonProgress).filter_by(user_id=user_id, lesson_id=lesson_id).all()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
def test_every_route_requires_authentication(client):
    for path in ADMIN_ROUTES:
        assert client.get(BASE + path).status_code == 401, path


def test_teacher_gets_403_on_every_route(client, teacher):
    for path in ADMIN_ROUTES:
        assert client.get(BASE + path, headers=teacher).status_code == 403, path


def test_responses_never_contain_password_hashes(client, teacher):
    admin = _admin(client)
    lesson_id = _lesson("Intro", "video", _user_id(client, admin))
    client.post("/progress/activity", json={"activity_type": "video", "lesson_id": lesson_id}, headers=teacher)
    for path in ["/teachers", "/records", f"/content/{lesson_id}"]:
        text = client.get(BASE + path, headers=admin).text
        assert "password" not in text.lower() and "$2b$" not in text, path


# ---------------------------------------------------------------------------
# Completion is recorded per teacher and per lesson
# ---------------------------------------------------------------------------
def test_mark_as_complete_stamps_completed_at_once(client, teacher):
    admin = _admin(client)
    lesson_id = _lesson("Intro to Speaking", "video", _user_id(client, admin))
    uid = _user_id(client, teacher)
    body = {"activity_type": "video", "lesson_id": lesson_id}

    assert client.post("/progress/activity", json=body, headers=teacher).status_code == 201
    first = _progress_row(uid, lesson_id)
    assert len(first) == 1 and first[0].completed and first[0].completed_at is not None

    assert client.post("/progress/activity", json=body, headers=teacher).status_code == 201
    second = _progress_row(uid, lesson_id)
    assert len(second) == 1  # no duplicate record
    assert second[0].completed_at == first[0].completed_at  # first completion time is kept


def test_percent_below_threshold_is_not_completion(client, teacher):
    admin = _admin(client)
    lesson_id = _lesson("Podcast", "podcast", _user_id(client, admin))
    res = client.post(f"/progress/lessons/{lesson_id}", json={"percent": 89}, headers=teacher)
    assert res.status_code == 200
    assert res.json()["completed"] is False and res.json()["completed_at"] is None
    assert res.json()["progress_percent"] == 89


def test_percent_at_threshold_completes_and_is_permanent(client, teacher):
    admin = _admin(client)
    lesson_id = _lesson("Podcast", "podcast", _user_id(client, admin))
    url = f"/progress/lessons/{lesson_id}"

    done = client.post(url, json={"percent": 90}, headers=teacher).json()
    assert done["completed"] is True and done["progress_percent"] == 100 and done["completed_at"]

    # Scrubbing back / reopening / repeating never un-completes or re-stamps.
    again = client.post(url, json={"percent": 5}, headers=teacher).json()
    assert again["completed"] is True and again["completed_at"] == done["completed_at"]
    assert len(_progress_row(_user_id(client, teacher), lesson_id)) == 1


def test_progress_only_moves_forward(client, teacher):
    admin = _admin(client)
    lesson_id = _lesson("Video", "video", _user_id(client, admin))
    url = f"/progress/lessons/{lesson_id}"
    client.post(url, json={"percent": 60}, headers=teacher)
    assert client.post(url, json={"percent": 30}, headers=teacher).json()["progress_percent"] == 60


def test_auto_completion_counts_as_learning_activity_once(client, teacher):
    admin = _admin(client)
    lesson_id = _lesson("Video", "video", _user_id(client, admin))
    url = f"/progress/lessons/{lesson_id}"
    client.post(url, json={"percent": 95}, headers=teacher)
    client.post(url, json={"percent": 100}, headers=teacher)
    summary = client.get("/progress/summary", headers=teacher).json()
    assert summary["completed_videos"] == 1


def test_progress_report_validates_input_and_lesson(client, teacher):
    assert client.post("/progress/lessons/999999", json={"percent": 50}, headers=teacher).status_code == 404
    admin = _admin(client)
    lesson_id = _lesson("Video", "video", _user_id(client, admin))
    for bad in (-1, 101):
        assert client.post(f"/progress/lessons/{lesson_id}", json={"percent": bad}, headers=teacher).status_code == 422
    assert client.post(f"/progress/lessons/{lesson_id}", json={"percent": 50}).status_code == 401


# ---------------------------------------------------------------------------
# What the admin sees
# ---------------------------------------------------------------------------
def _scenario(client):
    """John completes the video and the podcast; Sarah completes only the video; Priya nothing."""
    admin = _admin(client)
    admin_id = _user_id(client, admin)
    video = _lesson("Introduction to Speaking", "video", admin_id)
    podcast = _lesson("British English A1 Podcast", "podcast", admin_id)
    john = auth_headers(client, "john@example.com", name="John Smith")
    sarah = auth_headers(client, "sarah@example.com", name="Sarah Williams")
    auth_headers(client, "priya@example.com", name="Priya Sharma")
    for who, lesson, kind in ((john, video, "video"), (john, podcast, "podcast"), (sarah, video, "video")):
        assert client.post("/progress/activity", json={"activity_type": kind, "lesson_id": lesson}, headers=who).status_code == 201
    return admin, video, podcast


def test_summary_counts_from_the_database(client):
    admin, _, _ = _scenario(client)
    s = client.get(f"{BASE}/summary", headers=admin).json()
    assert s["total_teachers"] == 3  # the admin is not a teacher
    assert (s["total_videos"], s["total_podcasts"]) == (1, 1)
    assert (s["video_completions"], s["podcast_completions"]) == (2, 1)
    assert (s["teachers_completed_videos"], s["teachers_completed_podcasts"]) == (2, 1)


def test_summary_on_an_empty_system_is_zeros(client):
    admin = _admin(client)
    s = client.get(f"{BASE}/summary", headers=admin).json()
    assert all(value == 0 for value in s.values())


def test_teacher_list(client):
    admin, _, _ = _scenario(client)
    rows = client.get(f"{BASE}/teachers", headers=admin).json()
    by_email = {r["email"]: r for r in rows}
    assert by_email["john@example.com"]["videos_completed"] == 1
    assert by_email["john@example.com"]["podcasts_completed"] == 1
    assert by_email["john@example.com"]["total_completed"] == 2
    assert by_email["john@example.com"]["last_activity"].endswith("Z")
    assert by_email["sarah@example.com"]["total_completed"] == 1
    assert by_email["priya@example.com"]["total_completed"] == 0
    assert by_email["priya@example.com"]["last_activity"] is None
    assert "admin@example.com" not in by_email
    assert [r["email"] for r in client.get(f"{BASE}/teachers?search=SARAH", headers=admin).json()] == ["sarah@example.com"]


def test_content_detail_lists_completed_and_not_completed(client):
    admin, video, _ = _scenario(client)
    d = client.get(f"{BASE}/content/{video}", headers=admin).json()
    assert d["title"] == "Introduction to Speaking" and d["content_type"] == "video"
    assert sorted(p["email"] for p in d["completed"]) == ["john@example.com", "sarah@example.com"]
    assert [p["email"] for p in d["not_completed"]] == ["priya@example.com"]
    assert all(p["completed_at"].endswith("Z") for p in d["completed"])
    assert client.get(f"{BASE}/content/424242", headers=admin).status_code == 404


def test_records_filters_and_paging(client):
    admin, video, podcast = _scenario(client)
    everything = client.get(f"{BASE}/records", headers=admin).json()
    assert everything["total"] == 6  # 3 teachers x 2 items

    todo = client.get(f"{BASE}/records?status=not_completed&content_type=podcast", headers=admin).json()
    assert sorted(r["teacher_email"] for r in todo["items"]) == ["priya@example.com", "sarah@example.com"]
    assert all(r["completed_at"] is None and r["status"] == "not_completed" for r in todo["items"])

    one = client.get(f"{BASE}/records?lesson_id={video}&status=completed", headers=admin).json()
    assert one["total"] == 2

    page = client.get(f"{BASE}/records?limit=4&offset=4", headers=admin).json()
    assert page["total"] == 6 and len(page["items"]) == 2

    assert client.get(f"{BASE}/records?status=bogus", headers=admin).status_code == 422
    assert client.get(f"{BASE}/records?limit=0", headers=admin).status_code == 422


def test_lesson_type_falls_back_to_uploaded_media_and_other_lessons_are_excluded(client):
    admin = _admin(client)
    admin_id = _user_id(client, admin)
    inferred = _lesson("Untyped audio lesson", "lesson", admin_id, media_type="audio")
    _lesson("Reading task", "reading", admin_id)  # no media, not video/podcast: not part of this report
    items = client.get(f"{BASE}/content", headers=admin).json()
    assert [(i["content_id"], i["content_type"]) for i in items] == [(inferred, "podcast")]


def test_completion_recorded_before_completed_at_existed_shows_completed_without_a_date(client, teacher):
    admin = _admin(client)
    lesson_id = _lesson("Old lesson", "video", _user_id(client, admin))
    db = SessionLocal()
    try:  # exactly what a pre-migration completion looks like: completed, no timestamp
        db.add(UserLessonProgress(user_id=_user_id(client, teacher), lesson_id=lesson_id, progress_percent=100, completed=True))
        db.commit()
    finally:
        db.close()
    d = client.get(f"{BASE}/content/{lesson_id}", headers=admin).json()
    assert len(d["completed"]) == 1 and d["completed"][0]["completed_at"] is None

    # Clicking "Mark as complete" again must NOT invent a completion date for the old record.
    client.post("/progress/activity", json={"activity_type": "video", "lesson_id": lesson_id}, headers=teacher)
    d = client.get(f"{BASE}/content/{lesson_id}", headers=admin).json()
    assert d["completed"][0]["completed_at"] is None


def test_unpublished_lessons_are_included_and_flagged(client):
    admin = _admin(client)
    _lesson("Draft video", "video", _user_id(client, admin), published=False)
    items = client.get(f"{BASE}/content", headers=admin).json()
    assert len(items) == 1 and items[0]["published"] is False
