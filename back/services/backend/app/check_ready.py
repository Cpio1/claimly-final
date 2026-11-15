"""Read-only deployment readiness check: python -m app.check_ready [--llm].

Prints only booleans/categories; never connection strings, keys, file names or document content.
Exit code 0 only if every selected dependency is ready.
"""

from __future__ import annotations

import argparse

import httpx

from app.db import Database
from app.settings import ConfigurationError, Settings
from app.storage import StorageError, make_storage


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm", action="store_true", help="Also call the internal LLM service /health (no inference)")
    args = parser.parse_args(argv)
    failed = False
    try:
        settings = Settings.from_env()
    except ConfigurationError as error:
        print(f"configuration: invalid ({error})")
        return 1
    print(f"database configured: {bool(settings.database_url)}; postgres: {settings.postgres}")
    try:
        with Database(settings).tx() as c:
            ok = c.execute("SELECT 1 AS ok FROM claimly.schema_migrations WHERE version='0004'").fetchone() is not None
        print(f"migration 0004 applied: {ok}")
        failed |= not ok
    except Exception as error:  # noqa: BLE001
        print(f"database reachable: False ({type(error).__name__})")
        failed = True
    print(f"storage backend: {settings.storage_backend}")
    try:
        make_storage(settings).ensure_private()
        print("storage private bucket check: passed")
    except StorageError as error:
        print(f"storage private bucket check: failed category={error.category} http_status={error.http_status}")
        failed = True
    except ConfigurationError as error:
        print(f"storage configuration: invalid ({error})")
        failed = True
    print(f"source review mode: {settings.source_review_mode}; frontend origins: {len(settings.frontend_origins)}")
    print(f"LLM service token configured: {bool(settings.llm_service_token)}; scheduler secret configured: {bool(settings.scheduler_secret)}")
    if args.llm:
        try:
            response = httpx.get(settings.llm_base_url.rstrip("/") + "/health", timeout=10, follow_redirects=False)
            status = response.json()["data"]["status"]
            print(f"LLM service health: {status}")
            failed |= status != "ok"
        except Exception as error:  # noqa: BLE001
            print(f"LLM service reachable: False ({type(error).__name__})")
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
