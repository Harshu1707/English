"""Practice module API: upload a speaking recording, analyse it in the background, read results/history.

Reuses the existing Cloudinary upload service and the existing SpeakingAttempt / SpeechScore /
SpeechFeedback tables. Every route requires a signed-in user and only ever touches that user's attempts.
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.database.session import get_db
from app.models.models import ActivityType, Lesson, SpeakingAttempt, SpeechFeedback, SpeechScore, User
from app.schemas.contracts import (
    AIAnalysis,
    AttemptDetail,
    AttemptList,
    AttemptScores,
    AttemptSummary,
    FillerWord,
    PronunciationIssue,
)
from app.services.activity_service import record_activity
from app.services.analysis_errors import MESSAGES
from app.services.analysis_pipeline import ACTIVE_STATUSES, STALE_AFTER, expire_if_stale, run_analysis
from app.services.media_service import destroy_on_cloudinary, upload_to_cloudinary, validate_recording_upload

logger = logging.getLogger("verba.practice")
router = APIRouter(prefix="/practice", tags=["practice"])

CLOUDINARY_FOLDER = "verba/recordings"
MAX_CONCURRENT_ANALYSES = 2  # per user; protects the rate-limited speech/AI provider calls from a runaway client


def _summary(attempt: SpeakingAttempt, number: int | None = None) -> AttemptSummary:
    return AttemptSummary(
        id=attempt.id,
        number=number,
        status=attempt.analysis_status,
        overall_score=attempt.overall_score,
        lesson_id=attempt.lesson_id,
        duration_seconds=attempt.duration_seconds,
        created_at=attempt.created_at,
    )


def _own_attempt_or_404(db: Session, attempt_id: int, user: User) -> SpeakingAttempt:
    # 404 (not 403) for someone else's attempt so ids can't be probed.
    attempt = (
        db.query(SpeakingAttempt)
        .filter(SpeakingAttempt.id == attempt_id, SpeakingAttempt.user_id == user.id)
        .first()
    )
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Practice attempt not found")
    expire_if_stale(db, attempt)
    return attempt


def _guard_concurrency(db: Session, user: User) -> None:
    from datetime import datetime

    active = (
        db.query(func.count(SpeakingAttempt.id))
        .filter(
            SpeakingAttempt.user_id == user.id,
            SpeakingAttempt.analysis_status.in_(ACTIVE_STATUSES),
            SpeakingAttempt.updated_at > datetime.utcnow() - STALE_AFTER,
        )
        .scalar()
    )
    if active >= MAX_CONCURRENT_ANALYSES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Your earlier recordings are still being analysed. Please wait for them to finish.",
        )


def _detail(db: Session, attempt: SpeakingAttempt) -> AttemptDetail:
    score = db.query(SpeechScore).filter(SpeechScore.attempt_id == attempt.id).first()
    feedback_row = db.query(SpeechFeedback).filter(SpeechFeedback.attempt_id == attempt.id).first()
    number = (
        db.query(func.count(SpeakingAttempt.id))
        .filter(
            SpeakingAttempt.user_id == attempt.user_id,
            or_(
                SpeakingAttempt.created_at < attempt.created_at,
                (SpeakingAttempt.created_at == attempt.created_at) & (SpeakingAttempt.id <= attempt.id),
            ),
        )
        .scalar()
    )

    try:
        analysis = AIAnalysis.model_validate(feedback_row.feedback) if feedback_row and feedback_row.feedback else None
    except ValueError:
        analysis = None
    raw = (score.raw_provider_data if score else None) or {}
    try:
        fillers = [FillerWord(**f) for f in raw.get("filler_words", [])]
        issues = [PronunciationIssue(**i) for i in raw.get("pronunciation_issues", [])]
    except (TypeError, ValueError):
        fillers, issues = [], []

    scores = AttemptScores(
        overall=attempt.overall_score,
        pronunciation=score.pronunciation if score else None,
        fluency=score.fluency if score else None,
        grammar=feedback_row.grammar_score if feedback_row else None,
        vocabulary=feedback_row.vocabulary_score if feedback_row else None,
        sentence_structure=feedback_row.sentence_structure_score if feedback_row else None,
        pace=score.pace if score else None,
    )

    assessment: dict[str, str] = {}
    if attempt.analysis_status == "completed" and raw.get("assessment") == "groq_whisper":
        model_note = f" ({feedback_row.model})" if feedback_row and feedback_row.model else ""
        assessment = {
            "transcription": "Transcribed from your audio by Whisper speech-to-text. It can smooth over some fillers and unclear words.",
            "pronunciation": "Estimated from Whisper's own recognition confidence and how much of the script's wording came through clearly. It is not phoneme-level scoring.",
        }
        if score and score.fluency is not None:
            assessment["fluency"] = "Calculated from long pauses between words (about a second or more) and filler words. A guide, not a precise measurement."
        assessment["pace"] = "Calculated from your word count and the recording length."
        assessment["language"] = f"Grammar, vocabulary and sentence structure are assessed by an AI language model{model_note} from the transcript."
    elif attempt.analysis_status == "completed" and raw.get("assessment") == "ai_estimate":
        # Attempts stored before the switch to Groq Whisper were assessed by Gemini; keep describing them truthfully.
        assessment = {
            "transcription": "Transcribed by Gemini from your audio, word for word.",
            "pronunciation": "An AI listener's estimate of clarity against British English. It is not phoneme-level scoring.",
            "fluency": "An AI listener's estimate of smoothness and hesitation.",
            "pace": "Calculated from your word count and the recording length.",
            "language": "Grammar, vocabulary and sentence structure are assessed by Gemini from the transcript.",
        }

    return AttemptDetail(
        **_summary(attempt, number).model_dump(),
        reference_text=attempt.reference_text,
        transcript=attempt.transcript,
        audio_url=attempt.audio_url,
        error_message=attempt.error_message,
        scores=scores,
        words_per_minute=score.words_per_minute if score else None,
        filler_words=fillers,
        pronunciation_issues=issues,
        grammar_errors=analysis.grammar_errors if analysis else [],
        vocabulary_suggestions=analysis.vocabulary_suggestions if analysis else [],
        repeated_words=analysis.repeated_words if analysis else [],
        sentence_structure_notes=analysis.sentence_structure_notes if analysis else [],
        strengths=analysis.strengths if analysis else [],
        areas_to_improve=analysis.areas_to_improve if analysis else [],
        practice_words=analysis.practice_words if analysis else [],
        recommendations=analysis.recommendations if analysis else [],
        overall_feedback=analysis.feedback if analysis else None,
        assessment=assessment,
    )


@router.post("/attempts", response_model=AttemptSummary, status_code=status.HTTP_202_ACCEPTED)
async def create_attempt(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    reference_text: str = Form(..., max_length=2000),
    lesson_id: int | None = Form(None),
    duration_seconds: float | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Store the recording in Cloudinary, create the attempt, and start analysis in the background.
    Returns immediately (202); poll GET /practice/attempts/{id} for progress and results."""
    reference_text = reference_text.strip()
    if not reference_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reference_text is required")
    if lesson_id is not None and db.get(Lesson, lesson_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    _guard_concurrency(db, user)

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_size_mb}MB limit",
        )
    head = await file.read(32)
    await file.seek(0)
    validate_recording_upload(file, head)

    max_seconds = settings.max_recording_seconds
    client_duration = duration_seconds if duration_seconds and 0 < duration_seconds < 24 * 3600 else None
    if client_duration and client_duration > max_seconds + 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=MESSAGES["too_long"].format(minutes=max_seconds // 60)
        )

    try:
        result = await upload_to_cloudinary(file, resource_type="video", folder=CLOUDINARY_FOLDER)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            # Not a transient failure: the server itself isn't set up to store recordings
            # (e.g. Cloudinary credentials missing from the environment). Retrying won't help.
            logger.error("Recording upload failed (storage not configured): %s", exc.detail)
            raise HTTPException(
                status_code=exc.status_code,
                detail="Recording storage isn't set up on this server yet. Please contact your administrator.",
            )
        if exc.status_code == status.HTTP_502_BAD_GATEWAY:
            logger.error("Recording upload failed: %s", exc.detail)  # raw provider text stays in the logs
            raise HTTPException(
                status_code=exc.status_code,
                detail="We couldn't store your recording just now. Please try again in a moment.",
            )
        raise

    # Cloudinary measures the real duration; fall back to what the browser reported.
    duration = float(result["duration"]) if result.get("duration") else client_duration
    public_id = result.get("public_id")
    if duration and duration > max_seconds:
        _discard_asset(public_id, result)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=MESSAGES["too_long"].format(minutes=max_seconds // 60)
        )

    attempt = SpeakingAttempt(
        user_id=user.id,
        lesson_id=lesson_id,
        audio_url=result["secure_url"],
        reference_text=reference_text,
        provider=settings.speech_provider,
        analysis_status="processing",
        public_id=public_id,
        duration_seconds=duration,
    )
    try:
        db.add(attempt)
        db.commit()
        db.refresh(attempt)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not save practice attempt")
        _discard_asset(public_id, result)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="We couldn't save your recording. Please try again.")

    # Submitting a recording is a qualifying activity: it marks today as an active
    # learning day for THIS user (several submissions on one day still count once).
    record_activity(db, user_id=user.id, activity_type=ActivityType.PRACTICE, attempt_id=attempt.id)

    background_tasks.add_task(run_analysis, attempt.id)
    return _summary(attempt)


