"""Runtime settings. Secrets come only from the environment / .env — never hard-coded."""
from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> str:
    """Locate the nearest .env by walking up from this file, so the app loads the
    real secrets file whether launched from the ralph workspace or the project root.
    An explicit DATABASE_URL in the process environment always takes precedence."""
    here = Path(__file__).resolve()
    for parent in [Path.cwd(), *here.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            return str(candidate)
    return ".env"


class Settings(BaseSettings):
    # App / runtime
    app_env: str = "development"
    log_level: str = "info"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Canonical store (Supabase Postgres). System of record.
    database_url: str = ""
    database_pool_size: int = 5
    database_statement_timeout_ms: int = 5000  # 5 s — safe default for remote Supabase; tune via DATABASE_STATEMENT_TIMEOUT_MS env var
    supabase_project_ref: str = ""

    # Integration layer (spec-stv-integration-layer §9). Bearer token for the
    # System A → System B outbox delivery channel. NEVER commit to Git or logs.
    # Set via Railway env var: AIHUB_OUTBOX_TOKEN.
    aihub_outbox_token: str = ""

    # System B (AI Accounting Hub) Supabase public credentials for the dashboard
    # read-only RLS view (spec-stv-integration-layer §6.4, §9).
    # These are anon/public keys — safe to inject as window globals in HTML, but
    # RLS must restrict to SELECT-only on the anon role.  Set via env / Railway.
    # NEVER confuse with System A (ejxrbxoncsgglrqvjulg); System B ref = fdnwlcomuddzmluvbylg.
    supabase_url_aihub: str = ""
    supabase_anon_key_aihub: str = ""

    # Daily digest email (spec-stv-integration-layer-2026-06-29.md §16). SMTP
    # transport for the automated "STV Integration Health" digest sent to Ben.
    # Uses stdlib smtplib — no new dependency. Optional/schedulable feature:
    # deliberately NOT enforced at startup (unlike aihub_outbox_token above);
    # an empty smtp_host / digest_email_to only raises when send_digest_email()
    # is actually invoked. NEVER log smtp_password.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    digest_email_from: str = ""
    digest_email_to: str = ""

    # Tolerate the many unrelated keys in the shared .env.
    model_config = SettingsConfigDict(
        env_file=_find_env_file(), env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    @field_validator("aihub_outbox_token")
    @classmethod
    def token_must_not_be_empty(cls, v: str) -> str:
        """Fail at startup when AIHUB_OUTBOX_TOKEN is missing or empty.

        Skipped in test environments (APP_ENV=test) so the unit-test suite
        can run without a real token.  Production and staging always require it.
        """
        import os as _os

        if not v and _os.environ.get("APP_ENV", "development") not in ("test", "testing"):
            raise ValueError(
                "AIHUB_OUTBOX_TOKEN must be set in the environment or .env file. "
                "The integration outbox endpoint is inaccessible without it."
            )
        return v

    @property
    def sqlalchemy_url(self) -> str:
        """Normalize to the psycopg (v3) driver SQLAlchemy expects."""
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


settings = Settings()
