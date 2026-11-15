"""Session-owned durable state in PostgreSQL (production) or SQLite (explicit LOCAL_DEV only).

Every user-facing row carries session_id. Every helper filters by the Backend-resolved session;
callers never accept an owner from request bodies. Tables live in the `claimly` schema; SQLite
attaches its file under that schema name so the same SQL runs on both engines.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from app.contract import validate
from app.errors import ApiError, not_found
from app.settings import Settings

TERMINAL = ("succeeded", "failed", "cancelled", "stale")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def uid() -> str:
    return str(uuid4())


def encoded(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha(value) -> str:
    return hashlib.sha256(encoded(value).encode()).hexdigest()


class DatabaseUnavailable(ApiError):
    def __init__(self, message="Database unavailable or not configured. Check DATABASE_URL and migrations."):
        super().__init__(503, "INTERNAL_ERROR", message, True)


class Connection:
    def __init__(self, raw, postgres: bool):
        self.raw, self.postgres = raw, postgres

    def execute(self, sql: str, params=()):
        if self.postgres:
            # No parameters: send as-is so literal % (e.g. format('%I')) is not a placeholder.
            return self.raw.execute(sql.replace("?", "%s"), params) if params else self.raw.execute(sql)
        return self.raw.execute(sql, params)

    def lock(self, value: str) -> None:
        """Transaction-scoped mutual exclusion (PostgreSQL advisory lock; SQLite writes are serialized)."""
        if self.postgres:
            number = int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big", signed=True)
            self.execute("SELECT pg_advisory_xact_lock(?)", (number,))


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.postgres = settings.postgres
        if settings.database_url and not self.postgres and not settings.database_url.startswith("sqlite:///"):
            raise DatabaseUnavailable("DATABASE_URL must be a PostgreSQL URI (or sqlite:/// with LOCAL_DEV=true).")

    def _pg_connect(self):
        import psycopg
        from psycopg.rows import dict_row

        url = self.settings.database_url
        kwargs = {"row_factory": dict_row, "connect_timeout": 10, "prepare_threshold": None}
        if "sslmode=" not in url:
            host = urlsplit(url).hostname or ""
            # Railway private networking is internal; public/Supabase connections require TLS.
            kwargs["sslmode"] = "prefer" if host.endswith(".railway.internal") or host in {"localhost", "127.0.0.1"} else "require"
        try:
            return psycopg.connect(url, **kwargs)
        except psycopg.Error:
            # Driver messages may contain hostnames/usernames; never relay them.
            raise DatabaseUnavailable() from None

    @contextmanager
    def tx(self, write: bool = False):
        if not self.settings.database_url:
            raise DatabaseUnavailable()
        if self.postgres:
            raw = self._pg_connect()
            try:
                raw.execute("SET LOCAL statement_timeout = '15s'")
                raw.execute("SET LOCAL lock_timeout = '5s'")
                yield Connection(raw, True)
                raw.commit()
            except Exception:
                raw.rollback()
                raise
            finally:
                raw.close()
            return
        path = self.settings.database_url.removeprefix("sqlite:///")
        raw = sqlite3.connect(":memory:", timeout=15, isolation_level=None, check_same_thread=False)
        raw.row_factory = sqlite3.Row
        try:
            raw.execute("ATTACH DATABASE ? AS claimly", (path,))
            raw.execute("PRAGMA foreign_keys=ON")
            raw.execute("PRAGMA claimly.busy_timeout=15000")
            raw.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield Connection(raw, False)
            raw.execute("COMMIT")
        except Exception:
            if raw.in_transaction:
                raw.execute("ROLLBACK")
            raise
        finally:
            raw.close()

    def prepare_local_file(self) -> None:
        if not self.postgres:
            path = Path(self.settings.database_url.removeprefix("sqlite:///"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(mode=0o600, exist_ok=True)

    # ── durable job queue ───────────────────────────────────────────────────────────
    def claim(self, worker_id: str):
        stamp = time.time()
        with self.tx(write=True) as c:
            c.lock("claimly-job-claim")
            exhausted = c.execute(
                "SELECT id, session_id, body FROM claimly.session_jobs WHERE attempts >= ? "
                "AND status IN ('queued','running') AND lease_until < ?", (self.settings.max_attempts, stamp)).fetchall()
            for old in exhausted:
                body = json.loads(old["body"])
                body.update(status="failed", progress=None, updated_at=now(),
                            error={"code": "LLM_UNAVAILABLE", "message": "Job retry/lease limit exhausted.", "retryable": False})
                c.execute("UPDATE claimly.session_jobs SET status='failed', body=?, lease_token=NULL WHERE id=?",
                          (encoded(body), old["id"]))
            sql = ("SELECT * FROM claimly.session_jobs j WHERE j.attempts < ? AND j.lease_until < ? AND j.available_at <= ? "
                   "AND j.status IN ('queued','running') AND NOT EXISTS (SELECT 1 FROM claimly.session_jobs r "
                   "WHERE r.target_id = j.target_id AND r.id <> j.id AND r.status = 'running' AND r.lease_until > ?) "
                   "ORDER BY j.created_at, j.id LIMIT 1")
            if self.postgres:
                sql += " FOR UPDATE SKIP LOCKED"
            row = c.execute(sql, (self.settings.max_attempts, stamp, stamp, stamp)).fetchone()
            if row is None:
                return None
            row = dict(row)
            body = json.loads(row["body"])
            body.update(status="running", updated_at=now())
            token = uid()
            c.execute("UPDATE claimly.session_jobs SET status='running', body=?, lease_token=?, lease_until=?, "
                      "attempts=attempts+1, locked_by=? WHERE id=?",
                      (encoded(body), token, stamp + self.settings.lease_seconds, worker_id, row["id"]))
            row.update(body=body, payload=json.loads(row["payload"]), lease_token=token, attempts=row["attempts"] + 1)
            return row


# ── session-scoped object helpers (all filter by owner) ──────────────────────────────
def find(c: Connection, owner: str, kind: str, object_id: str):
    row = c.execute("SELECT body, private FROM claimly.session_objects WHERE id=? AND session_id=? AND kind=?",
                    (object_id, owner, kind)).fetchone()
    if row is None:
        return None
    return json.loads(row["body"]), json.loads(row["private"])


def get(c: Connection, owner: str, kind: str, object_id: str):
    found = find(c, owner, kind, object_id)
    if found is None:
        raise not_found(kind.capitalize())
    return found


def put(c: Connection, owner: str, kind: str, body: dict, private: dict | None = None, parent: str | None = None) -> None:
    c.execute(
        "INSERT INTO claimly.session_objects AS o (id, session_id, kind, parent_id, body, private, created_at) "
        "VALUES (?,?,?,?,?,?,?) ON CONFLICT (id) DO UPDATE SET body=excluded.body, private=excluded.private, "
        "parent_id=excluded.parent_id WHERE o.session_id=excluded.session_id AND o.kind=excluded.kind",
        (body["id"], owner, kind, parent, encoded(body), encoded(private or {}), body.get("created_at") or now()))


def objects(c: Connection, owner: str, kind: str, parent: str | None = None):
    sql, args = "SELECT body, private FROM claimly.session_objects WHERE session_id=? AND kind=?", [owner, kind]
    if parent is not None:
        sql += " AND parent_id=?"
        args.append(parent)
    sql += " ORDER BY created_at, id"
    return [(json.loads(r["body"]), json.loads(r["private"])) for r in c.execute(sql, args).fetchall()]


def remove(c: Connection, owner: str, object_id: str) -> None:
    c.execute("DELETE FROM claimly.session_objects WHERE id=? AND session_id=?", (object_id, owner))


def new_job(c: Connection, owner: str, kind: str, target: str, payload: dict) -> dict:
    stamp = now()
    body = {"id": uid(), "kind": kind, "status": "queued", "progress": None, "result": None, "error": None,
            "created_at": stamp, "updated_at": stamp}
    validate("Job", body, output=True)
    c.execute("INSERT INTO claimly.session_jobs (id, session_id, target_id, kind, status, body, payload, created_at) "
              "VALUES (?,?,?,?,?,?,?,?)", (body["id"], owner, target, kind, "queued", encoded(body), encoded(payload), stamp))
    return body


def get_job(c: Connection, owner: str, job_id: str):
    row = c.execute("SELECT body, payload FROM claimly.session_jobs WHERE id=? AND session_id=?", (job_id, owner)).fetchone()
    if row is None:
        raise not_found("Job")
    return json.loads(row["body"]), json.loads(row["payload"])


def jobs(c: Connection, owner: str, *, active_only: bool = False):
    sql = "SELECT id, kind, target_id, status, body, payload FROM claimly.session_jobs WHERE session_id=?"
    if active_only:
        sql += " AND status IN ('queued','running')"
    return [dict(r, body=json.loads(r["body"]), payload=json.loads(r["payload"])) for r in c.execute(sql, (owner,)).fetchall()]


def end_job(c: Connection, owner: str, job_id: str, status: str, *, keep_result: bool = False, error: dict | None = None) -> None:
    """Cancel/stale a job outside its lease; a later worker publish fails its lease check."""
    body, _ = get_job(c, owner, job_id)
    body.update(status=status, progress=None, updated_at=now(), error=error)
    if not keep_result:
        body["result"] = None
    c.execute("UPDATE claimly.session_jobs SET status=?, body=?, lease_token=NULL WHERE id=? AND session_id=?",
              (status, encoded(body), job_id, owner))


def finish(c: Connection, claimed: dict, *, result=None, failure=None, status: str | None = None, max_attempts: int = 3) -> dict:
    row = c.execute("SELECT * FROM claimly.session_jobs WHERE id=? AND session_id=?",
                    (claimed["id"], claimed["session_id"])).fetchone()
    if row is None or row["status"] != "running" or row["lease_token"] != claimed["lease_token"] or row["lease_until"] < time.time():
        raise ApiError(409, "STALE_INPUT", "The job lease is no longer active.")
    body = json.loads(row["body"])
    retry = bool(failure is not None and failure.retryable and claimed["attempts"] < max_attempts and status is None)
    final = status or ("queued" if retry else "failed" if failure is not None else "succeeded")
    body.update(status=final, progress=100 if final == "succeeded" else None, result=result,
                error=failure.dto() if failure is not None and not retry else None, updated_at=now())
    validate("Job", body, output=True)
    delay = min(60, claimed["attempts"] * 10) if retry else 0
    c.execute("UPDATE claimly.session_jobs SET status=?, body=?, lease_token=NULL, lease_until=0, available_at=? "
              "WHERE id=? AND session_id=?", (final, encoded(body), time.time() + delay, body["id"], claimed["session_id"]))
    return body


def lease_active(c: Connection, claimed: dict) -> bool:
    row = c.execute("SELECT status, lease_token, lease_until FROM claimly.session_jobs WHERE id=? AND session_id=?",
                    (claimed["id"], claimed["session_id"])).fetchone()
    return bool(row and row["status"] == "running" and row["lease_token"] == claimed["lease_token"] and row["lease_until"] >= time.time())
