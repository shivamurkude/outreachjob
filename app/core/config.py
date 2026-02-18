from functools import lru_cache
from typing import Any, List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_CORS = ["http://localhost:3000", "http://localhost:5173"]


def _parse_cors_origins(v: Any) -> List[str]:
    try:
        if v is None or v == "":
            return _DEFAULT_CORS.copy()
        if isinstance(v, list):
            return [x for x in v if isinstance(x, str) and x.strip()]
        s = str(v).strip()
        if not s:
            return _DEFAULT_CORS.copy()
        if s.startswith("["):
            import json
            out = json.loads(s)
            return [x for x in out if isinstance(x, str) and x.strip()] or _DEFAULT_CORS.copy()
        return [x.strip() for x in s.split(",") if x.strip()] or _DEFAULT_CORS.copy()
    except Exception:
        return _DEFAULT_CORS.copy()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    env: str = Field(default="development", description="ENV")
    debug: bool = Field(default=False, description="DEBUG")
    secret_key: str = Field(default="change-me-in-production-min-32-chars")

    # MongoDB
    mongodb_uri: str = Field(default="mongodb://localhost:27017", alias="MONGODB_URI")
    mongodb_db_name: str = Field(default="findmyjob", alias="MONGODB_DB_NAME")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # Google OAuth
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    gmail_oauth_redirect_uri: str = Field(
        default="http://localhost:8000/v1/gmail/oauth/callback",
        alias="GMAIL_OAUTH_REDIRECT_URI",
    )

    # Token encryption (Fernet key, base64)
    token_encryption_key: str = Field(default="", alias="TOKEN_ENCRYPTION_KEY")

    # Razorpay
    razorpay_key_id: str = Field(default="", alias="RAZORPAY_KEY_ID")
    razorpay_key_secret: str = Field(default="", alias="RAZORPAY_KEY_SECRET")
    razorpay_webhook_secret: str = Field(default="", alias="RAZORPAY_WEBHOOK_SECRET")

    # OpenAI
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # Storage
    storage_backend: str = Field(default="local", alias="STORAGE_BACKEND")
    storage_local_path: str = Field(default="./uploads", alias="STORAGE_LOCAL_PATH")
    gcs_bucket_name: str | None = Field(default=None, alias="GCS_BUCKET_NAME")

    # Sentry
    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")

    # CORS: env as string, exposed as list
    cors_origins_raw: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        alias="CORS_ORIGINS",
        description="Comma-separated or JSON list",
    )

    @property
    def cors_origins(self) -> List[str]:
        return _parse_cors_origins(getattr(self, "cors_origins_raw", None))

    # Pricing (credits)
    credits_per_send: int = 5
    credits_per_verify: int = 1
    credits_per_resume_scan: int = 20
    free_resume_scans_per_month: int = 3

    # Gmail sending
    gmail_daily_cap: int = 250


@lru_cache
def get_settings() -> Settings:
    return Settings()