def _discard_asset(public_id: str | None, result: dict) -> None:
    """Best-effort removal of an uploaded recording we decided not to keep."""
    if not public_id:
        return
    try:
        destroy_on_cloudinary(public_id, resource_type=result.get("resource_type") or "video")
    except HTTPException:
        logger.warning("Could not remove discarded recording %s from Cloudinary", public_id)


@router.get("/attempts", response_model=AttemptList)
def list_attempts(
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The signed-in user's practice history, newest first."""
    base = db.query(SpeakingAttempt).filter(SpeakingAttempt.user_id == user.id)
    total = base.with_entities(func.count(SpeakingAttempt.id)).scalar() or 0
    rows = base.order_by(SpeakingAttempt.created_at.desc(), SpeakingAttempt.id.desc()).offset(offset).limit(limit).all()
    items = []
    for index, row in enumerate(rows):
        expire_if_stale(db, row)
        items.append(_summary(row, number=total - offset - index))
    return AttemptList(total=total, items=items)


@router.get("/attempts/{attempt_id}", response_model=AttemptDetail)
def get_attempt(
    attempt_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Status while analysing; transcript, scores and feedback once completed."""
    return _detail(db, _own_attempt_or_404(db, attempt_id, user))


@router.post("/attempts/{attempt_id}/retry", response_model=AttemptSummary, status_code=status.HTTP_202_ACCEPTED)
def retry_attempt(
    attempt_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Re-run analysis of a failed attempt using the recording already stored (no re-upload)."""
    attempt = _own_attempt_or_404(db, attempt_id, user)
    if attempt.analysis_status != "failed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This recording is already being analysed or has finished.")
    _guard_concurrency(db, user)
    attempt.analysis_status = "processing"
    attempt.error_message = None
    db.commit()
    background_tasks.add_task(run_analysis, attempt.id)
    return _summary(attempt)
