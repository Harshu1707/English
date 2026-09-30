"""Provider boundary. No scores are produced until a real speech provider is configured."""
import logging
import math
import re
from typing import Protocol
from app.schemas.contracts import PronunciationIssue, SpeechSignals

logger = logging.getLogger("verba.analysis")
class SpeechAnalysisService(Protocol):
    async def analyse(self, *, audio_url:str, reference_text:str, locale:str="en-GB") -> SpeechSignals: ...
class UnconfiguredSpeechAnalysisService:
    async def analyse(self, *, audio_url:str, reference_text:str, locale:str="en-GB") -> SpeechSignals:
        raise RuntimeError("Speech analysis is not configured. Connect a provider before requesting pronunciation measurements.")


# ---------------------------------------------------------------------------
# Groq Whisper provider (SPEECH_PROVIDER=groq)
# ---------------------------------------------------------------------------
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.services.analysis_errors import AnalysisError, from_http_status
from app.services.media_service import sniff_audio_container

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_MAX_AUDIO_BYTES = 24 * 1024 * 1024  # Groq's free tier accepts files up to 25 MB
LONG_PAUSE_SECONDS = 1.0  # a gap this long between two words counts as a hesitation
_NO_SPEECH_PROB = 0.8  # Whisper's own "this segment is silence/noise" probability

# Groq works out the audio format from the file name, so it must match the real container.
_MIME_BY_EXT = {
    "mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg",
    "webm": "audio/webm", "mp4": "audio/mp4", "flac": "audio/flac",
}
_EXT_BY_CONTENT_TYPE = {
    "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
    "audio/ogg": "ogg", "audio/webm": "webm", "audio/mp4": "mp4", "audio/m4a": "mp4",
    "audio/x-m4a": "mp4", "audio/flac": "flac",
}


def _audio_format(audio: bytes, content_type: str | None) -> tuple[str, str]:
    """(file extension, mime type) for the downloaded audio: sniffed from its bytes first (headers and
    file names are client-controlled), then the Content-Type, then MP3 (what Cloudinary is asked for)."""
    ext = sniff_audio_container(audio[:32])
    if ext is None:
        ext = _EXT_BY_CONTENT_TYPE.get((content_type or "").split(";", 1)[0].strip().lower(), "mp3")
    return ext, _MIME_BY_EXT[ext]


