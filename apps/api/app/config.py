"""Application configuration loaded from environment variables."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://fiscaudit:fiscaudit@postgres:5432/fiscaudit"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # MinIO / object storage
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "fiscaudit"
    minio_secret_key: str = "fiscaudit"
    minio_bucket: str = "fiscaudit-files"
    minio_secure: bool = False

    # JWT
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 240

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Anthropic (Claude Vision pour OCR factures)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-7"

    # MailerSend (emails transactionnels : onboarding client, invitations)
    mailersend_api_key: str = ""
    mail_from_email: str = "no-reply@verifiscale.com"
    mail_from_name: str = "VerifiScale"
    mail_reply_to: str = ""
    app_base_url: str = "https://verifiscale.com"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
