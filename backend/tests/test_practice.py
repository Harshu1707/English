import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
import httpx
from sqlalchemy import text

from app.core.config import settings
from app.database.session import engine
from app.schemas.contracts import AIAnalysis, GrammarError, PronunciationIssue, SpeechSignals, VocabSuggestion
from app.services import analysis_pipeline as pipeline
from app.services.analysis_errors import AnalysisError
from app.services.speech_analysis import GroqSpeechAnalysisService, _download_audio

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 300
TRANSCRIPT = "Um I have went to the market yesterday and I bought some apples for my class you know"  # 18 words
UPLOADS: list = []
DESTROYED: list = []


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    """Fake Cloudinary + speech provider + AI analysis model so nothing touches the network."""
    UPLOADS.clear(); DESTROYED.clear()
    state = {"upload_error": None, "cloud_duration": 30.0, "speech_error": None, "ai_error": None,
             "transcript": TRANSCRIPT, "pron": None, "fluency": None, "grammar": 84.0}

    async def fake_upload(file, *, resource_type, folder):
        if state["upload_error"]:
            raise state["upload_error"]
        await file.read()
        UPLOADS.append((resource_type, folder))
        n = len(UPLOADS)
        return {"secure_url": f"https://res.cloudinary.com/demo/video/upload/v1/verba/recordings/r{n}.webm",
                "public_id": f"verba/recordings/r{n}", "resource_type": "video", "duration": state["cloud_duration"]}

    class FakeSpeech:
        async def analyse(self, *, audio_url, reference_text, locale="en-GB"):
            assert audio_url.startswith("https://res.cloudinary.com/") and locale == "en-GB"
            if state["speech_error"]:
                raise state["speech_error"]
            # Shaped like the Groq Whisper provider: no pronunciation or fluency of its own, but word timings.
            return SpeechSignals(transcript=state["transcript"], pronunciation=state["pron"], fluency=state["fluency"],
                                 provider_data={"provider": "groq_whisper", "assessment": "groq_whisper", "phoneme_level": False,
                                                "long_pause_count": 1, "speech_seconds": 30.0})

    class FakeAI:
        async def speaking_feedback(self, *, reference_text, teacher_transcript, speech, difficulty):
            assert teacher_transcript == state["transcript"].strip() and speech.words_per_minute is not None
            if state["ai_error"]:
                raise state["ai_error"]
            return AIAnalysis(grammar_score=state["grammar"], vocabulary_score=79, sentence_structure_score=81,
                              feedback="Good effort.", strengths=["Clear ideas"], areas_to_improve=["Reduce fillers"],
                              grammar_errors=[GrammarError(original="I have went", correction="I have gone", category="tense")],
                              vocabulary_suggestions=[VocabSuggestion(word="bought", suggestion="purchased")])

    monkeypatch.setattr("app.routers.practice.upload_to_cloudinary", fake_upload)
    monkeypatch.setattr("app.routers.practice.destroy_on_cloudinary", lambda pid, resource_type: DESTROYED.append(pid))
    monkeypatch.setattr(pipeline, "get_speech_service", lambda: FakeSpeech())
    monkeypatch.setattr(pipeline, "AIAnalysisService", FakeAI)
    monkeypatch.setattr(pipeline, "analysis_audio_url", lambda pid: f"https://res.cloudinary.com/demo/video/upload/{pid}.mp3")
    return state


def upload(client, headers, *, name="recording.webm", data=WEBM, **form):
    form = {"reference_text": "Good morning everyone.", **form}
    return client.post("/practice/attempts", headers=headers, files={"file": (name, data, "audio/webm")}, data=form)