async def _download_audio(url: str) -> tuple[bytes, str | None]:
    """Fetch a stored recording. Only our own Cloudinary URLs are ever fetched (no SSRF via stored URLs).

    Returns (audio_bytes, content_type) so the caller can send the format the audio was actually
    delivered in, instead of assuming a fixed one.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not (host == "cloudinary.com" or host.endswith(".cloudinary.com")):
        raise AnalysisError("download_failed")
    data = bytearray()
    content_type = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=False) as client:
        async with client.stream("GET", url) as response:
            content_type = response.headers.get("content-type")
            if response.status_code == 400:
                logger.warning("Cloudinary could not deliver audio as mp3 (status 400) for %s", host)
                raise AnalysisError("invalid_audio")  # Cloudinary couldn't decode/transcode the file
            if response.status_code != 200:
                logger.warning("Recording download failed: status=%s host=%s", response.status_code, host)
                raise AnalysisError("download_failed")
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > _MAX_AUDIO_BYTES:
                    raise AnalysisError("too_large")
    logger.info("Downloaded recording for analysis: bytes=%d content_type=%s", len(data), content_type)
    if not data:
        raise AnalysisError("invalid_audio")
    return bytes(data), content_type


_WORD_TOKEN_RE = re.compile(r"[a-z0-9']+")
_MIN_ISSUE_WORD_LEN = 3  # skip flagging very short words (a, to, is...) as pronunciation issues


def _tokenize(text: str) -> list[str]:
    return _WORD_TOKEN_RE.findall((text or "").lower())


def _segment_confidence(segments: list) -> float | None:
    """0-100 acoustic-confidence score from Whisper's own per-segment metrics: avg_logprob (how
    likely the model thought its own transcription was) and no_speech_prob (how much of the segment
    it judged to be silence/noise rather than clear speech). Weighted by segment duration so long,
    confidently-heard segments count for more than short, uncertain ones. This is Whisper's read on
    how clearly the audio was articulated -- not a phoneme-level score, but a real, audio-derived signal."""
    weighted_sum = 0.0
    total_weight = 0.0
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        logprob = seg.get("avg_logprob")
        no_speech = seg.get("no_speech_prob") or 0.0
        if not isinstance(logprob, (int, float)):
            continue
        start, end = seg.get("start"), seg.get("end")
        duration = (end - start) if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start else 1.0
        # exp(avg_logprob) turns a log-probability back into a 0-1 confidence; no_speech discounts it further.
        clarity = max(0.0, min(1.0, math.exp(logprob))) * max(0.0, 1.0 - no_speech)
        weighted_sum += clarity * duration
        total_weight += duration
    if total_weight <= 0:
        return None
    return round((weighted_sum / total_weight) * 100.0, 1)


def _lexical_pronunciation(transcript: str, reference_text: str) -> tuple[float | None, list[PronunciationIssue]]:
    """How much of the reference script's wording actually came through in what Whisper heard.
    A word that isn't recognised in roughly the position it was scripted is either mispronounced
    badly enough to be misheard, or skipped/garbled -- both are pronunciation-relevant. Returns a
    0-100 match score plus the specific reference words that didn't come through, as candidate
    trouble spots for the speaker to review."""
    ref_words = _tokenize(reference_text)
    said_words = set(_tokenize(transcript))
    if not ref_words:
        return None, []
    matched = sum(1 for w in ref_words if w in said_words)
    score = round((matched / len(ref_words)) * 100.0, 1)
    missed_seen: set[str] = set()
    issues: list[PronunciationIssue] = []
    for w in ref_words:
        if w in said_words or w in missed_seen or len(w) < _MIN_ISSUE_WORD_LEN:
            continue
        missed_seen.add(w)
        issues.append(PronunciationIssue(word=w, note="Not clearly heard in your recording -- check the sound of this word."))
        if len(issues) >= 8:
            break
    return score, issues


def _pause_stats(words: list) -> tuple[int | None, float | None]:
    """(number of long pauses, seconds from first to last word) from Whisper's word timestamps.
    (None, None) when the response carried no usable word timings."""
    timed = [
        (float(w["start"]), float(w["end"]))
        for w in words
        if isinstance(w, dict) and isinstance(w.get("start"), (int, float)) and isinstance(w.get("end"), (int, float))
    ]
    if len(timed) < 2:
        return None, None
    pauses = sum(1 for (_, prev_end), (next_start, _) in zip(timed, timed[1:]) if next_start - prev_end >= LONG_PAUSE_SECONDS)
    return pauses, round(timed[-1][1] - timed[0][0], 2)


class GroqSpeechAnalysisService:
    """Transcription with Groq-hosted Whisper, plus pause timings read from its word timestamps.

    Pronunciation is estimated from two audio-derived Whisper signals: how confidently it recognised
    each segment (avg_logprob / no_speech_prob) and how much of the reference script's wording it
    actually heard back (words it failed to recognise are flagged as pronunciation_issues). This is a
    real, audio-grounded estimate -- not phoneme-level scoring like a dedicated pronunciation-assessment
    service would give. Fluency is derived later by the pipeline from the measured pauses and filler words.
    """

    async def analyse(self, *, audio_url: str, reference_text: str, locale: str = "en-GB") -> SpeechSignals:
        if not settings.groq_api_key:
            raise AnalysisError("not_configured")
        audio, content_type = await _download_audio(audio_url)
        ext, mime_type = _audio_format(audio, content_type)

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
                response = await client.post(
                    GROQ_TRANSCRIPTION_URL,
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                    files={"file": (f"recording.{ext}", audio, mime_type)},
                    data={
                        "model": settings.groq_stt_model,
                        "response_format": "verbose_json",  # segments (confidence) + word timestamps (pauses)
                        "timestamp_granularities[]": ["word", "segment"],
                        "language": "en",  # Verba is English practice; stops accented English being mis-detected
                        "temperature": "0",
                    },
                )
        except httpx.TimeoutException:
            logger.warning("Groq transcription timed out: model=%s audio_bytes=%d", settings.groq_stt_model, len(audio))
            raise AnalysisError("timeout")
        except httpx.TransportError as exc:
            logger.warning("Groq transcription unreachable: %s: %s", type(exc).__name__, str(exc)[:300])
            raise AnalysisError("ai_unavailable")

        if response.status_code != 200:
            logger.warning(
                "Groq transcription failed: status=%s model=%s audio_bytes=%d ext=%s body=%r",
                response.status_code, settings.groq_stt_model, len(audio), ext, response.text[:300],
            )
            if response.status_code in (400, 415, 422):
                raise AnalysisError("invalid_audio")  # Groq couldn't decode the file
            raise from_http_status(response.status_code, fallback="transcription_failed")

        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            logger.warning("Groq transcription returned a non-JSON body: %r", response.text[:200])
            raise AnalysisError("transcription_failed")

        transcript = " ".join(str(payload.get("text") or "").split())
        segments = [s for s in (payload.get("segments") or []) if isinstance(s, dict)]
        logger.info(
            "Groq transcription ok: model=%s audio_bytes=%d ext=%s words=%d segments=%d",
            settings.groq_stt_model, len(audio), ext, len(transcript.split()), len(segments),
        )
        # Whisper "hears" words in silence/noise; its own per-segment probability tells us when that happened.
        if not transcript or (segments and all((s.get("no_speech_prob") or 0) > _NO_SPEECH_PROB for s in segments)):
            raise AnalysisError("no_speech")

        long_pauses, speech_seconds = _pause_stats(payload.get("words") or [])

        acoustic_confidence = _segment_confidence(segments)
        lexical_score, pronunciation_issues = _lexical_pronunciation(transcript, reference_text)
        # Blend Whisper's own recognition confidence with how much of the script actually came through;
        # fall back to whichever signal is available if the other couldn't be computed.
        if acoustic_confidence is not None and lexical_score is not None:
            pronunciation = round(0.5 * acoustic_confidence + 0.5 * lexical_score, 1)
        else:
            pronunciation = acoustic_confidence if acoustic_confidence is not None else lexical_score

        return SpeechSignals(
            transcript=transcript,
            pronunciation=pronunciation,
            pronunciation_issues=pronunciation_issues,
            provider_data={
                "provider": "groq_whisper",
                "model": settings.groq_stt_model,
                "locale": locale,
                "assessment": "groq_whisper",
                "phoneme_level": False,
                "long_pause_count": long_pauses,
                "speech_seconds": speech_seconds,
                "long_pause_seconds": LONG_PAUSE_SECONDS,
                "pronunciation_acoustic_confidence": acoustic_confidence,
                "pronunciation_lexical_match": lexical_score,
            },
        )


def get_speech_service() -> SpeechAnalysisService:
    """Select the provider named by SPEECH_PROVIDER; anything else stays on the safe unconfigured adapter."""
    if settings.speech_provider == "groq":
        return GroqSpeechAnalysisService()
    if settings.speech_provider not in ("", "unconfigured"):
        logger.error("SPEECH_PROVIDER=%r is not supported; set SPEECH_PROVIDER=groq. Speech analysis is disabled.", settings.speech_provider)
    return UnconfiguredSpeechAnalysisService()
