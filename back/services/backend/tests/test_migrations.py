"""PostgreSQL grammar/access checks (pglast) plus a real SQLite apply of runner-managed migrations."""

import re
from pathlib import Path

from pglast import ast, parse_sql
from pglast.enums import AlterTableType

from app.migrate import FIRST_MANAGED, managed, run, statements

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
LEGACY = [p for p in sorted(MIGRATIONS.glob("*.sql")) if int(p.name[:4]) < FIRST_MANAGED]


def test_all_migrations_parse_as_postgresql():
    for migration in sorted(MIGRATIONS.glob("*.sql")):
        assert parse_sql(migration.read_text(encoding="utf-8")), migration.name


def test_legacy_migrations_keep_their_own_transactions():
    for migration in LEGACY:
        statements_ = parse_sql(migration.read_text(encoding="utf-8"))
        assert isinstance(statements_[0].stmt, ast.TransactionStmt)
        assert isinstance(statements_[-1].stmt, ast.TransactionStmt)


def test_managed_migrations_leave_transactions_to_the_runner():
    for _, path in managed():
        assert not any(isinstance(s.stmt, ast.TransactionStmt) for s in parse_sql(path.read_text(encoding="utf-8"))), path.name


def test_legacy_tables_are_private_and_have_rls():
    parsed = parse_sql("\n".join(p.read_text(encoding="utf-8") for p in LEGACY))
    tables, protected = set(), set()
    for raw in parsed:
        statement = raw.stmt
        if isinstance(statement, ast.CreateStmt):
            tables.add(statement.relation.relname)
        if isinstance(statement, ast.AlterTableStmt) and any(c.subtype == AlterTableType.AT_EnableRowSecurity for c in statement.cmds):
            protected.add(statement.relation.relname)
        assert not isinstance(statement, ast.CreatePolicyStmt)
    assert tables and tables == protected


def test_managed_tables_are_in_claimly_schema_and_all_get_rls():
    for _, path in managed():
        sql = path.read_text(encoding="utf-8")
        created = set()
        for raw in parse_sql(sql):
            statement = raw.stmt
            assert not isinstance(statement, ast.CreatePolicyStmt)
            if isinstance(statement, ast.CreateStmt):
                assert statement.relation.schemaname == "claimly"
                created.add(statement.relation.relname)
        rls = set(re.findall(r"'(\w+)'", re.search(r"ARRAY\[(.*?)\]", sql, re.S).group(1)))
        assert created == rls, path.name


def test_sqlite_apply_is_repeatable(tmp_path):
    from app.db import Database
    from conftest import make_settings
    db = Database(make_settings(tmp_path, database_url="sqlite:///" + str(tmp_path / "m.sqlite")))
    assert run(db, out=lambda *_: None) == [p.name for _, p in managed()]
    assert run(db, out=lambda *_: None) == []
    sql = (MIGRATIONS / "0004_isolated_sessions.sql").read_text()
    assert all("pg-only" not in s and "DO $$" not in s for s in statements(sql, postgres=False))


def test_legacy_seed_workspace_is_untouched():
    seed = (MIGRATIONS / "0002_shared_workspace.sql").read_text(encoding="utf-8")
    assert "10000000-0000-4000-8000-000000000000" in seed
