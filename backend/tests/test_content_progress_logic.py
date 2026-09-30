"""Unit tests for the admin content-completion rules. Pure Python: no database or web stack."""
from datetime import datetime

from app.services.content_progress import (
    COMPLETED,
    NOT_COMPLETED,
    PODCAST,
    VIDEO,
    Content,
    Progress,
    Teacher,
    classify,
    content_detail,
    content_rows,
    make_snapshot,
    overview,
    record_rows,
    teacher_rows,
)

T1 = Teacher(1, "John Smith", "john@example.com")
T2 = Teacher(2, "Sarah Williams", "sarah@example.com")
T3 = Teacher(3, "Priya Sharma", "priya@example.com")
V1 = Content(10, "Introduction to Speaking", VIDEO, True)
V2 = Content(11, "Greetings", VIDEO, False)
P1 = Content(20, "British English A1 Podcast", PODCAST, True)

D1 = datetime(2026, 9, 24, 9, 30)
D2 = datetime(2026, 9, 20, 8, 0)


def _done(when=D1):
    return Progress(100, True, when, when)


def _snap():
    progress = {
        (1, 10): _done(D1),            # John completed video 1
        (2, 10): _done(D2),            # Sarah completed video 1
        (1, 11): Progress(40, False, None, D2),   # John started video 2 only
        (1, 20): _done(D2),            # John completed the podcast
        (99, 10): _done(D1),           # a non-teacher (admin) row: must be ignored
        (1, 777): _done(D1),           # a lesson that is not video/podcast content: ignored
    }
    return make_snapshot([T3, T1, T2], [P1, V2, V1], progress)


# ---- classification ----------------------------------------------------------------------
def test_classify_uses_lesson_type_first():
    assert classify("video") == VIDEO
    assert classify(" Podcast ") == PODCAST
    assert classify("AUDIO") == PODCAST
    assert classify("video", ["audio"]) == VIDEO


def test_classify_falls_back_to_media_then_none():
    assert classify("lesson", ["thumbnail", "video"]) == VIDEO
    assert classify("", ["audio"]) == PODCAST
    assert classify(None, ["thumbnail"]) is None
    assert classify("reading", []) is None


# ---- snapshot hygiene ----------------------------------------------------------------------
def test_snapshot_drops_non_teacher_and_non_content_rows_and_sorts():
    snap = _snap()
    assert [t.name for t in snap.teachers] == ["John Smith", "Priya Sharma", "Sarah Williams"]
    assert [c.title for c in snap.contents] == ["British English A1 Podcast", "Greetings", "Introduction to Speaking"]
    assert (99, 10) not in snap.progress and (1, 777) not in snap.progress


# ---- summary cards ---------------------------------------------------------------------------
def test_overview_counts():
    o = overview(_snap())
    assert o["total_teachers"] == 3
    assert (o["total_videos"], o["total_podcasts"]) == (2, 1)
    assert (o["video_completions"], o["podcast_completions"]) == (2, 1)
    assert (o["teachers_completed_videos"], o["teachers_completed_podcasts"]) == (2, 1)
    assert (o["possible_video_completions"], o["possible_podcast_completions"]) == (6, 3)


def test_overview_with_no_data_is_all_zero_not_an_error():
    o = overview(make_snapshot([], [], {}))
    assert all(v == 0 for v in o.values())


# ---- teacher list ----------------------------------------------------------------------------
def test_teacher_rows_counts_dates_and_order():
    rows = teacher_rows(_snap())
    by_name = {r["name"]: r for r in rows}
    assert by_name["John Smith"]["videos_completed"] == 1
    assert by_name["John Smith"]["podcasts_completed"] == 1
    assert by_name["John Smith"]["total_completed"] == 2
    assert by_name["John Smith"]["last_activity"] == D1
    assert by_name["Sarah Williams"]["total_completed"] == 1
    assert by_name["Priya Sharma"]["total_completed"] == 0
    assert by_name["Priya Sharma"]["last_activity"] is None  # never fabricated
    assert [r["name"] for r in rows] == ["John Smith", "Sarah Williams", "Priya Sharma"]  # most first


def test_teacher_rows_search_by_name_or_email():
    assert [r["name"] for r in teacher_rows(_snap(), "  SARAH ")] == ["Sarah Williams"]
    assert [r["name"] for r in teacher_rows(_snap(), "priya@")] == ["Priya Sharma"]
    assert teacher_rows(_snap(), "nobody") == []


def test_a_started_but_unfinished_lesson_is_activity_but_not_a_completion():
    snap = make_snapshot([T3], [V1], {(3, 10): Progress(35, False, None, D1)})
    row = teacher_rows(snap)[0]
    assert row["total_completed"] == 0 and row["last_activity"] == D1


# ---- content list / detail ---------------------------------------------------------------------
def test_content_rows_and_kind_filter():
    rows = content_rows(_snap())
    intro = next(r for r in rows if r["title"] == "Introduction to Speaking")
    assert (intro["completed_count"], intro["not_completed_count"], intro["total_teachers"]) == (2, 1, 3)
    assert [r["content_type"] for r in content_rows(_snap(), PODCAST)] == [PODCAST]
    assert next(r for r in rows if r["title"] == "Greetings")["published"] is False


def test_content_detail_splits_completed_and_not_completed():
    d = content_detail(_snap(), 10)
    assert [p["name"] for p in d["completed"]] == ["John Smith", "Sarah Williams"]  # newest first
    assert [p["name"] for p in d["not_completed"]] == ["Priya Sharma"]
    assert d["completed"][0]["completed_at"] == D1
    assert d["not_completed"][0]["completed_at"] is None
    assert content_detail(_snap(), 12345) is None


def test_completion_without_a_recorded_date_is_still_completed_and_sorts_last():
    legacy = Progress(100, True, None, D2)  # completed before completed_at existed
    snap = make_snapshot([T1, T2], [V1], {(1, 10): legacy, (2, 10): _done(D1)})
    d = content_detail(snap, 10)
    assert [p["name"] for p in d["completed"]] == ["Sarah Williams", "John Smith"]
    assert d["completed"][1]["completed_at"] is None


def test_partial_progress_is_reported_but_stays_not_completed():
    d = content_detail(_snap(), 11)
    john = next(p for p in d["not_completed"] if p["name"] == "John Smith")
    assert john["progress_percent"] == 40
    assert d["completed"] == []


# ---- flat records + filters --------------------------------------------------------------------
def test_record_rows_cover_every_teacher_content_pair():
    assert len(record_rows(_snap())) == 3 * 3


def test_record_rows_filters():
    snap = _snap()
    assert {r["content_type"] for r in record_rows(snap, kind=VIDEO)} == {VIDEO}
    done = record_rows(snap, status=COMPLETED)
    assert len(done) == 3 and all(r["completed_at"] is not None for r in done)
    todo = record_rows(snap, status=NOT_COMPLETED, content_id=10)
    assert [r["teacher_name"] for r in todo] == ["Priya Sharma"]
    assert all(r["status"] == NOT_COMPLETED and r["completed_at"] is None for r in todo)
    assert [r["teacher_email"] for r in record_rows(snap, search="john", content_id=20)] == ["john@example.com"]
    assert record_rows(snap, kind=PODCAST, content_id=10) == []  # filters combine with AND
