-- Upload/chat integration slice. Backend service-role connection only; no browser DB access.
BEGIN;

CREATE TABLE IF NOT EXISTS claimly_sessions (id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, expires DOUBLE PRECISION NOT NULL, creator_hash TEXT NOT NULL, created DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS claimly_objects (id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES claimly_sessions(id) ON DELETE CASCADE, kind TEXT NOT NULL, parent_id TEXT, body TEXT NOT NULL, private TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(id,session_id));
CREATE INDEX IF NOT EXISTS claimly_objects_owner ON claimly_objects(session_id,kind,parent_id);
CREATE TABLE IF NOT EXISTS claimly_jobs (id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES claimly_sessions(id) ON DELETE CASCADE, target_id TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, lease_token TEXT, lease_until DOUBLE PRECISION NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS claimly_jobs_queue ON claimly_jobs(status,lease_until);
CREATE TABLE IF NOT EXISTS claimly_idempotency (session_id TEXT NOT NULL REFERENCES claimly_sessions(id) ON DELETE CASCADE, route TEXT NOT NULL, key TEXT NOT NULL, request_hash TEXT NOT NULL, response TEXT NOT NULL, status INTEGER NOT NULL, PRIMARY KEY(session_id,route,key));
CREATE TABLE IF NOT EXISTS claimly_vectors (chunk_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, document_id TEXT NOT NULL, version INTEGER NOT NULL, profile TEXT NOT NULL, chunk TEXT NOT NULL, vector TEXT NOT NULL, FOREIGN KEY(document_id,session_id) REFERENCES claimly_objects(id,session_id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS claimly_vectors_owner ON claimly_vectors(session_id,document_id,version,profile);

ALTER TABLE claimly_sessions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON claimly_sessions FROM anon, authenticated;

ALTER TABLE claimly_objects ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON claimly_objects FROM anon, authenticated;

ALTER TABLE claimly_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON claimly_jobs FROM anon, authenticated;

ALTER TABLE claimly_idempotency ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON claimly_idempotency FROM anon, authenticated;

ALTER TABLE claimly_vectors ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON claimly_vectors FROM anon, authenticated;
COMMIT;
