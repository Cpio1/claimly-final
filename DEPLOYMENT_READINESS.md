# Claimly deployment readiness

Audit date: 2026-11-15. **Ready to start product integration; not ready to claim a live, end-to-end deployment.** This audit read source/configuration and prior verification artifacts. It did not deploy infrastructure, run live inference, change Supabase, or rerun the product frontend/backend test suites.

## Current component map

| Component | Actual location | Current evidence |
|---|---|---|
| Product frontend | `back/front/apps/frontend/` | Next.js/TypeScript source and lockfile present; default mode is MSW mock; expects per-browser demo sessions |
| Product Backend | `back/services/backend/` | PostgreSQL/private Storage upload foundation; fixed shared workspace; extract jobs remain queued; no worker/chat routes |
| Upload/chat integration slice | `services/backend/` | Separate Backend, durable worker, review, retrieval and integration UI; SQLite path tested; not merged into product Backend |
| Model/parsing service | `services/llm/app/`, `services/llm/parsing/` | Real Docling, Qwen tokenizer assets, HF clients, schema/evidence/hallucination guards |
| Reference sources | `services/llm/rag/claimly_legal_corpus_kit/` | Downloaded source candidates, audit and source plan; not active legal retrieval |

## Prerequisite checklist

| Prerequisite | Status | Remaining work |
|---|---|---|
| Existing UI and Backend source | Present | Reuse them; do not replace the Next.js product with the integration screen |
| Shared schema agreement | Partly ready | Root and frontend contract copies are byte-identical 2.0.0, but product Backend deliberately deviates from the session/security model |
| User/session boundary | **Blocker** | Frontend bootstraps `/api/v1/demo/sessions`; product Backend has no session endpoint and uses a single public workspace. CORS omits `X-Demo-Session`. Resolve before accepting private user uploads |
| Product upload -> analysis -> chat | **Blocker** | Product Backend has upload/metadata/job reads only. Port/adapt worker, admission, retrieval, message/thread and content-source paths; implement remaining routes required by shipped UI |
| Qwen embedding execution | **Not ready** | Tokenizers/configs are pinned. Latest recommended local/server embedding adapter and actual inference are absent. Current slice calls HF embeddings instead |
| Qwen chat endpoint | **Not configured here** | Model selected/pinned, but actual protected HF endpoint URL and inference token are absent. Model repository pages are not endpoints |
| Production database/private bucket | **Not verified here** | No local product Backend .env or root DATABASE_URL/Supabase credentials. Existing migrations and storage adapter need live checks; do not infer remote migration state |
| Runtime/build tooling | **Not ready on task PATH** | Node/npm, Docker and psql are unavailable on the inspected task PATH. No local frontend build or container build was run. A configured CI/hosting build environment can satisfy this instead |
| Runtime dependency compatibility | **Needs reconciliation** | Product Backend constrains pypdf below 7 and Pillow below 13; the slice tested pypdf 7.1.0/Pillow 13.0.0. Use separate environments and reconcile adapters explicitly |
| Quality/relevance and hallucination guards | Implemented in slice | Port without bypasses. Exact quote checks/controlled abstention are not proof of semantic entailment |
| Automated regression evidence | Ready for slice only | Recorded 100 passing tests, including 61 parsing + 39 integration tests; provider HTTP is mocked with separate real Docling/tokenizer checks |
| Live model accuracy and full-product E2E | **Not verified** | Run reviewed synthetic/known-source tests against actual services and models; product frontend README results are historical, not rerun here |
| Hosting/domain/HTTPS/secrets/rollback | **Not configured/verified here** | Choose target(s), prepare exact configuration and cost, configure protected access, readiness, worker supervision, backups and rollback |
| Legal/reference answers | Inactive | Review sources/jurisdiction/version/conditions and agree citations before enabling legal inference; keep unsupported legal answers unavailable |

Root `.env` contains a local internal-service token, but required HF/database/Storage fields are empty. Only presence/absence was inspected; no values were printed. External account or machine configuration was not inspected, so 'not configured here' is not a claim that no remote account exists.

## Blocking integration mismatch

Source evidence:

- `back/front/apps/frontend/src/components/Providers.tsx` always calls `ensureSession()` on boot.
- `back/front/apps/frontend/src/api/config.ts` defaults to mock mode.
- `back/services/backend/app/routes.py` exposes only POST entries/documents and GET document/job under `/api/v1`; it describes a shared workspace with no visitor sessions.
- `back/services/backend/app/main.py` only allows GET/POST CORS and Content-Type/Idempotency-Key headers; its health check is liveness, not model/database readiness.
- `back/services/backend/UPLOADS.md` explicitly records the contract conflict, shared synthetic-only demo and missing worker/content/list/chat integration.

**Do not solve this by merely pointing the current frontend at that Backend or deleting its session headers.** For private user documents, use an explicit, consistent isolation model throughout database, Storage, jobs, retrieval, chat and deletion. The original contract direction is automatic anonymous isolated demo sessions, without login. If the product owner intentionally selects a shared demo instead, restrict it to clearly labelled synthetic material, align all layers and document the contractual deviation. A private-user product and a shared public demo are different release scopes.

## Existing implementation assets worth reusing

Preserve the product Backend's tracked upload intents, idempotency, quota/rate limits, storage failure recovery, strict key handling and private bucket checks. Its new Supabase secret keys use `apikey`, not a Bearer JWT. Do not overwrite this with the prototype's different storage assumptions.

Reuse the slice's Docling/OCR, canonical text, quality/relevance gating, source-bound review, embedding identity, exact page spans, filtered retrieval, durable worker logic, citation checks and controlled no-evidence abstention. Adapt them to the chosen product schema, rather than applying both Backend schemas blindly to the same project.

The latest proposed hosting direction is local embeddings for development, CPU application-server embeddings for an initial MVP, and hosted HF Qwen3.8-27B chat. Current code still calls HF for BOTH model roles. Local/server embeddings require an explicit adapter, pinned weights, correct instructions/pooling/normalization and measured performance.

## Verdict

Integration coding and local analysis can begin now. A truthful live deployment still requires the security-model decision, actual product wiring, model execution/credentials, verified production storage, build/hosting setup and live E2E validation.

Use [PRODUCT_DEPLOYMENT_PROMPT.md](PRODUCT_DEPLOYMENT_PROMPT.md) for the next full-product implementation/deployment task. No product code or infrastructure was changed by this audit.
