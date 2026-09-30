from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.database.session import Base


# ============================================================
# ENUMS
# ============================================================

class Role(str, Enum):
    ADMIN = "admin"
    TEACHER = "teacher"


class ActivityType(str, Enum):
    """A learning action that makes a calendar day count towards the streak."""

    VIDEO = "video"
    PODCAST = "podcast"
    PRACTICE = "practice"


# ============================================================
# BASE / TIMESTAMP MODEL
# ============================================================

class Timestamped(Base):
    """
    Base class that adds created_at and updated_at
    timestamps to all inherited models.
    """

    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


# ============================================================
# USER
# ============================================================

class User(Timestamped):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[Role] = mapped_column(
        SAEnum(Role),
        default=Role.TEACHER,
        index=True,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )


# ============================================================
# USER LOGIN  (admin analytics: daily/active-user login history)
# ============================================================

class UserLogin(Timestamped):
    """One successful sign-in. Written once per successful /auth/login call — never on
    every API request — so it can be trusted as a real login history for admin analytics.
    """

    __tablename__ = "user_logins"

    __table_args__ = (
        Index("ix_user_logins_user_id_login_at", "user_id", "login_at"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    login_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        index=True,
        nullable=False,
    )

    login_date: Mapped[date] = mapped_column(
        Date,
        index=True,
        nullable=False,
    )


# ============================================================
# LESSON
# ============================================================

class Lesson(Timestamped):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    lesson_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    difficulty: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False,
    )

    duration_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    tags: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    published: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
        nullable=False,
    )

    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )


# ============================================================
# LESSON MEDIA
# ============================================================

class LessonMedia(Timestamped):
    __tablename__ = "lesson_media"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    media_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    file_size: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    duration_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Cloudinary identifiers — public_id is required to replace/delete the
    # remote asset later, so it is stored (not just derived from the URL).
    provider: Mapped[str] = mapped_column(
        String(30),
        default="cloudinary",
        nullable=False,
    )

    public_id: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        nullable=True,
    )

    resource_type: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    format: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    width: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    height: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    original_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    metadata_json: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )


# ============================================================
# LESSON TRANSCRIPT
# ============================================================

class LessonTranscript(Timestamped):
    __tablename__ = "lesson_transcripts"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    locale: Mapped[str] = mapped_column(
        String(20),
        default="en-GB",
        nullable=False,
    )


# ============================================================
# LESSON NOTES
# ============================================================

class LessonNote(Timestamped):
    __tablename__ = "lesson_notes"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    position: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )


# ============================================================
# VOCABULARY
# ============================================================

class Vocabulary(Timestamped):
    __tablename__ = "vocabulary"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    word: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    meaning: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    example_sentence: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    phonetic: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    reference_audio_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    locale: Mapped[str] = mapped_column(
        String(20),
        default="en-GB",
        nullable=False,
    )


# ============================================================
# COMPREHENSION QUESTIONS
# ============================================================

class ComprehensionQuestion(Timestamped):
    __tablename__ = "comprehension_questions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    question_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    options: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    correct_answer: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


# ============================================================
# COMPREHENSION ANSWERS
# ============================================================

class ComprehensionAnswer(Timestamped):
    __tablename__ = "comprehension_answers"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    question_id: Mapped[int] = mapped_column(
        ForeignKey("comprehension_questions.id"),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    answer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    is_correct: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )


# ============================================================
# SPEAKING ATTEMPT
# ============================================================

class SpeakingAttempt(Timestamped):
    __tablename__ = "speaking_attempts"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    lesson_id: Mapped[int | None] = mapped_column(
        ForeignKey("lessons.id"),
        index=True,
        nullable=True,
    )

    audio_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    reference_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    transcript: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    provider: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # pending -> processing -> transcribing -> analyzing -> completed | failed
    analysis_status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        index=True,
        nullable=False,
    )

    # Cloudinary public_id of the stored recording (lets analysis be retried without re-uploading).
    public_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    duration_seconds: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Server-computed mean of the category scores that were actually measured.
    overall_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # User-safe failure reason shown in the UI (never a stack trace or provider error text).
    error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )


# ============================================================
# SPEECH SCORE
# ============================================================

class SpeechScore(Timestamped):
    __tablename__ = "speech_scores"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("speaking_attempts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    pronunciation: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    fluency: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    accuracy: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    intonation: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Derived from transcript word count / recording duration (objective, not AI-generated).
    words_per_minute: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    pace: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    raw_provider_data: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )


# ============================================================
# SPEECH FEEDBACK
# ============================================================

class SpeechFeedback(Timestamped):
    __tablename__ = "speech_feedback"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("speaking_attempts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    grammar_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    vocabulary_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    sentence_structure_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    feedback: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )


# ============================================================
# PRACTICE WORD
# ============================================================

class PracticeWord(Timestamped):
    __tablename__ = "practice_words"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    vocabulary_id: Mapped[int | None] = mapped_column(
        ForeignKey("vocabulary.id"),
        nullable=True,
    )

    word: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        nullable=False,
    )


# ============================================================
# USER PROGRESS
# ============================================================

class UserProgress(Timestamped):
    __tablename__ = "user_progress"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        primary_key=True,
    )

    lessons_completed: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    speaking_seconds: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    current_streak: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )


# ============================================================
# USER LESSON PROGRESS
# ============================================================

class UserLessonProgress(Timestamped):
    __tablename__ = "user_lesson_progress"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "lesson_id",
            name="uq_user_lesson_progress",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id"),
        index=True,
        nullable=False,
    )

    progress_percent: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # UTC time the teacher FIRST completed this lesson. Set once and never overwritten.
    # NULL on rows completed before this column existed and whose time can't be recovered
    # (the admin UI shows those as "date not recorded" instead of inventing a date).
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )


# ============================================================
# NOTIFICATION
# ============================================================

class Notification(Timestamped):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )


# ============================================================
# LEARNING ACTIVITY  (streak / activity-calendar source of truth)
# ============================================================

class LearningActivity(Timestamped):
    """One qualifying learning action by one user on one calendar day.

    Rows are per-action (several rows can share a day); the streak and the
    activity calendar are reconstructed from the DISTINCT activity_date values
    belonging to the authenticated user, so multiple actions on the same day
    still count as a single active day.
    """

    __tablename__ = "learning_activities"

    __table_args__ = (
        Index("ix_learning_activities_user_date", "user_id", "activity_date"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    activity_type: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False,
    )

    activity_date: Mapped[date] = mapped_column(
        Date,
        index=True,
        nullable=False,
    )

    lesson_id: Mapped[int | None] = mapped_column(
        ForeignKey("lessons.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Set for PRACTICE rows so a recording is never counted twice.
    attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("speaking_attempts.id", ondelete="SET NULL"),
        nullable=True,
    )
