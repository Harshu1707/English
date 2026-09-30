"""Practice-recording analysis pipeline.

    stored recording (Cloudinary URL)
        -> speech service:   transcript + word timings (Groq Whisper)          (SpeechAnalysisService)
        -> computed metrics: words per minute, pace, fillers, fluency           (deterministic, below)
        -> AIAnalysisService: grammar / vocabulary / sentence-structure feedback (language only, open model)
        -> speech_scores + speech_feedback rows, attempt marked completed

The sources are kept separate on purpose (see README): the transcript comes from the speech provider,
pace, fillers and fluency are computed here from measured data, and the AI model only interprets the
language. Pronunciation comes from the speech provider too -- for Groq Whisper it is estimated from
transcription confidence and script-word recognition, not phoneme-level scoring.
"""
import asyncio
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.models import Lesson, SpeakingAttempt, SpeechFeedback, SpeechScore
from app.schemas.contracts import AIAnalysis, FillerWord, SpeechSignals
from app.services.ai_analysis_service import AIAnalysisService, analysis_model_name
from app.services.analysis_errors import AnalysisError, from_exception, logger
from app.services.media_service import analysis_audio_url
from app.services.speech_analysis import get_speech_service

ACTIVE_STATUSES = ("pending", "processing", "transcribing", "analyzing")
# If the server restarts mid-analysis nothing would ever finish the attempt; treat it as failed.
STALE_AFTER = timedelta(minutes=10)
MIN_WORDS = 8  # fewer than this and there's nothing meaningful to analyse
MIN_SECONDS_FOR_WPM = 3.0