def test_upload_analyse_store_and_read_back(client, teacher):
    res = upload(client, teacher, duration_seconds="30")
    assert res.status_code == 202 and res.json()["status"] == "processing"
    assert UPLOADS == [("video", "verba/recordings")]

    detail = client.get(f"/practice/attempts/{res.json()['id']}", headers=teacher).json()
    assert detail["status"] == "completed" and detail["transcript"] == TRANSCRIPT
    s = detail["scores"]
    # words_per_minute is computed (18 words in 30s = 36 wpm), the overall is the mean of what was measured.
    assert detail["words_per_minute"] == 36.0
    assert s["pace"] == 0.0  # 36 wpm is far below the ideal band
    # Whisper cannot judge pronunciation, so it is reported as not measured (None), never invented.
    fluency = pipeline.fluency_score(1, 30.0, 2, 18)  # 1 long pause in 30 s, 2 fillers in 18 words
    assert fluency == 40.0
    assert (s["pronunciation"], s["fluency"], s["grammar"], s["vocabulary"], s["sentence_structure"]) == (None, fluency, 84, 79, 81)
    assert s["overall"] == round((fluency + 84 + 79 + 81 + 0) / 5, 1)  # the mean of what was measured only
    assert detail["grammar_errors"][0] == {"original": "I have went", "correction": "I have gone", "explanation": "", "category": "tense"}
    assert {f["word"]: f["count"] for f in detail["filler_words"]} == {"um": 1, "you know": 1}
    assert detail["pronunciation_issues"] == []
    assert "Not measured" in detail["assessment"]["pronunciation"] and "Whisper" in detail["assessment"]["transcription"]
    assert "Gemini" not in str(detail["assessment"])
    assert detail["created_at"].endswith("Z")
    # survives a "refresh": a second GET returns the stored result without re-analysis
    assert client.get(f"/practice/attempts/{detail['id']}", headers=teacher).json()["scores"] == s


def test_scores_come_from_the_analysis_not_hardcoded(client, teacher, fakes):
    fakes.update(pron=50.0, fluency=60.0, grammar=70.0, transcript=" ".join(["word"] * 60))  # 60 words / 30 s = 120 wpm
    detail = client.get(f"/practice/attempts/{upload(client, teacher).json()['id']}", headers=teacher).json()
    assert detail["words_per_minute"] == 120.0 and detail["scores"]["pace"] == 100.0
    assert detail["scores"]["overall"] == round((50 + 60 + 70 + 79 + 81 + 100) / 6, 1)


def test_all_practice_routes_require_login(client, teacher):
    for method, url in [("post", "/practice/attempts"), ("get", "/practice/attempts"), ("get", "/practice/attempts/1"), ("post", "/practice/attempts/1/retry")]:
        assert getattr(client, method)(url).status_code == 401, url


def test_users_only_see_their_own_attempts(client, teacher, other_teacher):
    attempt_id = upload(client, teacher).json()["id"]
    assert client.get(f"/practice/attempts/{attempt_id}", headers=other_teacher).status_code == 404
    assert client.post(f"/practice/attempts/{attempt_id}/retry", headers=other_teacher).status_code == 404
    assert client.get("/practice/attempts", headers=other_teacher).json() == {"total": 0, "items": []}


def test_history_is_numbered_newest_first_and_paginated(client, teacher):
    ids = [upload(client, teacher).json()["id"] for _ in range(3)]
    listing = client.get("/practice/attempts", headers=teacher).json()
    assert listing["total"] == 3
    assert [(i["id"], i["number"]) for i in listing["items"]] == [(ids[2], 3), (ids[1], 2), (ids[0], 1)]
    page2 = client.get("/practice/attempts?limit=2&offset=2", headers=teacher).json()
    assert [(i["id"], i["number"]) for i in page2["items"]] == [(ids[0], 1)]
    assert client.get(f"/practice/attempts/{ids[1]}", headers=teacher).json()["number"] == 2


@pytest.mark.parametrize("name,data,expected", [
    ("evil.exe", WEBM, 400),                       # extension not allowed
    ("clip.webm", b"<html>not audio</html>" * 5, 400),  # right extension, wrong contents
    ("noext", WEBM, 400),
])
def test_invalid_audio_rejected_before_upload(client, teacher, name, data, expected):
    assert upload(client, teacher, name=name, data=data).status_code == expected
    assert UPLOADS == []


