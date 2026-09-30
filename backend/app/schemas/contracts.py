import math
import re
from datetime import date, datetime, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator, model_validator

from app.models.models import ActivityType, Role

_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def _normalise_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 255 or not _EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address")
    return value


def _clamp_score(value: float | None) -> float | None:
    """Scores from an AI/provider are untrusted input: force them into 0-100 (or None)."""
    if value is None:
        return None
    value = float(value)
    if math.isnan(value):
        return None
    return max(0.0, min(100.0, value))


def _iso_utc(value: datetime) -> str:
    # The DB stores naive UTC; without a zone marker browsers would read it as local time.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str)]

class RegisterRequest(BaseModel):
    email: str
    full_name: str = Field(min_length=2, max_length=150)
    password: str = Field(min_length=12, max_length=128)
    confirm_password: str = Field(max_length=128)
    role: Role = Role.TEACHER
    # Only consulted when role == admin (see routers/auth.py).
    admin_invite_code: str | None = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _normalise_email(v)

    @field_validator("full_name", mode="before")
    @classmethod
    def _strip_name(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("password")
    @classmethod
    def _bcrypt_limit(cls, v: str) -> str:
        # bcrypt only uses the first 72 bytes; refuse rather than silently truncate.
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes long")
        return v

    @model_validator(mode="after")
    def _passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self
class LoginRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.strip().lower()
class UserOut(BaseModel):
    """The only user fields the API ever returns: never password_hash."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: Role


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut | None = None
class LessonCreate(BaseModel): title:str; description:str; lesson_type:str; difficulty:str; duration_seconds:int=Field(gt=0); tags:list[str]=[]; published:bool=False
class PronunciationIssue(BaseModel):
    word: str
    note: str = ""


class FillerWord(BaseModel):
    word: str
    count: int


class SpeechSignals(BaseModel):
    transcript: str | None = None
    pronunciation: float | None = None
    fluency: float | None = None
    accuracy: float | None = None
    intonation: float | None = None
    # Additive fields. words_per_minute / pace / filler_words are computed from the transcript and
    # recording duration by the analysis pipeline (deterministic, not AI-generated).
    pronunciation_issues: list[PronunciationIssue] = []
    filler_words: list[FillerWord] = []
    words_per_minute: float | None = None
    pace: float | None = None
    duration_seconds: float | None = None
    provider_data: dict = {}

    @field_validator("pronunciation", "fluency", "accuracy", "intonation", "pace")
    @classmethod
    def _clamp(cls, v):
        return _clamp_score(v)
class GrammarError(BaseModel):
    original: str  # exact words from the transcript
    correction: str
    explanation: str = ""
    category: str | None = None  # e.g. tense, article, preposition, subject-verb agreement


class VocabSuggestion(BaseModel):
    word: str
    suggestion: str
    note: str = ""


class AIAnalysis(BaseModel):
    grammar_score: float | None = None
    vocabulary_score: float | None = None
    sentence_structure_score: float | None = None
    feedback: str
    strengths: list[str] = []
    areas_to_improve: list[str] = []
    practice_words: list[str] = []
    recommendations: list[str] = []
    grammar_errors: list[GrammarError] = []
    vocabulary_suggestions: list[VocabSuggestion] = []
    repeated_words: list[str] = []
    sentence_structure_notes: list[str] = []

    @field_validator("grammar_score", "vocabulary_score", "sentence_structure_score")
    @classmethod
    def _clamp(cls, v):
        return _clamp_score(v)


class LessonMediaOut(BaseModel):
    id: int
    lesson_id: int
    url: str
    media_type: str
    provider: str
    public_id: str | None = None
    resource_type: str | None = None
    format: str | None = None
    width: int | None = None
    height: int | None = None
    file_size: int | None = None
    duration_seconds: int | None = None
    original_filename: str | None = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Practice / speaking analysis (responses)
# ---------------------------------------------------------------------------
class AttemptScores(BaseModel):
    overall: float | None = None
    pronunciation: float | None = None
    fluency: float | None = None
    grammar: float | None = None
    vocabulary: float | None = None
    sentence_structure: float | None = None
    pace: float | None = None


class AttemptSummary(BaseModel):
    id: int
    number: int | None = None  # 1 = the user's first attempt
    status: str  # processing | transcribing | analyzing | completed | failed
    overall_score: float | None = None
    lesson_id: int | None = None
    duration_seconds: float | None = None
    created_at: UtcDatetime


class AttemptDetail(AttemptSummary):
    reference_text: str
    transcript: str | None = None
    audio_url: str
    error_message: str | None = None
    scores: AttemptScores = AttemptScores()
    words_per_minute: float | None = None
    filler_words: list[FillerWord] = []
    pronunciation_issues: list[PronunciationIssue] = []
    grammar_errors: list[GrammarError] = []
    vocabulary_suggestions: list[VocabSuggestion] = []
    repeated_words: list[str] = []
    sentence_structure_notes: list[str] = []
    strengths: list[str] = []
    areas_to_improve: list[str] = []
    practice_words: list[str] = []
    recommendations: list[str] = []
    overall_feedback: str | None = None
    # What produced each part of the result, so the UI can be honest about it.
    assessment: dict[str, str] = {}


class AttemptList(BaseModel):
    total: int
    items: list[AttemptSummary]


# ---------------------------------------------------------------------------
# Progress, streaks and the activity calendar (per authenticated user)
# ---------------------------------------------------------------------------
class ProgressSignals(BaseModel):
    pronunciation: float | None = None
    fluency: float | None = None
    grammar: float | None = None
    vocabulary: float | None = None


class ProgressSummary(BaseModel):
    """Learning statistics for one user. All zeros for a brand-new account."""

    today: date
    current_streak: int = 0
    longest_streak: int = 0
    active_days: int = 0
    progress_percent: int = 0
    completed_videos: int = 0
    completed_podcasts: int = 0
    practice_activities: int = 0
    lessons_completed: int = 0
    lessons_total: int = 0
    speaking_attempts: int = 0
    speaking_seconds: int = 0
    overall_score: float | None = None
    average_score: float | None = None
    signals: ProgressSignals = ProgressSignals()


class ActivityCalendar(BaseModel):
    year: int
    month: int
    days_in_month: int
    first_weekday: int  # Monday = 0 ... Sunday = 6
    today: date
    active_days: list[int] = []


class ActivityRequest(BaseModel):
    activity_type: ActivityType
    lesson_id: int | None = None


# ============================================================
# ADMIN ANALYTICS
# ============================================================

class AdminUserStats(BaseModel):
    total_users: int
    total_teachers: int
    total_admins: int
    active_users: int
    inactive_users: int
    users_logged_in: int
    users_never_logged_in: int
    new_users_last_7_days: int
    new_users_last_30_days: int


class DailyLoginPoint(BaseModel):
    date: date
    count: int


class AdminLoginStats(BaseModel):
    today: int
    yesterday: int
    last_7_days: int
    last_30_days: int
    daily_history: list[DailyLoginPoint] = []


class AdminCompletionStats(BaseModel):
    users_started_learning: int
    users_completed_a_lesson: int
    lessons_completed_total: int
    users_completed_practice: int
    practice_attempts_completed: int
    practice_attempts_total: int
    total_published_lessons: int
    completion_rate_percent: float | None


class TopMediaItem(BaseModel):
    lesson_id: int
    lesson_title: str
    media_type: str
    times_accessed: int


class AdminMediaStats(BaseModel):
    total_media: int
    total_videos: int
    total_audio: int
    total_images: int
    lessons_with_media: int
    users_who_accessed_media: int
    video_activity_count: int
    podcast_activity_count: int
    most_used_media: list[TopMediaItem] = []


class RecentActivityItem(BaseModel):
    user_name: str
    activity: str
    detail: str
    score: float | None
    created_at: UtcDatetime


class AdminOverview(BaseModel):
    users: AdminUserStats
    logins: AdminLoginStats
    completion: AdminCompletionStats
    media: AdminMediaStats
    recent_activity: list[RecentActivityItem] = []


# ---------------------------------------------------------------------------
# Lesson completion (teacher reports playback progress) and admin content-completion analytics
# ---------------------------------------------------------------------------
class LessonProgressRequest(BaseModel):
    """How far through a video/podcast the signed-in teacher is, as a percentage (0-100)."""

    percent: int = Field(ge=0, le=100)


class LessonProgressOut(BaseModel):
    lesson_id: int
    progress_percent: int
    completed: bool
    completed_at: UtcDatetime | None = None


class ContentProgressSummary(BaseModel):
    total_teachers: int
    total_videos: int
    total_podcasts: int
    video_completions: int
    podcast_completions: int
    possible_video_completions: int
    possible_podcast_completions: int
    teachers_completed_videos: int
    teachers_completed_podcasts: int


class ContentProgressTeacher(BaseModel):
    teacher_id: int
    name: str
    email: str
    videos_completed: int
    podcasts_completed: int
    total_completed: int
    last_activity: UtcDatetime | None = None


class ContentProgressItem(BaseModel):
    content_id: int
    title: str
    content_type: str  # "video" | "podcast"
    published: bool
    completed_count: int
    not_completed_count: int
    total_teachers: int


class ContentProgressPerson(BaseModel):
    teacher_id: int
    name: str
    email: str
    progress_percent: int
    completed_at: UtcDatetime | None = None


class ContentProgressDetail(BaseModel):
    content_id: int
    title: str
    content_type: str
    published: bool
    total_teachers: int
    completed: list[ContentProgressPerson]
    not_completed: list[ContentProgressPerson]


class ContentProgressRecord(BaseModel):
    teacher_id: int
    teacher_name: str
    teacher_email: str
    content_id: int
    content_title: str
    content_type: str
    status: str  # "completed" | "not_completed"
    progress_percent: int
    completed_at: UtcDatetime | None = None


class ContentProgressRecordPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ContentProgressRecord]
