# Verba — English Speaking Practice

A premium, responsive British-English speaking practice platform for teachers. Verba pairs lesson media, transcripts, comprehension and an in-browser recording studio with a deliberately separated AI architecture: a speech provider (Groq Whisper) owns the transcript and word timings, while an open-weight AI model provides language interpretation and next-step guidance.

## Included in this foundation

- **Responsive Next.js product UI**: landing page, teacher dashboard, lesson library/player, recording studio, progress page and admin overview.
- **Accessible interaction foundations**: semantic controls, labelled inputs, visible controls, responsive bottom navigation and transcript-first lesson design.
- **FastAPI service foundation** with Pydantic contracts, CORS configuration and REST route placeholders.
- **PostgreSQL / SQLAlchemy relational model** covering users, lessons/media/transcripts/notes, vocabulary, comprehension, attempts, objective scores, AI feedback, practice words, progress and notifications.
- **Alembic initial migration** and environment configuration.
- **Safe AI boundaries**: Groq and AI-model keys are server-only and structured responses are validated; pronunciation is reported as not measured rather than invented.
- **PWA manifest** and app icon.

## Architecture

```
frontend/             Next.js App Router UI
backend/app/          FastAPI application
  core/               settings and security configuration
  database/           SQLAlchemy session and declarative base
  models/             normalized relational schema
  schemas/            API/AI validation contracts
  services/           Groq Whisper, AI analysis and provider interfaces
backend/alembic/      schema migration environment
```

## Local development

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
cd backend
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

The API documentation is available at `http://localhost:8000/docs`.

## PostgreSQL and migrations

Create a PostgreSQL database and set `DATABASE_URL` in `.env`. Apply the initial schema with `alembic upgrade head`. During development, after changing SQLAlchemy models, generate a reviewed revision with:

```bash
cd backend
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Environment variables

Copy `.env.example` to `.env`. `JWT_SECRET` must be a long random secret in production. Configure `GROQ_API_KEY` (and, if you use them, `HF_TOKEN` / `AI_ANALYSIS_API_KEY`) only on the backend. Set `SPEECH_PROVIDER=groq` to enable speech analysis; any other value uses the unconfigured adapter, which fails safely instead of inventing scores.

## AI and speech setup

`AIAnalysisService` (`services/ai_analysis_service.py`) submits structured reference text, teacher transcript, speech signals and lesson difficulty to an OpenAI-compatible chat endpoint (Groq by default; Hugging Face or any other compatible server via `AI_ANALYSIS_PROVIDER`), then validates the JSON response against `AIAnalysis`. The `SpeechAnalysisService` protocol accepts `en-GB` by default. Implement a provider behind that protocol to supply transcription, timing, pronunciation and intonation signals. The language model must not be used to manufacture those measurements.

## Production notes

Use managed PostgreSQL and object storage for media; store URLs and metadata in `lesson_media` / `speaking_attempts`, never media blobs in the database. Configure restrictive CORS origins, a managed secret store and HTTPS. Add a production authentication repository/JWT dependency before exposing auth routes.


## Authentication and speaking analysis

**Auth.** `POST /auth/register`, `POST /auth/login` and `GET /auth/me` issue and verify a JWT (bcrypt password hashes, 24 h expiry). Roles are `teacher` and `admin`; registering as admin needs `ADMIN_INVITE_CODE` from `.env` (leave it empty to disable admin sign-up). The frontend stores the token in `localStorage` (`verba_token`), sends it as a Bearer header, and `SiteShell` redirects signed-out visitors to `/login`. Sign-out is client-side because the JWT is stateless.

**Practice analysis.** Recording (or upload) -> `POST /practice/attempts` -> Cloudinary (`verba/recordings`) -> background task -> transcript -> AI language analysis -> `speaking_attempts` / `speech_scores` / `speech_feedback`. The UI polls `GET /practice/attempts/{id}`; history is `GET /practice/attempts`; a failed attempt can be re-run with `POST /practice/attempts/{id}/retry` (no re-upload).

Set `SPEECH_PROVIDER=groq` and `GROQ_API_KEY` to enable it. What each part really is:

| Part | Source |
| --- | --- |
| Transcript | Groq Whisper speech-to-text (`GROQ_STT_MODEL`, default `whisper-large-v3-turbo`); Whisper can drop some fillers |
| Pronunciation | **Not measured** (shown as "—"): a transcript can't show how words sound. Needs a dedicated pronunciation-assessment provider |
| Fluency score | Computed from long pauses (Whisper word timestamps) and filler words; a guide, and the UI says so |
| Words per minute, pace score, filler counts | Computed here from the transcript and recording length |
| Grammar, vocabulary, sentence structure | An open-weight AI model (`AI_ANALYSIS_MODEL`, default `openai/gpt-oss-120b` on Groq), from the transcript, judged against British English |
| Overall score | Mean of the category scores that were actually measured |

For real phoneme-level en-GB scoring, implement another `SpeechAnalysisService` (see `services/speech_analysis.py`) and select it with `SPEECH_PROVIDER`.

**Settings are read from `.env` in the directory you start the backend from** (`backend/` in the steps above), so put your `.env` there.

**Tests.** `cd backend && pip install -r requirements-dev.txt && python -m pytest tests` (SQLite by default; set `TEST_DATABASE_URL` to use MySQL). Cloudinary, Groq and the AI model are faked.


## Admin content-completion tracking

Admins can see which teachers have completed which videos and podcasts.

**Where.** Sign in as an admin: the sidebar (and mobile bar) now has **Admin** and **Content Progress**. The existing `/admin` dashboard has a new *Content completion* section with the headline numbers, and `/admin/content-progress` has the full view: summary cards, a teacher table (videos / podcasts / total completed / last activity), and a filterable video/podcast table (by type, status, lesson and teacher name/email) with a per-lesson *Completed / Not completed* split.

**What counts.** A content item is a lesson whose `lesson_type` is `video`, `podcast` or `audio` (if it is something else, its uploaded media decides). Only `teacher` accounts are counted. A teacher has completed an item only if their `user_lesson_progress` row says so; no row means "Not Completed". Nothing is invented: a completion that predates completion dates shows **Date not recorded**.

**How completion is recorded** (one row per teacher per lesson, enforced by the existing unique constraint, so no duplicates):

| Path | Rule |
| --- | --- |
| "Mark as complete" (existing button, `POST /progress/activity` with `lesson_id`) | Completed at once; `completed_at` is stamped the first time only. |
| `POST /progress/lessons/{lesson_id}` with `{"percent": 0-100}` (for a real video/audio player) | Progress only moves forward; the first report at or above `COMPLETION_THRESHOLD_PERCENT` (default 90) completes the lesson permanently and counts as a learning day. |

In the frontend, `progressApi.reportLessonProgress(lessonId, percent)` calls the second endpoint. The teacher lesson pages are currently static prototypes without a real `<video>`/`<audio>` element, so `/lessons/<numeric id>` passes the id to the existing "Mark as complete" button; a real player should call `reportLessonProgress` from its `timeupdate`/`ended` events.

**API (all admin-only; a teacher gets 403).** `GET /admin/content-progress/summary`, `/teachers?search=`, `/content?content_type=`, `/content/{lesson_id}`, `/records?content_type=&status=&lesson_id=&search=&limit=&offset=`.

**Database.** Migration `0006_progress_completed_at` adds one nullable column, `user_lesson_progress.completed_at`, and backfills it only from the teacher's earliest recorded video/podcast activity for the same lesson. Run `cd backend && alembic upgrade head`.

**Setting.** `COMPLETION_THRESHOLD_PERCENT` (default `90`).