# --------------------------------------------------------------------------------------
# Deterministic metrics
# --------------------------------------------------------------------------------------
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['\u2019-][A-Za-z0-9]+)*")

# Comfortable conversational pace band for a learner giving a spoken response (heuristic).
IDEAL_WPM = (120, 160)

_FILLERS = [
    ("um", r"\bum+\b"),
    ("uh", r"\buh+\b"),
    ("er / erm", r"\b(?:er|erm)\b"),
    ("hmm", r"\bhmm+\b"),
    ("you know", r"\byou know\b"),
    ("I mean", r"\bi mean\b"),
    ("basically", r"\bbasically\b"),
    ("actually", r"\bactually\b"),
    ("literally", r"\bliterally\b"),
    ("sort of", r"\bsort of\b"),
    ("kind of", r"\bkind of\b"),
    # "like" is only counted as a filler when it's set off by a comma ("it was, like, huge"),
    # otherwise ordinary uses ("I like tea") would be flagged.
    ("like", r",\s*like\b|\blike\s*,"),
]


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


# --------------------------------------------------------------------------------------
# Script matching: did the user attempt the reference script, or something unrelated?
# One normalized-similarity check, gated by the single SCRIPT_MATCH_THRESHOLD setting.
# --------------------------------------------------------------------------------------
_CONTRACTIONS = {
    "i'm": "i am", "you're": "you are", "he's": "he is", "she's": "she is", "it's": "it is",
    "we're": "we are", "they're": "they are", "i've": "i have", "you've": "you have",
    "we've": "we have", "they've": "they have", "i'll": "i will", "you'll": "you will",
    "he'll": "he will", "she'll": "she will", "we'll": "we will", "they'll": "they will",
    "i'd": "i would", "you'd": "you would", "he'd": "he would", "she'd": "she would",
    "we'd": "we would", "they'd": "they would", "isn't": "is not", "aren't": "are not",
    "wasn't": "was not", "weren't": "were not", "don't": "do not", "doesn't": "does not",
    "didn't": "did not", "can't": "cannot", "couldn't": "could not", "shouldn't": "should not",
    "wouldn't": "would not", "won't": "will not", "let's": "let us", "that's": "that is",
    "what's": "what is",
}


def _normalize_for_match(text: str) -> str:
    text = (text or "").lower().replace("\u2019", "'").replace("\u2018", "'")
    words = re.findall(r"[a-z0-9']+", text)
    expanded: list[str] = []
    for w in words:
        expanded.extend(_CONTRACTIONS.get(w, w).split())
    return " ".join(expanded)


def script_match_ratio(transcript: str, reference_text: str) -> float:
    """Normalized similarity (0-1) between what was said and the reference script. Tolerant of
    STT-level differences (case, punctuation, contractions); low for genuinely unrelated speech."""
    a, b = _normalize_for_match(transcript), _normalize_for_match(reference_text)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def words_per_minute(word_count: int, duration_seconds: float | None) -> float | None:
    if not duration_seconds or duration_seconds < MIN_SECONDS_FOR_WPM:
        return None
    return round(word_count / (duration_seconds / 60.0), 1)


def pace_score(wpm: float | None) -> float | None:
    """100 inside the ideal band, losing 1.25 points per wpm outside it."""
    if wpm is None:
        return None
    low, high = IDEAL_WPM
    gap = low - wpm if wpm < low else wpm - high if wpm > high else 0
    return round(max(0.0, 100.0 - gap * 1.25), 1)


def count_fillers(transcript: str) -> list[FillerWord]:
    text = (transcript or "").lower()
    found = [(label, len(re.findall(pattern, text))) for label, pattern in _FILLERS]
    return [FillerWord(word=label, count=n) for label, n in sorted(found, key=lambda x: -x[1]) if n > 0]


def fluency_score(long_pauses: int | None, speech_seconds: float | None, filler_count: int, word_count: int) -> float | None:
    """Heuristic from measured data: 100 minus 10 points per long pause per minute (max 50) and 4 points per
    filler per 100 words (max 40). None when the provider gave no word timings or the speech was too short."""
    if long_pauses is None or not speech_seconds or speech_seconds < MIN_SECONDS_FOR_WPM or word_count <= 0:
        return None
    pause_penalty = min(50.0, long_pauses / (speech_seconds / 60.0) * 10.0)
    filler_penalty = min(40.0, filler_count / word_count * 100.0 * 4.0)
    return round(max(0.0, 100.0 - pause_penalty - filler_penalty), 1)


def overall_score(*scores: float | None) -> float | None:
    """Mean of the category scores that were actually measured (missing ones are left out, not zeroed)."""
    present = [s for s in scores if s is not None]
    return round(sum(present) / len(present), 1) if present else None


# --------------------------------------------------------------------------------------
# State handling
# --------------------------------------------------------------------------------------
def _set_status(db: Session, attempt: SpeakingAttempt, status: str) -> None:
    attempt.analysis_status = status
    db.commit()


def _fail(db: Session, attempt: SpeakingAttempt, error: AnalysisError) -> None:
    db.rollback()
    attempt.analysis_status = "failed"
    attempt.error_message = error.message[:500]
    db.commit()


def expire_if_stale(db: Session, attempt: SpeakingAttempt) -> None:
    if attempt.analysis_status in ACTIVE_STATUSES and datetime.utcnow() - attempt.updated_at > STALE_AFTER:
        _fail(db, attempt, AnalysisError("timeout"))


# --------------------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------------------
def _run(db: Session, attempt: SpeakingAttempt) -> None:
    duration = attempt.duration_seconds
    if duration and duration > settings.max_recording_seconds:
        raise AnalysisError("too_long", minutes=settings.max_recording_seconds // 60)

    # 1. Transcription (+ word timings) ------------------------------------------------
    _set_status(db, attempt, "transcribing")
    audio_url = analysis_audio_url(attempt.public_id) if attempt.public_id else attempt.audio_url
    try:
        signals: SpeechSignals = asyncio.run(
            get_speech_service().analyse(audio_url=audio_url, reference_text=attempt.reference_text, locale="en-GB")
        )
    except Exception as exc:
        raise from_exception(exc, stage="transcription") from exc

    transcript = (signals.transcript or "").strip()
    words = count_words(transcript)
    if words < MIN_WORDS:
        raise AnalysisError("too_short")

    # 1b. Script matching: reject attempts that aren't the reference script -----------
    if script_match_ratio(transcript, attempt.reference_text) < settings.script_match_threshold:
        raise AnalysisError("not_matched")

    # 2. Computed metrics --------------------------------------------------------------
    wpm = words_per_minute(words, duration)
    signals.words_per_minute = wpm
    signals.pace = pace_score(wpm)
    signals.duration_seconds = duration
    signals.filler_words = count_fillers(transcript)
    if signals.fluency is None:  # Whisper reports no fluency; derive it from the measured pauses and fillers
        signals.fluency = fluency_score(
            signals.provider_data.get("long_pause_count"),
            signals.provider_data.get("speech_seconds"),
            sum(f.count for f in signals.filler_words),
            words,
        )

    # 3. Language analysis (open model via AIAnalysisService) --------------------------
    _set_status(db, attempt, "analyzing")
    difficulty = "intermediate"
    if attempt.lesson_id:
        lesson = db.get(Lesson, attempt.lesson_id)
        difficulty = str(getattr(lesson, "difficulty", None) or difficulty)
    try:
        analysis: AIAnalysis = asyncio.run(
            AIAnalysisService().speaking_feedback(
                reference_text=attempt.reference_text,
                teacher_transcript=transcript,
                speech=signals,
                difficulty=difficulty,
            )
        )
    except Exception as exc:
        raise from_exception(exc, stage="analysis") from exc

    # 4. Persist -----------------------------------------------------------------------
    db.query(SpeechScore).filter(SpeechScore.attempt_id == attempt.id).delete()
    db.query(SpeechFeedback).filter(SpeechFeedback.attempt_id == attempt.id).delete()
    raw = dict(signals.provider_data)
    raw["filler_words"] = [f.model_dump() for f in signals.filler_words]
    raw["pronunciation_issues"] = [i.model_dump() for i in signals.pronunciation_issues]
    db.add(
        SpeechScore(
            attempt_id=attempt.id,
            pronunciation=signals.pronunciation,
            fluency=signals.fluency,
            words_per_minute=wpm,
            pace=signals.pace,
            raw_provider_data=raw,
        )
    )
    db.add(
        SpeechFeedback(
            attempt_id=attempt.id,
            grammar_score=analysis.grammar_score,
            vocabulary_score=analysis.vocabulary_score,
            sentence_structure_score=analysis.sentence_structure_score,
            feedback=analysis.model_dump(mode="json"),
            model=analysis_model_name(),
        )
    )
    attempt.transcript = transcript
    attempt.provider = str(raw.get("provider") or settings.speech_provider)
    attempt.overall_score = overall_score(
        signals.pronunciation,
        signals.fluency,
        analysis.grammar_score,
        analysis.vocabulary_score,
        analysis.sentence_structure_score,
        signals.pace,
    )
    attempt.analysis_status = "completed"
    attempt.error_message = None
    db.commit()


def run_analysis(attempt_id: int) -> None:
    """Background entry point (FastAPI BackgroundTasks runs sync callables in a worker thread).
    Uses its own DB session: the request's session is closed once the response is sent."""
    db = SessionLocal()
    try:
        attempt = db.get(SpeakingAttempt, attempt_id)
        if attempt is None:
            return
        try:
            _run(db, attempt)
        except Exception as exc:
            error = from_exception(exc)
            if error.code == "unexpected":
                logger.exception("Analysis of attempt %s failed unexpectedly", attempt_id)
            else:
                logger.warning("Analysis of attempt %s failed (%s): %r", attempt_id, error.code, exc)
            _fail(db, attempt, error)
    finally:
        db.close()