def test_oversized_file_rejected(client, teacher, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    res = upload(client, teacher, data=WEBM + b"\x00" * (2 * 1024 * 1024))
    assert res.status_code == 413 and UPLOADS == []


def test_too_long_recordings_rejected(client, teacher, fakes):
    assert upload(client, teacher, duration_seconds="400").status_code == 400 and UPLOADS == []
    fakes["cloud_duration"] = 400.0  # browser said nothing, Cloudinary measured 400s
    res = upload(client, teacher)
    assert res.status_code == 400 and "5 minutes" in res.json()["detail"]
    assert DESTROYED == ["verba/recordings/r1"]  # the discarded asset is cleaned up
    assert client.get("/practice/attempts", headers=teacher).json()["total"] == 0


def test_upload_failure_hides_provider_details(client, teacher, fakes):
    fakes["upload_error"] = HTTPException(502, "Upload to Cloudinary failed: Invalid api_key sk_live_SECRET")
    res = upload(client, teacher)
    assert res.status_code == 502 and "SECRET" not in res.text and "Cloudinary" not in res.text
    fakes["upload_error"] = HTTPException(503, "Cloudinary is not configured. Missing environment variable(s): CLOUDINARY_API_KEY")
    res = upload(client, teacher)
    assert res.status_code == 503 and "CLOUDINARY_API_KEY" not in res.text
    assert client.get("/practice/attempts", headers=teacher).json()["total"] == 0


def _failed(client, teacher):
    return client.get(f"/practice/attempts/{upload(client, teacher).json()['id']}", headers=teacher).json()


@pytest.mark.parametrize("key,error,needle", [
    ("speech_error", AnalysisError("no_speech"), "any speech"),
    ("speech_error", AnalysisError("invalid_audio"), "couldn't read that audio"),
    ("speech_error", AnalysisError("too_large"), "too large"),
    ("speech_error", AnalysisError("rate_limited"), "busy right now"),
    ("speech_error", httpx.ConnectError("dns SECRET"), "couldn't retrieve your recording"),
    ("speech_error", asyncio.TimeoutError(), "took too long"),
    ("speech_error", ValueError("bad json SECRET"), "couldn't transcribe"),
    ("ai_error", AnalysisError("ai_unavailable"), "temporarily unavailable"),
    ("ai_error", httpx.ConnectError("dns SECRET"), "temporarily unavailable"),
    ("ai_error", ValueError("not json SECRET"), "language analysis"),
    ("ai_error", RuntimeError("AI analysis is not configured."), "isn't set up"),
    ("ai_error", RuntimeError("mysql://root:hunter2@db SECRET"), "Something went wrong"),
])
def test_failures_become_friendly_messages(client, teacher, fakes, key, error, needle):
    fakes[key] = error
    detail = _failed(client, teacher)
    assert detail["status"] == "failed" and needle in detail["error_message"]
    assert "SECRET" not in detail["error_message"] and "hunter2" not in detail["error_message"]
    assert detail["scores"]["overall"] is None and detail["transcript"] is None


def test_too_little_speech_is_reported_not_scored(client, teacher, fakes):
    fakes["transcript"] = "Hello there"
    detail = _failed(client, teacher)
    assert detail["status"] == "failed" and "enough speech" in detail["error_message"]


def test_unconfigured_speech_provider_fails_safely_and_keeps_recording(client, teacher, monkeypatch):
    monkeypatch.undo()  # real get_speech_service, provider unconfigured
    monkeypatch.setattr(settings, "speech_provider", "unconfigured")
    monkeypatch.setattr("app.routers.practice.upload_to_cloudinary", lambda f, **k: _async({"secure_url": "https://res.cloudinary.com/d/video/upload/v1/x.webm", "public_id": "x", "duration": 20.0, "resource_type": "video"}))
    monkeypatch.setattr(pipeline, "analysis_audio_url", lambda pid: "https://res.cloudinary.com/d/video/upload/x.mp3")
    detail = _failed(client, teacher)
    assert detail["status"] == "failed" and "isn't set up" in detail["error_message"]
    assert detail["audio_url"].startswith("https://res.cloudinary.com/")  # the recording itself is kept


async def _async(value):
    return value


def test_retry_reuses_stored_recording(client, teacher, fakes):
    fakes["speech_error"] = AnalysisError("rate_limited")
    attempt_id = upload(client, teacher).json()["id"]
    assert client.get(f"/practice/attempts/{attempt_id}", headers=teacher).json()["status"] == "failed"
    fakes["speech_error"] = None
    assert client.post(f"/practice/attempts/{attempt_id}/retry", headers=teacher).status_code == 202
    detail = client.get(f"/practice/attempts/{attempt_id}", headers=teacher).json()
    assert detail["status"] == "completed" and detail["error_message"] is None
    assert len(UPLOADS) == 1  # nothing was re-uploaded
    assert client.post(f"/practice/attempts/{attempt_id}/retry", headers=teacher).status_code == 409
    with engine.connect() as c:  # retry replaced, not duplicated, the result rows
        assert c.execute(text("SELECT COUNT(*) FROM speech_scores")).scalar() == 1


def test_stuck_attempts_time_out_instead_of_spinning_forever(client, teacher):
    attempt_id = upload(client, teacher).json()["id"]
    with engine.begin() as c:
        c.execute(text("UPDATE speaking_attempts SET analysis_status='transcribing', updated_at=:t"), {"t": datetime.utcnow() - timedelta(hours=1)})
    detail = client.get(f"/practice/attempts/{attempt_id}", headers=teacher).json()
    assert detail["status"] == "failed" and "took too long" in detail["error_message"]


def test_per_user_limit_on_simultaneous_analyses(client, teacher, other_teacher, monkeypatch):
    monkeypatch.setattr(pipeline, "run_analysis", lambda attempt_id: None)  # leave attempts "processing"
    monkeypatch.setattr("app.routers.practice.run_analysis", lambda attempt_id: None)
    assert upload(client, teacher).status_code == 202 and upload(client, teacher).status_code == 202
    third = upload(client, teacher)
    assert third.status_code == 429
    assert upload(client, other_teacher).status_code == 202  # limit is per user


def test_lesson_must_exist(client, teacher):
    assert upload(client, teacher, lesson_id="999").status_code == 404


# ---- units ---------------------------------------------------------------------------------
def test_metrics():
    assert pipeline.count_words("It's a well-known thing, isn't it?") == 6
    assert pipeline.words_per_minute(60, 30) == 120.0 and pipeline.words_per_minute(60, 2) is None
    assert [pipeline.pace_score(w) for w in (120, 140, 160)] == [100.0] * 3
    assert pipeline.pace_score(80) == 50.0 and pipeline.pace_score(200) == 50.0 and pipeline.pace_score(300) == 0.0
    assert pipeline.overall_score(80, None, 90) == 85.0 and pipeline.overall_score(None) is None
    found = {f.word: f.count for f in pipeline.count_fillers("So, like, it was um fine. I like tea. Uh, actually basically no.")}
    assert found == {"like": 1, "um": 1, "uh": 1, "actually": 1, "basically": 1}


def test_ai_scores_are_clamped():
    assert AIAnalysis(feedback="x", grammar_score=140, vocabulary_score=-5).grammar_score == 100.0
    assert SpeechSignals(pronunciation=float("nan")).pronunciation is None


def test_only_cloudinary_urls_are_downloaded():
    for bad in ["http://res.cloudinary.com/a.mp3", "https://evil.example.com/a.mp3", "https://cloudinary.com.evil.io/a.mp3", "file:///etc/passwd", "https://169.254.169.254/latest"]:
        with pytest.raises(AnalysisError) as exc:
            asyncio.run(_download_audio(bad))
        assert exc.value.code == "download_failed"


def test_audio_format_is_sniffed_then_falls_back_to_content_type():
    from app.services.speech_analysis import _audio_format

    assert _audio_format(b"RIFF\x00\x00\x00\x00WAVEfmt ", "application/octet-stream") == ("wav", "audio/wav")
    assert _audio_format(b"\x00" * 40, "audio/ogg; codecs=opus") == ("ogg", "audio/ogg")  # unsniffable -> header
    assert _audio_format(b"\x00" * 40, None) == ("mp3", "audio/mpeg")  # nothing known -> what Cloudinary delivers


# ---- Groq Whisper (speech-to-text) -----------------------------------------------------------
MP3 = b"ID3" + b"\x00" * 300


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _mock_httpx(monkeypatch, handler):
    """Route every httpx.AsyncClient in the process through `handler` (no real network)."""

    class Patched(_REAL_ASYNC_CLIENT):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)


