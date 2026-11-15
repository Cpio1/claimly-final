# Claimly product Backend (merged)

FastAPI API + durable worker for the Claimly frontend (`front/apps/frontend`), implementing all
43 operations of `backend.openapi.json` **2.0.0** without contract changes. It merges this product
Backend (tracked upload intents, idempotency, rate/capacity limits, private Storage checks, curated
errors) with the integration slice (`services/backend/`, now superseded): isolated anonymous sessions,
durable worker, Docling/Qwen adapters, source-quality gate, retrieval and cited chat.

Deployment, environment variables and the list of external prerequisites: [DEPLOYMENT.md](DEPLOYMENT.md).

## Architecture

```
Browser (Vercel, NEXT_PUBLIC_API_MODE=http)
   │  HTTPS, X-Demo-Session, Idempotency-Key
   ▼
API  (app.main)  ── PostgreSQL (claimly schema: sessions, objects, jobs, chunks, usage, limits)
   │                └─ private bucket (S3-compatible / Supabase / local-dev) for originals
   └─ creates durable jobs ─▶ Worker (app.worker) ── private network ─▶ LLM service (services/llm)
                               │  extract → gate → chunk → embed      │  Docling/OCR, Qwen chat via
                               │  answer / match / assess / draft /   │  protected HF endpoint, schema +
                               │  analyze_reply → validate → publish  │  citation/ID guards (stateless)
                               └─ embeddings: HF TEI endpoint or local Qwen3-Embedding (CPU)
```

- **Sessions.** `POST /api/v1/demo/sessions` (no body, no login) returns a ≥32-byte random token; only
  its SHA-256 is stored; TTL 7 days; creation is rate-limited per client IP. Every data route resolves
  the owner from `X-Demo-Session`; every row is keyed by `session_id`; relationships (entry↔document,
  thread↔documents, case↔entries/documents/benefit, outcome evidence) are validated in the same session.
  Wrong-session IDs return 404. Missing/expired tokens return 401 `DEMO_SESSION_REQUIRED`/`EXPIRED`.
- **Uploads.** PDF/JPEG/PNG, signature + parser validation, ≤10 MB, ≤25 pages, ≤5 files/entry. A
  durable intent is committed before the Storage write and completed with the document + job in one
  transaction; replays return the original response; orphans are cleaned by maintenance.
- **Worker.** Postgres lease (`FOR UPDATE SKIP LOCKED`), ≤3 attempts with backoff, per-target
  serialization, lease + source-version checks inside the publishing transaction, restart-safe.
- **Admission gate (`SOURCE_REVIEW_MODE`).** `operator` (default): a trusted operator approves the
  exact original + canonical page hashes with `python -m app.review` before anything is populated or
  indexed. `user_confirmation`: clean conversions are indexed and *every* extracted fact/benefit is
  flagged `needs_review` for the existing review UI. Unreadable/uncertain/out-of-scope sources never
  enter the Vault or retrieval; out-of-scope originals are deleted.
- **Retrieval.** Owner, scope (vault/entry/case-linked documents), admission, document version and
  embedding identity are filtered **before** hybrid lexical+dense ranking; the model receives selected
  page text only. Embedding-profile changes queue a re-index from the cached conversion.
- **Guards.** Citations must resolve to exact quotes on supplied pages; benefit/action IDs must be in
  the supplied context; uncited answers become controlled abstentions; no usable pages → deterministic
  abstention without a model call; positive assessments require citations; draft contacts must be
  quoted from supplied text. Drafts are never sent.
- **Backend-owned rules.** Absolute usage with history (`usage_events`), outcome usage corrected in
  place (no double counting; unknown baselines never produce a full remainder), deterministic deadline
  dates (explicit dates and calendar intervals only), DST-aware reminder deliveries with unique keys
  (reminder + revision + interval + channel), protected idempotent dispatch.
- **Deletion.** Deleting a document/entry removes chunks/benefits, cancels reminders and jobs, marks
  historical jobs `stale`, scrubs citations from messages/assessments/drafts/replies, and tombstones the
  original in the same transaction (Storage deletion retried until it succeeds).

## Run locally

```bash
cd back/services/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
export PYTHONPATH=$PWD:$(cd ../../.. && pwd)            # repo root provides services.llm + contracts
export LOCAL_DEV=true DATABASE_URL=sqlite:///.data/claimly.sqlite STORAGE_BACKEND=local \
       LOCAL_STORAGE_DIR=.data/originals FRONTEND_ORIGINS=http://localhost:3000
.venv/bin/python -m app.migrate
.venv/bin/uvicorn app.main:app --port 8000          # API
.venv/bin/python -m app.worker                      # worker (+ maintenance, in-app reminders)
.venv/bin/python -m app.check_ready --llm           # read-only readiness (booleans only)
```

Or the whole stack with PostgreSQL: `docker compose up --build` from the repo root (see `compose.yaml`).
Frontend against it: `NEXT_PUBLIC_API_MODE=http NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run build && npm start`.

## Tests

```bash
.venv/bin/python -m pytest -q                                   # SQLite
CLAIMLY_TEST_DATABASE_URL=postgresql://user@127.0.0.1:5432/claimly_test?sslmode=disable \
  .venv/bin/python -m pytest -q                                 # real PostgreSQL (drops schema claimly!)
```

Tests use the real API, worker, Storage adapter (local), migrations, internal LLM API, prompts and guards.
Only the Hugging Face HTTP endpoint is an in-memory mock and PDF text comes from a native parser instead
of Docling. **They prove integration and safety rules, not live-model accuracy.**

## Operator review (operator mode)

```bash
python -m app.review --list
python -m app.review <document_id> --session-id <session_id>        # prints hashes + canonical pages
python -m app.review <document_id> --session-id <session_id> --approve --source-sha <…> --pages-sha <…>
```
