from __future__ import annotations

import os
from typing import Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """TrustDesk Application Configuration Settings.

    Loads configuration from environment variables and local .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Database
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/trustdesk",
        description="SQLAlchemy PostgreSQL connection URL",
    )
    database_url_test: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/trustdesk_test",
        description="SQLAlchemy PostgreSQL test database connection URL",
    )

    # Server-validated demo token for internal support-agent MVP demo
    trustdesk_demo_token: str = Field(
        default="demo_secret_token_123",
        description="Demo bearer token configured on the server",
    )

    # Server binding
    app_host: str = Field(default="0.0.0.0", description="FastAPI host binding")
    app_port: int = Field(default=8000, description="FastAPI port binding")

    # AI Provider Settings
    ai_provider: Literal["mock", "live"] = Field(
        default="mock",
        description="Active AI provider adapter ('mock' or 'live')",
    )
    gemini_api_key: str | None = Field(
        default=None,
        description="Google Gemini API key for production LLM calls",
    )
    gemini_model: str = Field(
        default="gemini-3.8-flash",
        description="Configured Gemini model identifier",
    )

    @field_validator("database_url", "database_url_test")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v or not (v.startswith("postgresql://") or v.startswith("postgresql+psycopg://") or v.startswith("sqlite://")):
            raise ValueError(f"Invalid database URL: must use postgresql or sqlite protocol, got '{v}'")
        return v

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: str) -> str:
        if isinstance(v, str):
            v_upper = v.upper()
            if v_upper not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
                raise ValueError(f"Invalid log_level: {v}. Must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL.")
            return v_upper
        return v


settings = Settings()

