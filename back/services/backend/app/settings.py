"""Server-only configuration for the merged product Backend, worker and maintenance.

No value here may be exposed through NEXT_PUBLIC_* frontend variables. Opening or importing the
app never connects to a database, Storage, or model endpoint.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parents[2]
ENV_FILE = BACKEND_DIR / ".env"

STORAGE_BACKENDS = ("supabase", "s3", "local")
REVIEW_MODES = ("operator", "user_confirmation")


class ConfigurationError(RuntimeError):
    """Required server configuration is missing or invalid."""


def _bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


def _int(name: str, default: int, low: int, high: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        raise ConfigurationError(f"{name} must be an integer.") from None
    if not low <= value <= high:
        raise ConfigurationError(f"{name} must be between {low} and {high}.")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default="", repr=False)
    local_dev: bool = False
    storage_backend: str = "supabase"
    local_storage_dir: str = str(BACKEND_DIR / ".data" / "originals")
    supabase_url: str = ""
    supabase_secret_key: str = field(default="", repr=False)
    supabase_bucket: str = "claimly-documents"
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_region: str = "auto"
    s3_access_key_id: str = field(default="", repr=False)
    s3_secret_access_key: str = field(default="", repr=False)
    s3_addressing_style: str = "virtual"
    llm_base_url: str = "http://127.0.0.1:8001"
    llm_service_token: str = field(default="", repr=False)
    scheduler_secret: str = field(default="", repr=False)
    frontend_origins: tuple[str, ...] = ("http://localhost:3000",)
    session_hours: int = 168
    session_creations_per_hour: int = 20
    lease_seconds: int = 1200
    max_attempts: int = 3
    source_review_mode: str = "operator"
    contracts_dir: str = str(REPO_ROOT / "Claimly_Three_Parts" / "contracts")
    max_entries_per_session: int = 100
    max_documents_per_session: int = 50
    max_session_bytes: int = 200 * 1024 * 1024
    max_files_per_entry: int = 5

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(ENV_FILE, override=False)
        origins = tuple(o.strip().rstrip("/") for o in os.environ.get("FRONTEND_ORIGINS", "http://localhost:3000").split(",") if o.strip())
        return cls(
            database_url=os.environ.get("DATABASE_URL", "").strip(),
            local_dev=_bool("LOCAL_DEV"),
            storage_backend=os.environ.get("STORAGE_BACKEND", "supabase").strip().lower(),
            local_storage_dir=os.environ.get("LOCAL_STORAGE_DIR", str(BACKEND_DIR / ".data" / "originals")),
            supabase_url=os.environ.get("SUPABASE_URL", "").strip(),
            supabase_secret_key=os.environ.get("SUPABASE_SECRET_KEY", "").strip(),
            supabase_bucket=os.environ.get("SUPABASE_STORAGE_BUCKET", "claimly-documents").strip(),
            s3_endpoint=os.environ.get("S3_ENDPOINT", "").strip(),
            s3_bucket=os.environ.get("S3_BUCKET", "").strip(),
            s3_region=os.environ.get("S3_REGION", "auto").strip() or "auto",
            s3_access_key_id=os.environ.get("S3_ACCESS_KEY_ID", "").strip(),
            s3_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY", "").strip(),
            s3_addressing_style=os.environ.get("S3_ADDRESSING_STYLE", "virtual").strip().lower() or "virtual",
            llm_base_url=os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8001").strip(),
            llm_service_token=os.environ.get("LLM_SERVICE_TOKEN", "").strip(),
            scheduler_secret=os.environ.get("SCHEDULER_SECRET", "").strip(),
            frontend_origins=origins,
            session_hours=_int("DEMO_SESSION_TTL_HOURS", 168, 1, 24 * 30),
            session_creations_per_hour=_int("DEMO_SESSIONS_PER_IP_PER_HOUR", 20, 1, 1000),
            lease_seconds=_int("JOB_LEASE_SECONDS", 1200, 30, 7200),
            max_attempts=_int("JOB_MAX_ATTEMPTS", 3, 1, 10),
            source_review_mode=os.environ.get("SOURCE_REVIEW_MODE", "operator").strip().lower(),
            contracts_dir=os.environ.get("CLAIMLY_CONTRACTS_DIR", str(REPO_ROOT / "Claimly_Three_Parts" / "contracts")),
        ).checked()

    def checked(self) -> "Settings":
        if self.storage_backend not in STORAGE_BACKENDS:
            raise ConfigurationError("STORAGE_BACKEND must be supabase, s3 or local.")
        if self.source_review_mode not in REVIEW_MODES:
            raise ConfigurationError("SOURCE_REVIEW_MODE must be operator or user_confirmation.")
        if self.storage_backend == "local" and not self.local_dev:
            raise ConfigurationError("STORAGE_BACKEND=local requires explicit LOCAL_DEV=true.")
        if self.database_url.startswith("sqlite:///") and not self.local_dev:
            raise ConfigurationError("SQLite DATABASE_URL requires explicit LOCAL_DEV=true.")
        for origin in self.frontend_origins:
            if origin == "*" or not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(:\d+)?", origin):
                raise ConfigurationError("FRONTEND_ORIGINS must list exact http(s) origins, without wildcards or paths.")
        return self

    @property
    def postgres(self) -> bool:
        return self.database_url.startswith(("postgresql://", "postgres://"))

    @property
    def email_configured(self) -> bool:
        # No email provider adapter is implemented; never claim delivery capability.
        return False