def _transcribe(monkeypatch, handler, *, audio=MP3, content_type="audio/mpeg; charset=binary"):
    import app.services.speech_analysis as sa

    async def fake_download(url):
        return audio, content_type

    monkeypatch.setattr(sa, "_download_audio", fake_download)
    _mock_httpx(monkeypatch, handler)
    return asyncio.run(GroqSpeechAnalysisService().analyse(audio_url="https://res.cloudinary.com/x.mp3", reference_text="hi"))


WHISPER_OK = {
    "text": " hello there everyone  and welcome ",
    "segments": [{"no_speech_prob": 0.01, "avg_logprob": -0.2}],
    "words": [{"word": "hello", "start": 0.0, "end": 0.4}, {"word": "there", "start": 0.5, "end": 0.9},
              {"word": "everyone", "start": 2.6, "end": 3.2}, {"word": "and", "start": 3.3, "end": 3.5},
              {"word": "welcome", "start": 3.6, "end": 4.2}],
}


def test_groq_whisper_request_and_response_parsing(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], request.content
        return httpx.Response(200, json=WHISPER_OK)

    out = _transcribe(monkeypatch, handler)
    assert seen["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert seen["auth"] == "Bearer test-key"
    body = seen["body"]
    for needle in (b'name="model"\r\n\r\nwhisper-large-v3-turbo', b'verbose_json', b'name="language"\r\n\r\nen',
                   b'name="timestamp_granularities[]"\r\n\r\nword', b'filename="recording.mp3"', b"Content-Type: audio/mpeg"):
        assert needle in body, needle
    assert out.transcript == "hello there everyone and welcome"  # whitespace normalised, not rewritten
    assert out.pronunciation is None and out.fluency is None  # Whisper measures neither
    pd = out.provider_data
    assert (pd["provider"], pd["assessment"], pd["model"]) == ("groq_whisper", "groq_whisper", "whisper-large-v3-turbo")
    assert pd["long_pause_count"] == 1 and pd["speech_seconds"] == 4.2  # the 1.7 s gap before "everyone"


def test_groq_whisper_sends_the_real_container_format(monkeypatch):
    seen = {}

    def handler(request):
        seen["body"] = request.content
        return httpx.Response(200, json=WHISPER_OK)

    _transcribe(monkeypatch, handler, audio=b"\x1a\x45\xdf\xa3" + b"\x00" * 100, content_type="application/octet-stream")
    assert b'filename="recording.webm"' in seen["body"]  # sniffed from the bytes, not trusted from the header


@pytest.mark.parametrize("status,code", [
    (401, "not_configured"), (403, "not_configured"), (404, "not_configured"), (400, "invalid_audio"),
    (413, "too_large"), (429, "rate_limited"), (503, "ai_unavailable"), (504, "timeout"), (418, "transcription_failed"),
])
def test_groq_whisper_http_errors_map_to_friendly_codes(monkeypatch, status, code):
    with pytest.raises(AnalysisError) as exc:
        _transcribe(monkeypatch, lambda request: httpx.Response(status, json={"error": {"message": "key gsk_SECRET"}}))
    assert exc.value.code == code and "SECRET" not in exc.value.message


def test_groq_whisper_timeouts_and_network_errors(monkeypatch):
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def down(request):
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(AnalysisError) as exc:
        _transcribe(monkeypatch, timeout)
    assert exc.value.code == "timeout"
    with pytest.raises(AnalysisError) as exc:
        _transcribe(monkeypatch, down)
    assert exc.value.code == "ai_unavailable"


@pytest.mark.parametrize("payload", [
    {"text": "", "segments": []},
    {"text": "Thank you.", "segments": [{"no_speech_prob": 0.97}, {"no_speech_prob": 0.9}]},  # Whisper hearing silence
])
def test_groq_whisper_silence_is_no_speech(monkeypatch, payload):
    with pytest.raises(AnalysisError) as exc:
        _transcribe(monkeypatch, lambda request: httpx.Response(200, json=payload))
    assert exc.value.code == "no_speech"


def test_groq_whisper_garbage_response_is_a_transcription_failure(monkeypatch):
    with pytest.raises(AnalysisError) as exc:
        _transcribe(monkeypatch, lambda request: httpx.Response(200, text="<html>oops</html>"))
    assert exc.value.code == "transcription_failed"


def test_groq_whisper_needs_an_api_key(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", None)
    with pytest.raises(AnalysisError) as exc:
        _transcribe(monkeypatch, lambda request: httpx.Response(200, json=WHISPER_OK))
    assert exc.value.code == "not_configured"


def test_unsupported_speech_provider_is_refused_not_silently_used(monkeypatch):
    from app.services.speech_analysis import UnconfiguredSpeechAnalysisService, get_speech_service

    monkeypatch.setattr(settings, "speech_provider", "gemini")  # a stale .env
    assert isinstance(get_speech_service(), UnconfiguredSpeechAnalysisService)
    monkeypatch.setattr(settings, "speech_provider", "groq")
    assert isinstance(get_speech_service(), GroqSpeechAnalysisService)


def test_fluency_is_computed_from_measured_pauses_and_fillers():
    assert pipeline.fluency_score(0, 60.0, 0, 100) == 100.0
    assert pipeline.fluency_score(3, 60.0, 0, 100) == 70.0  # 3 long pauses per minute
    assert pipeline.fluency_score(0, 60.0, 5, 100) == 80.0  # 5 fillers per 100 words
    assert pipeline.fluency_score(20, 60.0, 50, 100) == 10.0  # penalties are capped (50 + 40)
    assert pipeline.fluency_score(None, None, 2, 50) is None  # no word timings -> not measured, not guessed
    assert pipeline.fluency_score(1, 2.0, 0, 10) is None  # too little speech


# ---- AI language analysis (open model) ---------------------------------------------------------
AI_TRANSCRIPT = "yesterday I have went to the market and I bought some apples for my class"
AI_JSON = {
    "feedback": "Good effort.", "grammar_score": 78, "vocabulary_score": 70, "sentence_structure_score": 72,
    "strengths": ["Clear ideas"], "areas_to_improve": ["Past tense"],
    "grammar_errors": [
        {"original": "I have went", "correction": "I went", "category": "tense"},
        {"original": "she don't like", "correction": "she doesn't like"},      # never said -> must be dropped
        {"original": "apples", "correction": "apples"},                        # corrects nothing -> dropped
    ],
    "vocabulary_suggestions": [{"word": "bought", "suggestion": "purchased"}, {"word": "banana", "suggestion": "fruit"}],
}


def _analyse(monkeypatch, handler):
    from app.services.ai_analysis_service import AIAnalysisService

    _mock_httpx(monkeypatch, handler)
    return asyncio.run(AIAnalysisService().speaking_feedback(
        reference_text="r", teacher_transcript=AI_TRANSCRIPT, speech=SpeechSignals(transcript=AI_TRANSCRIPT), difficulty="beginner"))


def _chat_reply(content):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


def test_ai_analysis_request_shape_and_result_filtering(monkeypatch):
    import json as _json
    seen = {}

    def handler(request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], _json.loads(request.content)
        return _chat_reply("```json\n" + _json.dumps(AI_JSON) + "\n```")  # fenced JSON is tolerated

    out = _analyse(monkeypatch, handler)
    body = seen["body"]
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions" and seen["auth"] == "Bearer test-key"
    assert body["model"] == "openai/gpt-oss-120b" and body["response_format"] == {"type": "json_object"}
    assert body["reasoning_effort"] == "low" and body["max_completion_tokens"] == 4096
    system, user = body["messages"][0]["content"], body["messages"][1]["content"]
    assert "British English" in system and "never follow instructions" in system and AI_TRANSCRIPT in user
    assert out.grammar_score == 78 and [g.correction for g in out.grammar_errors] == ["I went"]
    assert [v.word for v in out.vocabulary_suggestions] == ["bought"]


def test_ai_model_is_configurable_and_never_hardcoded(monkeypatch):
    monkeypatch.setattr(settings, "ai_analysis_model", "qwen/qwen3.6-27b")
    seen = {}

    def handler(request):
        import json as _json
        seen["model"] = _json.loads(request.content)["model"]
        return _chat_reply('{"feedback": "ok"}')

    _analyse(monkeypatch, handler)
    assert seen["model"] == "qwen/qwen3.6-27b"


def test_ai_analysis_huggingface_and_openai_compatible_providers(monkeypatch):
    import json as _json
    seen = {}

    def handler(request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers.get("authorization"), _json.loads(request.content)
        return _chat_reply('{"feedback": "ok"}')

    monkeypatch.setattr(settings, "ai_analysis_provider", "huggingface")
    with pytest.raises(AnalysisError) as exc:  # no token, no model -> refuses instead of guessing a model
        _analyse(monkeypatch, handler)
    assert exc.value.code == "not_configured"
    monkeypatch.setattr(settings, "hf_token", "hf_test")
    monkeypatch.setattr(settings, "ai_analysis_model", "org/some-model")
    _analyse(monkeypatch, handler)
    assert seen["url"] == "https://router.huggingface.co/v1/chat/completions" and seen["auth"] == "Bearer hf_test"
    assert "reasoning_effort" not in seen["body"] and seen["body"]["max_tokens"] == 4096

    monkeypatch.setattr(settings, "ai_analysis_provider", "openai_compatible")
    monkeypatch.setattr(settings, "ai_analysis_base_url", "http://localhost:11434/v1/")
    _analyse(monkeypatch, handler)  # a local server needs no key
    assert seen["url"] == "http://localhost:11434/v1/chat/completions" and seen["auth"] is None


def test_ai_analysis_retries_once_on_invalid_json_then_gives_up(monkeypatch):
    calls = []

    def flaky(request):
        calls.append(1)
        return _chat_reply("Sure! Here is my analysis: not json") if len(calls) == 1 else _chat_reply('{"feedback": "ok"}')

    assert _analyse(monkeypatch, flaky).feedback == "ok" and len(calls) == 2

    calls.clear()
    with pytest.raises(ValueError):  # the pipeline turns this into the friendly "language analysis" message
        _analyse(monkeypatch, lambda request: (calls.append(1), _chat_reply('{"grammar_score": "high"}'))[1])
    assert len(calls) == 2


def test_ai_analysis_http_errors_map_to_friendly_codes(monkeypatch):
    for status, code in [(401, "not_configured"), (404, "not_configured"), (429, "rate_limited"), (500, "ai_unavailable"), (422, "ai_failed")]:
        with pytest.raises(AnalysisError) as exc:
            _analyse(monkeypatch, lambda request, s=status: httpx.Response(s, json={"error": "SECRET"}))
        assert exc.value.code == code and "SECRET" not in exc.value.message


def test_full_pipeline_runs_the_real_groq_and_ai_services(client, teacher, monkeypatch):
    """Upload -> Cloudinary download -> Groq Whisper -> AI analysis -> stored -> read back, with only the HTTP
    transport faked (the real service code, request building, parsing and persistence all run)."""
    import json as _json
    from app.services.ai_analysis_service import AIAnalysisService
    from app.services.speech_analysis import get_speech_service

    monkeypatch.setattr(pipeline, "get_speech_service", get_speech_service)  # undo the autouse fakes
    monkeypatch.setattr(pipeline, "AIAnalysisService", AIAnalysisService)
    hits = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        hits.append(url.split("?")[0])
        if request.url.host.endswith("cloudinary.com"):
            return httpx.Response(200, content=MP3, headers={"content-type": "audio/mpeg"})
        if url.endswith("/audio/transcriptions"):
            return httpx.Response(200, json={
                "text": " " + AI_TRANSCRIPT + " um you know ",
                "segments": [{"no_speech_prob": 0.02}],
                "words": [{"word": "yesterday", "start": 0.0, "end": 0.6}, {"word": "I", "start": 0.7, "end": 0.8},
                          {"word": "class", "start": 24.0, "end": 24.5}],
            })
        if url.endswith("/chat/completions"):
            assert _json.loads(request.content)["messages"][1]["content"].count(AI_TRANSCRIPT) >= 1
            return _chat_reply(_json.dumps(AI_JSON))
        raise AssertionError(f"unexpected request {url}")

    _mock_httpx(monkeypatch, handler)
    detail = client.get(f"/practice/attempts/{upload(client, teacher, duration_seconds='30').json()['id']}", headers=teacher).json()

    assert [h.split("/")[-1] for h in hits if "cloudinary" not in h] == ["transcriptions", "completions"]
    assert detail["status"] == "completed" and detail["error_message"] is None
    assert detail["transcript"] == AI_TRANSCRIPT + " um you know"
    sc = detail["scores"]
    assert sc["pronunciation"] is None  # not measured, not invented
    assert sc["grammar"] == 78 and sc["vocabulary"] == 70 and sc["sentence_structure"] == 72
    assert sc["fluency"] is not None and sc["overall"] is not None  # fluency comes from 1 long pause + 2 fillers
    assert [g["correction"] for g in detail["grammar_errors"]] == ["I went"]  # invented errors filtered out
    assert {f["word"] for f in detail["filler_words"]} == {"um", "you know"}
    assert "openai/gpt-oss-120b" in detail["assessment"]["language"]
    with engine.connect() as c:  # the result rows are really persisted, tagged with the model that produced them
        assert c.execute(text("SELECT model FROM speech_feedback")).scalar() == "openai/gpt-oss-120b"
        assert c.execute(text("SELECT provider FROM speaking_attempts")).scalar() == "groq_whisper"


def test_legacy_gemini_attempts_still_read_back_truthfully(client, teacher):
    """Rows written before the Groq switch carry assessment='ai_estimate' and must keep their honest description."""
    attempt_id = upload(client, teacher).json()["id"]
    with engine.begin() as c:
        c.execute(text("UPDATE speech_scores SET raw_provider_data = :d"), {"d": '{"provider": "gemini_audio", "assessment": "ai_estimate"}'})
    detail = client.get(f"/practice/attempts/{attempt_id}", headers=teacher).json()
    assert detail["status"] == "completed" and "Gemini" in detail["assessment"]["transcription"]


def test_submitting_a_recording_marks_today_as_an_active_day(client, teacher, other_teacher):
    """A practice submission is a qualifying activity for the submitting user only."""
    from app.services import activity_service

    assert client.get("/progress/summary", headers=teacher).json()["current_streak"] == 0
    upload(client, teacher)
    upload(client, teacher)  # a second recording the same day must not add a second active day

    body = client.get("/progress/summary", headers=teacher).json()
    assert body["practice_activities"] == 2
    assert body["current_streak"] == 1 and body["active_days"] == 1
    assert client.get("/progress/calendar", headers=teacher).json()["active_days"] == [
        activity_service.today_local().day
    ]
    # Teacher B is unaffected.
    assert client.get("/progress/summary", headers=other_teacher).json()["current_streak"] == 0
