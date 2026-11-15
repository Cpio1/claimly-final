"""Forward-only migration runner: python -m app.migrate [--status].

Applies numbered files from migrations/ starting at 0004 (the isolated-session schema), each in
one transaction together with its claimly.schema_migrations record. Legacy 0001–0003 belong to
the retired shared-workspace demo and are never re-run here (0001 intentionally fails on repeat).
Safe to run on every deploy (Railway preDeployCommand): applied versions are skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from pathlib import Path

from app.db import Database
from app.settings import BACKEND_DIR, Settings

MIGRATIONS = BACKEND_DIR / "migrations"
FIRST_MANAGED = 4
PG_ONLY = re.compile(r"-- pg-only:begin.*?-- pg-only:end", re.S)


def managed() -> list[tuple[str, Path]]:
    files = []
    for path in sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        if int(path.name[:4]) >= FIRST_MANAGED:
            files.append((path.name[:4], path))
    return files


def statements(sql: str, postgres: bool) -> list[str]:
    if not postgres:
        sql = PG_ONLY.sub("", sql)
        sql = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
        # SQLite qualifies the index name (not the table) and requires unqualified FK targets.
        sql = re.sub(r"(CREATE (?:UNIQUE )?INDEX IF NOT EXISTS )(\w+) ON claimly\.", r"\1claimly.\2 ON ", sql)
        sql = sql.replace("REFERENCES claimly.", "REFERENCES ")
        return [s.strip() for s in sql.split(";") if s.strip()]
    return [sql]


def ensure_table(c) -> None:
    if c.postgres:
        c.execute("CREATE SCHEMA IF NOT EXISTS claimly")
    c.execute("CREATE TABLE IF NOT EXISTS claimly.schema_migrations (version TEXT PRIMARY KEY, "
              "filename TEXT NOT NULL, sha256 TEXT NOT NULL, applied_at DOUBLE PRECISION NOT NULL)")
    if c.postgres:
        c.execute("""DO $$ BEGIN
            ALTER TABLE claimly.schema_migrations ENABLE ROW LEVEL SECURITY;
            REVOKE ALL ON claimly.schema_migrations FROM PUBLIC;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON claimly.schema_migrations FROM anon; END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON claimly.schema_migrations FROM authenticated; END IF;
        END $$""")


def applied(db: Database) -> dict[str, dict]:
    with db.tx(write=True) as c:
        ensure_table(c)
        return {r["version"]: dict(r) for r in c.execute("SELECT * FROM claimly.schema_migrations").fetchall()}


def run(db: Database, *, out=print) -> list[str]:
    db.prepare_local_file()
    done = []
    for version, path in managed():
        sql = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(sql.encode()).hexdigest()
        with db.tx(write=True) as c:
            c.lock("claimly-migrations")
            ensure_table(c)
            row = c.execute("SELECT sha256 FROM claimly.schema_migrations WHERE version=?", (version,)).fetchone()
            if row is not None:
                if row["sha256"] != digest:
                    raise SystemExit(f"Migration {path.name} changed after it was applied; add a new numbered migration instead.")
                continue
            for statement in statements(sql, c.postgres):
                c.execute(statement)
            c.execute("INSERT INTO claimly.schema_migrations VALUES (?,?,?,?)", (version, path.name, digest, time.time()))
            done.append(path.name)
            out(f"applied {path.name}")
    return done


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="List applied and pending managed migrations")
    args = parser.parse_args(argv)
    db = Database(Settings.from_env())
    if args.status:
        db.prepare_local_file()
        state = applied(db)
        for version, path in managed():
            print(f"{path.name}: {'applied' if version in state else 'pending'}")
        return 0
    done = run(db)
    print(f"Migrations complete; newly applied: {len(done)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
