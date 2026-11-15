# Deploying Claimly (Railway: API + worker + private LLM service, PostgreSQL, private bucket)

Status on 2026-11-15: **deployment configuration is prepared; nothing has been deployed.** No Railway,
Hugging Face or database resources were created, no paid calls were made, and the Vercel frontend
(`https://claimly-final.vercel.app`, mock mode) was not changed.

## Topology

| Railway resource | Source | Public? | Purpose |
|---|---|---|---|
| `api` | `back/services/backend/Dockerfile.api` | yes, HTTPS domain | Contract API for the browser; runs `python -m app.migrate` as pre-deploy |
| `worker` | `back/services/backend/Dockerfile.worker` | no | Durable jobs, embeddings, maintenance, in-app reminder dispatch |
| `llm` | `services/llm/Dockerfile` | **no** (private network only) | Docling/OCR conversion and Qwen chat calls; holds no DB/Storage credentials |
| `postgres` | Railway PostgreSQL | no | All state (`claimly` schema) |
| `claimly-originals` | Railway Bucket (private, S3-compatible) | no | Original uploads |

`.railway/railway.ts` is an Infrastructure-as-Code **draft** of this topology (Railway deprecated
`railway.json`; legacy files stop working for legacy services on 2026-12-01). Review it with
`railway config plan` before `railway config apply` — applying creates billable resources.
Supabase Postgres/Storage remain supported instead (`STORAGE_BACKEND=supabase`, `SUPABASE_*`).

## Steps

1. **Create/link the project** (`railway login && railway link`), connect this GitHub repo to `api`,
   `worker` and `llm` (repo root as build context; `RAILWAY_DOCKERFILE_PATH` selects each Dockerfile).
2. **Secrets** (Railway Variables, never in git or `NEXT_PUBLIC_*`):
   - `LLM_SERVICE_TOKEN` — same random value (≥32 bytes) on `worker` and `llm`.
   - `SCHEDULER_SECRET` — on `api`, used by a cron calling `POST /internal/v1/reminders/dispatch` (optional;
     the worker already dispatches in-app reminders every minute).
   - `HF_TOKEN`, `MODEL_BASE_URL` on `llm`; `HF_TOKEN`, `HF_EMBEDDING_URL` on `worker` if
     `EMBEDDING_PROVIDER=hf_endpoint`.
3. **Choose `SOURCE_REVIEW_MODE`** on `api`+`worker` (owner decision, see below).
4. **Plan, then apply**: `railway config plan` → review → `railway config apply`. The `api` pre-deploy
   applies migration 0004 (idempotent). Generate a Railway HTTPS domain for `api` only.
5. **Verify**: `railway run --service api python -m app.check_ready` (booleans only), `GET https://<api>/health`
   → `status: ok`, and on `worker`: `python -m app.check_ready --llm`.
6. **Frontend (later, when you approve it):** in Vercel set `NEXT_PUBLIC_API_MODE=http` and
   `NEXT_PUBLIC_API_BASE_URL=https://<api domain>`, then redeploy (build-time variables). Add any
   additional exact origin (e.g. a preview URL) to `FRONTEND_ORIGINS` on `api`. Rollback = revert those
   two variables and redeploy (mock mode).

## External prerequisites still missing

| Needed | Where | Why |
|---|---|---|
| Railway account/project authorization and budget | you | All resources below are billable; not created here |
| Protected **Qwen/Qwen3.8-27B** chat endpoint URL (vLLM/OpenAI-compatible) at revision `37561816…` | `MODEL_BASE_URL` on `llm` | Extraction, relevance, answers, matching, assessment, drafts, reply analysis. A model page URL is rejected |
| HF token with access to that endpoint | `HF_TOKEN` on `llm` (+ `worker` for TEI) | Server-side only |
| Embeddings: either a TEI endpoint for **Qwen/Qwen3-Embedding-0.6B** at revision `97b0c614…` (`HF_EMBEDDING_URL`), **or** `EMBEDDING_PROVIDER=local` with the worker image built `LOCAL_EMBEDDINGS=true`, the pinned weights (`EMBEDDING_MODEL_PATH`, e.g. on a worker volume) and `EMBEDDING_WEIGHTS_SHA256` | `worker` | Indexing and question embeddings (same space). Local mode needs ~3 GB RAM for fp32 on CPU; not benchmarked here |
| Decision: `SOURCE_REVIEW_MODE=operator` (an operator approves each upload; until then it stays "needs review") or `user_confirmation` (clean conversions indexed; every extracted item flagged for the user) | `api`, `worker` | Product/security decision; the default `operator` is safe but needs a staffed operator |
| Vercel env change + redeploy | Vercel | Not done, per instruction |
| Email provider (optional) | — | Not implemented: `email_configured=false`, email channels are rejected/marked failed |
| Custom domain (optional) | Railway | Otherwise use the generated `*.up.railway.app` HTTPS domain |

## Verification evidence (this workspace)

| Check | Result |
|---|---|
| Backend pytest on SQLite | 98 passed |
| Same suite on real PostgreSQL 14 (temporary local cluster) | 98 passed |
| 0004 applied on top of legacy 0001–0003 with Supabase-like roles; re-run is a no-op; `anon` has no access | passed |
| Slice regression suite (`services/backend/tests`) against the modified LLM service | 38 passed, 1 not run (needs Docling/torch) |
| Frontend typecheck + vitest (unchanged code) | passed, 41 tests |
| Real frontend built with `NEXT_PUBLIC_API_MODE=http` driven by headless Chromium against the local API/worker/LLM API (HF mocked) | session bootstrap, upload→extract→review, Vault, cited answer with source link, refresh persistence, second-browser isolation: passed |
| Docker image builds | **not run** (Docker daemon not running here) |
| Real Docling conversion, local Qwen embedding inference | **not run**: this machine is macOS x86_64, for which the locked torch 2.15 / onnxruntime 1.32 wheels do not exist; they run in the Linux images |
| Live Qwen chat/embedding accuracy, live Storage/Postgres on Railway, HTTPS E2E | **not run** (no endpoints/credentials/deployment) |

## Known limitations

- Vectors are JSON in PostgreSQL and ranked in Python per session (fine for MVP corpora; add pgvector
  for large corpora). Each request opens a new DB connection (add a pool before high traffic).
- Legal/reference corpus stays inactive: no legal source is supplied to the model; legal questions abstain.
- Exact-quote checks are not semantic entailment; live accuracy must be measured with real endpoints.
- `Railway` IaC DSL details for concatenated references and bucket variable names are not documented;
  confirm in the plan output or set those variables in the dashboard.
