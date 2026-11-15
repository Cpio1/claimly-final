-- Claimly 0004: isolated anonymous demo sessions, durable jobs, retrieval chunks, usage history.
-- Forward-only and additive. Applied by `python -m app.migrate`, which records it in
-- claimly.schema_migrations inside the same transaction. It does NOT drop or modify the
-- legacy shared-workspace tables from 0001–0003; those are no longer used by the API.
-- Lines between "-- pg-only:begin" and "-- pg-only:end" are skipped for local SQLite.

-- pg-only:begin
CREATE SCHEMA IF NOT EXISTS claimly;
-- pg-only:end

CREATE TABLE IF NOT EXISTS claimly.demo_sessions (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash) = 64),
    creator_hash TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS demo_sessions_creator ON claimly.demo_sessions (creator_hash, created_at);
CREATE INDEX IF NOT EXISTS demo_sessions_expiry ON claimly.demo_sessions (expires_at);

-- Contract-shaped DTO bodies (entries, documents, benefits, threads, messages, cases, events,
-- drafts, outcomes, reminders, notifications, profile) plus Backend-only private metadata.
CREATE TABLE IF NOT EXISTS claimly.session_objects (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES claimly.demo_sessions(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('profile','entry','document','benefit','thread','message','case',
        'event','draft','outcome','reminder','notification')),
    parent_id TEXT,
    body TEXT NOT NULL,
    private TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE (id, session_id)
);
CREATE INDEX IF NOT EXISTS session_objects_owner ON claimly.session_objects (session_id, kind, parent_id);

CREATE TABLE IF NOT EXISTS claimly.session_jobs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES claimly.demo_sessions(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('extract','answer','match_need','assess','draft','draft_follow_up','analyze_reply')),
    target_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed','cancelled','stale')),
    body TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    lease_token TEXT,
    lease_until DOUBLE PRECISION NOT NULL DEFAULT 0,
    available_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    locked_by TEXT
);
CREATE INDEX IF NOT EXISTS session_jobs_queue ON claimly.session_jobs (status, available_at, lease_until);
CREATE INDEX IF NOT EXISTS session_jobs_owner ON claimly.session_jobs (session_id, target_id);

-- Idempotent mutation responses and durable upload intents (reserved -> completed, or
-- cleanup_required when Storage may hold an orphaned object).
CREATE TABLE IF NOT EXISTS claimly.session_requests (
    session_id TEXT NOT NULL REFERENCES claimly.demo_sessions(id) ON DELETE CASCADE,
    route TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('reserved','completed','cleanup_required')),
    status INTEGER,
    response TEXT,
    storage_path TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    size_bytes BIGINT NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    created_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (session_id, route, key_hash),
    CHECK ((state = 'completed') = (response IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS session_requests_recovery ON claimly.session_requests (state, created_at);

-- Storage paths outlive their session row so orphan cleanup survives session expiry.
CREATE TABLE IF NOT EXISTS claimly.storage_tombstones (
    storage_path TEXT PRIMARY KEY,
    created_at DOUBLE PRECISION NOT NULL
);

-- Retrieval chunks/vectors, filtered by owner, document version and embedding profile.
CREATE TABLE IF NOT EXISTS claimly.session_chunks (
    session_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    document_version INTEGER NOT NULL CHECK (document_version >= 1),
    profile TEXT NOT NULL,
    chunk TEXT NOT NULL,
    vector TEXT NOT NULL,
    PRIMARY KEY (session_id, chunk_id),
    FOREIGN KEY (document_id, session_id) REFERENCES claimly.session_objects(id, session_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS session_chunks_owner ON claimly.session_chunks (session_id, document_id, document_version, profile);

-- Absolute-usage history. An outcome owns at most one usage event, corrected in place.
CREATE TABLE IF NOT EXISTS claimly.usage_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES claimly.demo_sessions(id) ON DELETE CASCADE,
    benefit_id TEXT NOT NULL,
    outcome_id TEXT,
    source TEXT NOT NULL CHECK (source IN ('user_usage','outcome')),
    used_units INTEGER NOT NULL CHECK (used_units >= 0),
    quantity INTEGER,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS usage_events_outcome ON claimly.usage_events (session_id, outcome_id) WHERE outcome_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS usage_events_benefit ON claimly.usage_events (session_id, benefit_id);

CREATE TABLE IF NOT EXISTS claimly.request_limits (
    bucket_key TEXT NOT NULL,
    window_start BIGINT NOT NULL,
    requests INTEGER NOT NULL CHECK (requests > 0),
    PRIMARY KEY (bucket_key, window_start)
);

-- pg-only:begin
-- Browser roles never reach these tables. On Supabase, anon/authenticated exist; on plain
-- PostgreSQL (e.g. Railway) the DO block skips them. Backend still filters every query.
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['demo_sessions','session_objects','session_jobs','session_requests',
                             'storage_tombstones','session_chunks','usage_events','request_limits'] LOOP
        EXECUTE format('ALTER TABLE claimly.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('REVOKE ALL ON claimly.%I FROM PUBLIC', t);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE format('REVOKE ALL ON claimly.%I FROM anon', t);
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE format('REVOKE ALL ON claimly.%I FROM authenticated', t);
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON claimly.%I TO service_role', t);
        END IF;
    END LOOP;
    REVOKE ALL ON SCHEMA claimly FROM PUBLIC;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON SCHEMA claimly FROM anon; END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON SCHEMA claimly FROM authenticated; END IF;
END $$;
-- pg-only:end
