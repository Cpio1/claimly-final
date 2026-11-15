"""Request plumbing: session resolution, rate limits, idempotency, pagination, envelopes."""

from __future__ import annotations

import hashlib
import json
import time
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse

from app.db import Connection, Database, encoded, sha
from app.errors import ApiError, invalid
from app.settings import Settings

SESSION_REQUIRED = ApiError(401, "DEMO_SESSION_REQUIRED", "A demo session is required.")
SESSION_EXPIRED = ApiError(401, "DEMO_SESSION_EXPIRED", "This demo session has expired. Start a new session.")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def client_ip(request: Request) -> str:
    # With uvicorn --proxy-headers and FORWARDED_ALLOW_IPS, client.host is the platform-forwarded address.
    return request.client.host if request.client else "unknown"


def identity(value) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError):
        raise invalid("Expected a valid object UUID.") from None


def envelope(request: Request, data) -> dict:
    return {"data": data, "request_id": request.state.request_id}


def limit_hit(c: Connection, key: str, limit: int, window_seconds: int = 60) -> bool:
    window = int(time.time() // window_seconds) * window_seconds
    row = c.execute(
        "INSERT INTO claimly.request_limits AS l (bucket_key, window_start, requests) VALUES (?, ?, 1) "
        "ON CONFLICT (bucket_key, window_start) DO UPDATE SET requests = l.requests + 1 RETURNING requests",
        (key, window)).fetchone()
    return row["requests"] > limit


class Api:
    """Per-app dependencies. Every data operation resolves the owner from X-Demo-Session."""

    READ_LIMIT, WRITE_LIMIT = 600, 120

    def __init__(self, settings: Settings, db: Database, storage_factory):
        self.settings, self.db, self._storage_factory, self._storage = settings, db, storage_factory, None

    @property
    def storage(self):
        if self._storage is None:
            self._storage = self._storage_factory()
        return self._storage

    def owner(self, c: Connection, request: Request, *, write: bool) -> str:
        token = request.headers.get("X-Demo-Session", "")
        if not 43 <= len(token) <= 128:
            raise SESSION_REQUIRED
        row = c.execute("SELECT id, expires_at FROM claimly.demo_sessions WHERE token_hash=?", (token_hash(token),)).fetchone()
        if row is None:
            raise SESSION_REQUIRED
        if row["expires_at"] < time.time():
            raise SESSION_EXPIRED
        group = "w" if write else "r"
        if limit_hit(c, f"{group}:s:{row['id']}", self.WRITE_LIMIT if write else self.READ_LIMIT):
            raise ApiError(429, "RATE_LIMITED", "Too many requests for this demo session. Retry in a minute.", True)
        return row["id"]

    def read(self, request: Request):
        """Context manager-like helper returning (connection, owner) for read-only routes."""
        return _Scope(self, request, write=False)

    def write(self, request: Request):
        return _Scope(self, request, write=True)

    def idempotent(self, c: Connection, request: Request, owner: str, payload, status: int, operation):
        key = request.headers.get("Idempotency-Key", "")
        if not 8 <= len(key) <= 128:
            raise invalid("Idempotency-Key must contain 8 to 128 characters.")
        route, key_hash = request.method + " " + request.url.path, token_hash(key)
        digest = sha(payload)
        c.lock(owner + route + key_hash)
        old = c.execute("SELECT * FROM claimly.session_requests WHERE session_id=? AND route=? AND key_hash=?",
                        (owner, route, key_hash)).fetchone()
        if old:
            if old["request_hash"] != digest:
                raise ApiError(409, "CONFLICT", "This Idempotency-Key was already used with a different request.")
            if old["state"] != "completed":
                raise ApiError(409, "CONFLICT", "This request is still being processed. Retry with the same key shortly.", True)
            return JSONResponse(json.loads(old["response"]), status_code=old["status"])
        result = envelope(request, operation())
        c.execute("INSERT INTO claimly.session_requests (session_id, route, key_hash, request_hash, state, status, response, created_at) "
                  "VALUES (?,?,?,?,?,?,?,?)", (owner, route, key_hash, digest, "completed", status, encoded(result), time.time()))
        return JSONResponse(result, status_code=status)


class _Scope:
    def __init__(self, api: Api, request: Request, *, write: bool):
        self.api, self.request, self.write = api, request, write
        self._tx = None

    def __enter__(self):
        # Rate-limit counters are writes, so even reads open a write transaction.
        self._tx = self.api.db.tx(write=True)
        c = self._tx.__enter__()
        try:
            return c, self.api.owner(c, self.request, write=self.write)
        except BaseException as error:
            # Close the transaction now (rollback) instead of leaving it to garbage collection.
            self._tx.__exit__(type(error), error, error.__traceback__)
            raise

    def __exit__(self, *exc):
        return self._tx.__exit__(*exc)


def page(request: Request, items: list[dict], cursor: str | None, limit: int) -> dict:
    """Stable, opaque cursor: the id of the last returned item in the sorted collection."""
    if not 1 <= limit <= 100:
        raise invalid("limit must be between 1 and 100.")
    if cursor:
        positions = [i for i, item in enumerate(items) if item["id"] == cursor]
        if not positions:
            raise invalid("The pagination cursor is not valid for this collection.")
        items = items[positions[0] + 1:]
    chunk = items[:limit]
    return {"data": chunk, "next_cursor": chunk[-1]["id"] if len(items) > limit else None,
            "request_id": request.state.request_id}


def sort_key(value):
    """None sorts last, like the reference mock's cmp()."""
    return (value is None, value if value is not None else "")
