from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "mysql+pymysql://Harshu:Harshu@localhost:3306/english_coach"
    jwt_secret: str = "development-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24
    cors_origins: str = "http://localhost:3000"
    # Timezone the app counts calendar days in (streaks and the activity calendar).
    app_timezone: str = "Asia/Kolkata"
    # Groq (server-only). Whisper speech-to-text, and the default host for the language analysis model.
    groq_api_key: str | None = None
    groq_stt_model: str = "whisper-large-v3-turbo"
    # Language analysis (grammar / vocabulary / sentence structure): groq | huggingface | openai_compatible.
    ai_analysis_provider: str = "groq"
    # Blank = the provider's default (Groq: openai/gpt-oss-120b). Required for huggingface / openai_compatible.
    ai_analysis_model: str = ""
    hf_token: str | None = None  # huggingface provider
    ai_analysis_base_url: str | None = None  # openai_compatible provider (any OpenAI-style /chat/completions API)
    ai_analysis_api_key: str | None = None  # openai_compatible provider (optional for local servers)
    # A video/podcast counts as completed once a teacher's player reports at least this % (1-100).
    completion_threshold_percent: int = 90
    speech_provider: str = "groq"  # groq = Whisper transcription; anything else disables analysis
    # Minimum normalized similarity (0-1) between transcript and reference script to accept an attempt.
    script_match_threshold: float = 0.70
    storage_provider: str = "local"
    max_upload_size_mb: int = 50
    # Required to self-register as an admin. Unset = admin self-registration is disabled.
    admin_invite_code: str | None = None
    # Longest practice recording accepted for analysis (keeps speech-to-text requests within provider limits).
    max_recording_seconds: int = 300
    # Cloudinary (server-only; never exposed to the client)
    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: str | None = None
    cloudinary_api_secret: str | None = None
settings = Settings()
