"""Backend-owned durable state. Explicit SQLite development mode or PostgreSQL; no implicit fallback."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4
from services.llm.app.contracts import Failure, validate

DDL = """
CREATE TABLE IF NOT EXISTS claimly_sessions (id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, expires DOUBLE PRECISION NOT NULL, creator_hash TEXT NOT NULL, created DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS claimly_objects (id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES claimly_sessions(id) ON DELETE CASCADE, kind TEXT NOT NULL, parent_id TEXT, body TEXT NOT NULL, private TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(id,session_id));
CREATE INDEX IF NOT EXISTS claimly_objects_owner ON claimly_objects(session_id,kind,parent_id);
CREATE TABLE IF NOT EXISTS claimly_jobs (id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES claimly_sessions(id) ON DELETE CASCADE, target_id TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, lease_token TEXT, lease_until DOUBLE PRECISION NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS claimly_jobs_queue ON claimly_jobs(status,lease_until);
CREATE TABLE IF NOT EXISTS claimly_idempotency (session_id TEXT NOT NULL REFERENCES claimly_sessions(id) ON DELETE CASCADE, route TEXT NOT NULL, key TEXT NOT NULL, request_hash TEXT NOT NULL, response TEXT NOT NULL, status INTEGER NOT NULL, PRIMARY KEY(session_id,route,key));
CREATE TABLE IF NOT EXISTS claimly_vectors (chunk_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, document_id TEXT NOT NULL, version INTEGER NOT NULL, profile TEXT NOT NULL, chunk TEXT NOT NULL, vector TEXT NOT NULL, FOREIGN KEY(document_id,session_id) REFERENCES claimly_objects(id,session_id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS claimly_vectors_owner ON claimly_vectors(session_id,document_id,version,profile);
"""

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def uid(): return str(uuid4())
def encoded(value): return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def sha(value): return hashlib.sha256(encoded(value).encode()).hexdigest()

class Connection:
    def __init__(self, raw, postgres): self.raw,self.postgres=raw,postgres
    def execute(self, sql, params=()):
        return self.raw.execute(sql.replace('?', '%s') if self.postgres else sql,params)
    def lock_key(self, value):
        if self.postgres:
            number=int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], 'big', signed=True)
            self.execute('SELECT pg_advisory_xact_lock(?)',(number,))

class Database:
    def __init__(self, settings):
        self.settings=settings
        self.postgres=not settings.database_url.startswith('sqlite:///')
    @contextmanager
    def tx(self, write=False):
        dsn=self.settings.database_url
        if not dsn:
            raise Failure('AI_NOT_CONFIGURED','Configure Backend DATABASE_URL and private storage before use.',503)
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            raw=psycopg.connect(dsn,row_factory=dict_row,connect_timeout=10)
        else:
            if not self.settings.local_storage:
                raise Failure('AI_NOT_CONFIGURED','SQLite requires explicit LOCAL_DEV_STORAGE=true.',503)
            raw=sqlite3.connect(dsn.removeprefix('sqlite:///'),timeout=15)
            raw.row_factory=sqlite3.Row
            raw.execute('PRAGMA foreign_keys=ON')
            raw.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        try:
            yield Connection(raw,self.postgres)
            raw.commit()
        except Exception:
            raw.rollback(); raise
        finally: raw.close()
    def setup(self):
        if not self.postgres:
            path=Path(self.settings.database_url.removeprefix('sqlite:///'))
            path.parent.mkdir(parents=True,exist_ok=True)
        with self.tx(write=True) as c:
            for stmt in DDL.split(';'):
                if stmt.strip(): c.execute(stmt)
            if self.postgres:
                for table in ('sessions','objects','jobs','idempotency','vectors'):
                    # No anon/authenticated grants/policies. Backend uses a privileged server connection,
                    # and STILL filters every user operation by the resolved session.
                    c.execute('ALTER TABLE claimly_'+table+' ENABLE ROW LEVEL SECURITY')
                    c.execute('REVOKE ALL ON claimly_'+table+' FROM anon, authenticated')
        if not self.postgres: path.chmod(0o600)
    def claim(self, lease_seconds=1200):
        stamp=time.time()
        with self.tx(write=True) as c:
            c.lock_key("claimly-job-claim")
            exhausted=c.execute("SELECT id,body FROM claimly_jobs WHERE attempts>=3 AND status IN ('queued','running') AND lease_until<?",(stamp,)).fetchall()
            for old in exhausted:
                body=json.loads(old["body"]); body.update(status="failed",updated_at=now(),error={"code":"LLM_UNAVAILABLE","message":"Job retry/lease limit exhausted.","retryable":False})
                c.execute("UPDATE claimly_jobs SET status='failed',body=?,lease_token=NULL WHERE id=?",(encoded(body),old["id"]))
            sql="""SELECT * FROM claimly_jobs j WHERE attempts < 3 AND lease_until < ?
                   AND status IN ('queued','running') AND NOT EXISTS
                   (SELECT 1 FROM claimly_jobs r WHERE r.target_id=j.target_id AND r.id<>j.id
                    AND r.status='running' AND r.lease_until>?) ORDER BY j.created_at,j.id LIMIT 1"""
            if self.postgres: sql+=' FOR UPDATE SKIP LOCKED'
            row=c.execute(sql,(stamp,stamp)).fetchone()
            if row is None: return None
            row=dict(row); body=json.loads(row['body']); body.update(status='running',updated_at=now())
            token=uid()
            c.execute('UPDATE claimly_jobs SET status=?,body=?,lease_token=?,lease_until=?,attempts=attempts+1 WHERE id=?',
                      ('running',encoded(body),token,stamp+lease_seconds,row['id']))
            row.update(body=body,payload=json.loads(row['payload']),lease_token=token,attempts=row['attempts']+1)
            return row

def get(c, owner, kind, object_id):
    row=c.execute('SELECT * FROM claimly_objects WHERE id=? AND session_id=? AND kind=?',(object_id,owner,kind)).fetchone()
    if row is None: raise Failure('NOT_FOUND','Object not found in this session.',404)
    return json.loads(row['body']),json.loads(row['private'])

def put(c, owner, kind, body, private=None, parent=None):
    c.execute('INSERT INTO claimly_objects(id,session_id,kind,parent_id,body,private,created_at) VALUES(?,?,?,?,?,?,?) '
              'ON CONFLICT(id) DO UPDATE SET body=excluded.body,private=excluded.private,parent_id=excluded.parent_id '
              'WHERE claimly_objects.session_id=excluded.session_id AND claimly_objects.kind=excluded.kind',
              (body['id'],owner,kind,parent,encoded(body),encoded(private or {}),body.get('created_at',now())))

def objects(c, owner, kind, parent=None):
    sql='SELECT body,private FROM claimly_objects WHERE session_id=? AND kind=?'; args=[owner,kind]
    if parent is not None: sql+=' AND parent_id=?'; args.append(parent)
    sql+=' ORDER BY created_at,id'
    return [(json.loads(r['body']),json.loads(r['private'])) for r in c.execute(sql,args).fetchall()]

def job(c, owner, kind, target, payload):
    body={'id':uid(),'kind':kind,'status':'queued','progress':0,'result':None,'error':None,'created_at':now(),'updated_at':now()}
    validate('Job',body)
    c.execute('INSERT INTO claimly_jobs(id,session_id,target_id,kind,status,body,payload,created_at) VALUES(?,?,?,?,?,?,?,?)',
              (body['id'],owner,target,kind,'queued',encoded(body),encoded(payload),body['created_at']))
    return body

def finish(c, claimed, *, result=None, failure=None, status=None):
    row=c.execute('SELECT * FROM claimly_jobs WHERE id=? AND session_id=?',(claimed['id'],claimed['session_id'])).fetchone()
    if row is None or row['status']!='running' or row['lease_token']!=claimed['lease_token'] or row['lease_until']<time.time():
        raise Failure('STALE_INPUT','The job lease is no longer active.',409)
    body=json.loads(row['body'])
    retry=bool(failure and failure.retryable and claimed['attempts']<3)
    body.update(status=status or ('queued' if retry else 'failed' if failure else 'succeeded'),progress=0 if retry else 100,
                result=result,error=failure.dto() if failure else None,updated_at=now())
    validate('Job',body)
    c.execute('UPDATE claimly_jobs SET status=?,body=?,lease_token=NULL,lease_until=? WHERE id=? AND session_id=?',
              (body['status'],encoded(body),time.time()+min(30,claimed['attempts']*5) if retry else 0,body['id'],claimed['session_id']))
    return body

if __name__=='__main__':
    from .config import BackendSettings
    Database(BackendSettings.env()).setup()
    print('Backend database schema initialized; user-facing contracts unchanged.')
