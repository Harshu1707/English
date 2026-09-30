# Gemini -> Groq Whisper + free AI analysis

Scope: only the practice-recording pipeline (transcription + language analysis). No frontend, database,
migration, auth, admin, Cloudinary or route/response-schema changes.

## Removed
- `backend/app/services/gemini_service.py` (Gemini language analysis).
- The Gemini audio transcription provider in `speech_analysis.py` (`GeminiSpeechAnalysisService`, the
  `google.genai` calls, thinking/AFC workarounds, Gemini mime-type handling).
- `google-genai` from `requirements.txt`; `google.genai` error mapping in `analysis_errors.py`.
- `GEMINI_API_KEY` and `GEMINI_MODEL` settings / env vars. No other code referenced them.

## Added
- **Groq Whisper speech-to-text** (`GroqSpeechAnalysisService` in `speech_analysis.py`), model
  `whisper-large-v3-turbo` (`GROQ_STT_MODEL`). Reuses the existing flow: the recording is still fetched from
  Cloudinary as MP3, so no ffmpeg or frontend change is needed. Requests `verbose_json` with word timestamps;
  language forced to English. Detects silence via Whisper's own `no_speech_prob`.
- **Free AI analysis** (`services/ai_analysis_service.py`): an open-weight model through an OpenAI-compatible
  chat API. Default is `openai/gpt-oss-120b` on Groq's free tier (same `GROQ_API_KEY`). Switchable to Hugging Face
  or any compatible server (e.g. local Ollama) with env vars. The model is never hard-coded beyond that default:
  Groq retired the Llama 3.x models on 2026-08-16, so change `AI_ANALYSIS_MODEL` if a model disappears.
  Same British-English prompt and same `AIAnalysis` schema as before; one retry on invalid JSON; suggestions that
  quote words not in the transcript are dropped rather than shown.
- `from_http_status()` in `analysis_errors.py` (401/403/404 -> "not set up", 413, 429, 5xx, timeouts).
- **Fluency** is now computed in the pipeline from measured long pauses (>= 1 s between words) and filler words.

## Files
- Modified: `backend/app/services/speech_analysis.py`, `analysis_pipeline.py`, `analysis_errors.py`,
  `backend/app/routers/practice.py` (assessment notes only), `backend/app/core/config.py`,
  `backend/requirements.txt`, `backend/.env.example`, `README.md`, `backend/tests/conftest.py`,
  `tests/test_practice.py`, `tests/test_admin.py` (one comment).
- Created: `backend/app/services/ai_analysis_service.py`, this file.
- Deleted: `backend/app/services/gemini_service.py`.

## Dependencies
Removed `google-genai`. Nothing added (`httpx` was already required; Groq is called over its REST API).

## Environment variables
| Variable | Purpose |
| --- | --- |
| `SPEECH_PROVIDER=groq` | **Must change** from `gemini`; any other value disables analysis (and logs why) |
| `GROQ_API_KEY` | Groq key (server-side only) |
| `GROQ_STT_MODEL` | Optional, default `whisper-large-v3-turbo` |
| `AI_ANALYSIS_PROVIDER` | `groq` (default) / `huggingface` / `openai_compatible` |
| `AI_ANALYSIS_MODEL` | Blank = provider default; required for `huggingface` / `openai_compatible` |
| `HF_TOKEN` | Hugging Face provider |
| `AI_ANALYSIS_BASE_URL`, `AI_ANALYSIS_API_KEY` | `openai_compatible` provider (key optional for local servers) |

Delete `GEMINI_API_KEY` / `GEMINI_MODEL` from your `.env`.

## Tests performed
- Existing suite: 69 passed before changes; **94 pass after** (with `google-genai` uninstalled).
- New tests cover: exact Groq request (URL, auth, model, verbose_json, language, sniffed filename), response
  parsing, pause detection, silence handling, every error mapping (401/403/404/400/413/429/5xx/timeout/network),
  no key leakage, AI request shape, model configurability, Hugging Face / OpenAI-compatible providers, JSON
  retry, hallucinated-suggestion filtering, and a full upload -> Whisper -> analysis -> DB -> read-back run
  through the real service code.
- Backend boots with uvicorn; all `/practice/*` routes present and unchanged.

## Limitations (please read)
- **Not tested against live Groq**: the build sandbox blocks `api.groq.com` and had no API key. All Groq calls
  were exercised against a faked HTTP transport that checks the request format. Do one real recording first.
- **Pronunciation is not measured.** It is returned as `null` (the UI shows "-") and excluded from the overall
  score. A transcript cannot show how words sound; a dedicated pronunciation-assessment service is needed.
- Fluency is a heuristic from Whisper's word timings; Whisper also tends to drop "um"/"uh", so filler counts
  and fluency can look better than the speech was.
- Free-tier limits apply (Groq Whisper about 20 requests/min, 25 MB per file). Rate limits show as "service is busy".
- Old attempts made with Gemini keep their stored data and their original "assessed by Gemini" note.
