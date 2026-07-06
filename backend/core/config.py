"""Application configuration loaded from environment variables / .env file."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Central configuration for the Resume Builder backend."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ResuMate AI"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # --- LLM providers (pluggable) ---
    llm_provider: str = Field(default="auto", description="auto | openai | anthropic | gemini | none")
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    llm_timeout_seconds: float = 90.0
    llm_max_retries: int = 2

    # --- Storage ---
    mongodb_url: str = ""
    mongodb_db_name: str = "resume_builder"
    sqlite_path: str = str(PROJECT_DIR / "database" / "resume_builder.db")

    # --- Directories ---
    templates_dir: str = str(BACKEND_DIR / "templates")
    builtin_templates_dir: str = str(BACKEND_DIR / "templates" / "builtin")
    downloaded_templates_dir: str = str(BACKEND_DIR / "templates" / "downloaded")
    uploaded_templates_dir: str = str(BACKEND_DIR / "templates" / "uploaded")
    generated_dir: str = str(BACKEND_DIR / "generated")
    uploads_dir: str = str(BACKEND_DIR / "generated" / "uploads")

    # --- Limits ---
    max_upload_mb: int = 15
    allowed_resume_extensions: tuple[str, ...] = (".pdf", ".docx", ".png", ".jpg", ".jpeg")
    allowed_template_extensions: tuple[str, ...] = (".pdf", ".docx", ".png", ".jpg", ".jpeg")

    # --- Job search connectors (all optional; keyless sources always work) ---
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    rapidapi_key: str = ""          # enables JSearch (Google-for-Jobs: LinkedIn/Indeed/Naukri listings)
    jooble_api_key: str = ""
    jobs_default_country: str = "in"  # Adzuna country code (in, us, gb, ...)
    jobs_timeout_seconds: float = 20.0
    jobs_cache_hours: float = 20.0        # day-level result cache (protects free API quotas)
    jsearch_monthly_budget: int = 180     # hard cap on JSearch calls per calendar month
    job_alerts_hour: int = 9              # earliest local hour alerts may run each day

    # --- SMTP (optional; enables sending application emails directly) ---
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""          # defaults to smtp_user when empty
    smtp_use_tls: bool = True

    # --- Template search ---
    template_search_interval_minutes: int = 1440  # daily
    template_search_enabled: bool = True

    def ensure_directories(self) -> None:
        for d in (
            self.templates_dir,
            self.builtin_templates_dir,
            self.downloaded_templates_dir,
            self.uploaded_templates_dir,
            self.generated_dir,
            self.uploads_dir,
            str(Path(self.sqlite_path).parent),
        ):
            Path(d).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings


def reset_settings_cache() -> None:
    """Used by tests to re-read environment variables."""
    get_settings.cache_clear()
    os.environ.setdefault("RESUME_BUILDER_TESTING", "0")
