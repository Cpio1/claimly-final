"""Validated Storage adapter settings. Process-wide settings live in app.settings."""

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app.settings import ConfigurationError, Settings

__all__ = ["ConfigurationError", "StorageSettings", "S3Settings", "storage_settings", "s3_settings"]


@dataclass(frozen=True)
class StorageSettings:
    url: str
    secret_key: str = field(repr=False)
    bucket: str = "claimly-documents"

    def __post_init__(self):
        try:
            parsed = urlsplit(self.url)
        except ValueError:
            raise ConfigurationError("SUPABASE_URL must be an HTTPS project origin.") from None
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ConfigurationError("SUPABASE_URL must be an HTTPS project origin.")
        if not self.secret_key.startswith("sb_secret_") or any(c.isspace() for c in self.secret_key):
            raise ConfigurationError("SUPABASE_SECRET_KEY must be a server-side Supabase secret key.")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", self.bucket):
            raise ConfigurationError("SUPABASE_STORAGE_BUCKET is invalid.")


@dataclass(frozen=True)
class S3Settings:
    endpoint: str
    bucket: str
    region: str = "auto"
    access_key_id: str = field(default="", repr=False)
    secret_access_key: str = field(default="", repr=False)
    addressing_style: str = "virtual"

    def __post_init__(self):
        if self.addressing_style not in ("virtual", "path"):
            raise ConfigurationError("S3_ADDRESSING_STYLE must be virtual or path.")
        parsed = urlsplit(self.endpoint)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ConfigurationError("S3_ENDPOINT must be an HTTPS S3-compatible endpoint.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]", self.bucket):
            raise ConfigurationError("S3_BUCKET is invalid.")
        if not self.access_key_id or not self.secret_access_key:
            raise ConfigurationError("S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY are required.")


def storage_settings(settings: Settings) -> StorageSettings:
    return StorageSettings(settings.supabase_url, settings.supabase_secret_key, settings.supabase_bucket)


def s3_settings(settings: Settings) -> S3Settings:
    return S3Settings(settings.s3_endpoint, settings.s3_bucket, settings.s3_region,
                      settings.s3_access_key_id, settings.s3_secret_access_key, settings.s3_addressing_style)
