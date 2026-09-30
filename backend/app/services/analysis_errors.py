"""One place that turns any failure in the upload -> transcribe -> analyse chain into a
user-safe message. Raw provider/SDK errors are logged server-side and never sent to the browser."""
import asyncio
import json
import logging

logger = logging.getLogger("verba.analysis")

MESSAGES = {
    "invalid_audio": "We couldn't read that audio. Please record again, or upload a WAV, MP3, M4A, OGG or WebM file.",
    "too_short": "We couldn't pick up enough speech to analyse. Try recording again for at least ten seconds.",
    "no_speech": "We couldn't hear any speech in that recording. Please check your microphone and try again.",
    "too_long": "Recordings can be up to {minutes} minutes long. Please record a shorter response.",
    "too_large": "That recording is too large to analyse. Please try a shorter recording.",
    "transcription_failed": "We couldn't transcribe your recording. Please try again.",
    "ai_failed": "We couldn't complete the language analysis. Please try again in a moment.",
    "ai_unavailable": "The analysis service is temporarily unavailable. Please try again shortly.",
    "timeout": "The analysis took too long. Please try again.",
    "rate_limited": "The analysis service is busy right now. Please wait a minute and try again.",
    "not_configured": "Speech analysis isn't set up on this server yet. Your recording has been saved.",
    "not_matched": "Not matched. Please try again.",
    "download_failed": "We couldn't retrieve your recording for analysis. Please try again.",
    "unexpected": "Something went wrong while analysing your recording. Please try again.",
}
# Retrying can't help these until something outside the user's control changes.
NOT_RETRYABLE = {"not_configured", "not_matched"}  # re-analysing the same audio won't change the match result


class AnalysisError(Exception):
    def __init__(self, code: str, message: str | None = None, **fmt):
        self.code = code
        self.message = (message or MESSAGES.get(code, MESSAGES["unexpected"])).format(**fmt)
        self.retryable = code not in NOT_RETRYABLE
        super().__init__(f"{code}: {self.message}")


def from_http_status(status: int, *, fallback: str) -> AnalysisError:
    """Map an HTTP error status from Groq / the analysis provider to a user-safe AnalysisError."""
    if status in (401, 403, 404):  # bad or missing API key, or the configured model isn't available
        return AnalysisError("not_configured")
    if status == 413:
        return AnalysisError("too_large")
    if status == 429:
        return AnalysisError("rate_limited")
    if status in (408, 504):
        return AnalysisError("timeout")
    if status >= 500:
        return AnalysisError("ai_unavailable")
    return AnalysisError(fallback)


def from_exception(exc: BaseException, *, stage: str = "analysis") -> AnalysisError:
    """Map an arbitrary exception to an AnalysisError. `stage` is 'transcription' or 'analysis'."""
    if isinstance(exc, AnalysisError):
        return exc
    fallback = "transcription_failed" if stage == "transcription" else "ai_failed"

    try:
        import httpx
    except ImportError:  # pragma: no cover
        httpx = None

    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or (httpx and isinstance(exc, httpx.TimeoutException)):
        return AnalysisError("timeout")
    if httpx and isinstance(exc, httpx.HTTPError):
        # Downloading the stored recording is the only unguarded HTTP call in the transcription stage;
        # provider calls map their own failures (see from_http_status), so anything left is the download.
        return AnalysisError("download_failed" if stage == "transcription" else "ai_unavailable")
    if isinstance(exc, RuntimeError) and "not configured" in str(exc).lower():
        return AnalysisError("not_configured")
    if isinstance(exc, (json.JSONDecodeError, ValueError)):  # includes pydantic.ValidationError
        return AnalysisError(fallback)
    return AnalysisError("unexpected")
