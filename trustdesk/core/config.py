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
    ai_provider: Literal["mock", "live", "openrouter"] = Field(
        default="mock",
        description="Active AI provider adapter ('mock', 'live', or 'openrouter')",
    )
    gemini_api_key: str | None = Field(
        default=None,
        description="Google Gemini API key for production LLM calls",
    )
    gemini_model: str = Field(
        default="gemini-3.8-flash",
        description="Configured Gemini model identifier",
    )

    # OpenRouter / OpenAI Compatible Settings
    openrouter_api_key: str | None = Field(
        default=None,
        description="OpenRouter API key for live LLM operations",
    )
    openai_api_key: str | None = Field(
        default=None,
        description="Fallback standard OpenAI API key variable if used for OpenRouter",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL",
    )
    openai_base_url: str | None = Field(
        default=None,
        description="Optional base URL override matching standard OpenAI SDK convention",
    )
    openrouter_model: str = Field(
        default="openai/gpt-5-mini",
        description="Configured OpenRouter model identifier (e.g. openai/gpt-5-mini)",
    )
    openrouter_site_url: str = Field(
        default="http://localhost:8000",
        description="App URL sent in HTTP-Referer header to OpenRouter",
    )
    openrouter_site_name: str = Field(
        default="TrustDesk",
        description="App title sent in X-Title header to OpenRouter",
    )
    openrouter_timeout_seconds: float = Field(
        default=15.0,
        ge=1.0,
        le=60.0,
        description="Timeout for OpenRouter API requests in seconds",
    )
    openrouter_max_retries: int = Field(
        default=1,
        ge=0,
        le=3,
        description="Maximum retry attempts for transient OpenRouter errors",
    )

    @property
    def effective_openrouter_api_key(self) -> str | None:
        """Resolve effective OpenRouter API key from either openrouter_api_key or openai_api_key."""
        return self.openrouter_api_key or self.openai_api_key

    @property
    def effective_openrouter_base_url(self) -> str:
        """Resolve effective OpenRouter base URL from either openai_base_url or openrouter_base_url."""
        return self.openai_base_url or self.openrouter_base_url

    # Redis and RQ Background Worker Settings
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for asynchronous task queue and broker",
    )
    rq_queue_name: str = Field(
        default="default",
        description="Default RQ queue name for background jobs",
    )
    worker_stale_threshold_seconds: int = Field(
        default=60,
        ge=5,
        description="Configurable threshold in seconds to detect orphaned queued jobs",
    )
    worker_heartbeat_timeout_seconds: int = Field(
        default=120,
        ge=10,
        description="Configurable threshold in seconds to detect dead worker heartbeats",
    )

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        if not v or not (v.startswith("redis://") or v.startswith("rediss://")):
            raise ValueError(f"Invalid redis URL: must use redis:// or rediss:// protocol, got '{v}'")
        return v

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

