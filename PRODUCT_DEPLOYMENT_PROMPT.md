# Claimly — full product integration and deployment prompt

Read [DEPLOYMENT_READINESS.md](DEPLOYMENT_READINESS.md) first. The code is ready for integration work; live deployment prerequisites are not all met. This prompt describes the next task, not a claim that deployment has occurred. Invoking it explicitly selects complete-product integration, so `back/` becomes the actual product target under the user's earlier condition.

Copy the following block into the next coding-agent conversation:

```text
You are integrating and deploying the existing Claimly product. Connect the actual frontend, users/demo sessions, Backend, document ingestion, model-backed agent roles, retrieval and deployment. Reuse what exists and complete the authorized work; do not stop at a diagram or recreate the product as a parallel scaffold.

READ FIRST
1. Applicable AGENTS.md. Query the existing graphify graph before source browsing, and update it after code changes. Keep user-facing paths relative. Never print credentials or .env contents.
2. DEPLOYMENT_READINESS.md and services/llm/rag/NEXT_CHAT_HANDOFF.md. Distinguish code, explicit mocks, prior test results, recommended changes and missing live connections.
3. Claimly_Three_Parts/00_START_HERE.txt, 01_BACKEND_TZ.txt, 02_FRONTEND_TZ.txt, 03_LLM_TZ.txt, 99_Product_MVP_Source.txt and shared contracts/fixtures. The canonical public contract is 2.0.0; coordinate any necessary change across copies and generated frontend types rather than changing fields/statuses/routes unilaterally.
4. The ACTUAL product: back/front/apps/frontend/ and back/services/backend/, including README.md, UPLOADS.md, migrations, API client/session/config/Providers, routes, upload service, repository and Storage adapters.
5. The reusable slice: services/backend/, services/llm/app/, services/llm/rag/runtime.py, services/llm/README.md, hf-models.lock.json, hf-deployment-plan.json and reports/verification.json.
6. services/llm/parsing/DOCLING_PLAN.md, FINAL_STAGE_1.md and the user-designated n8n-rag reference. The legal kit is a source candidate collection, not an approved legal index.

GOAL AND RELEASE SCOPE
Deliver the real product UI connected to real Backend/worker/model/storage services, deployed at a reachable HTTPS URL with evidence that the promised flows work. The standalone services/backend/web/ screen is an integration demo, not the product frontend. Do not substitute a mock demo for a live release, invent model outputs or claim a complete product by hiding unfinished required functionality.

Start with a source-grounded architecture/gap map, then implement and verify the missing connections. The first vertical slice is upload -> validated conversion -> relevance/quality review -> accepted document -> embeddings/index -> user question -> authorized retrieval -> cited answer. Then complete the other shipped UI flows and required backend/model operations from the product specification. If the owner explicitly narrows the release scope, record that decision and its UI/API consequences.

CURRENT STATE — DO NOT ASSUME IT IS ALREADY CONNECTED
- Product frontend is Next.js/TypeScript and defaults to MSW mock. It expects automatic isolated demo sessions and X-Demo-Session on data requests. Its public API base/mode values are build-time configuration.
- Product Backend has PostgreSQL/private Storage uploads, idempotency/tracked upload recovery and queued extract jobs, but uses a fixed shared public workspace with no visitor sessions. It has no AI worker, chat/message endpoints or source content delivery. It lacks many routes used by the frontend. Its /health only proves process liveness.
- The separate slice has isolated sessions, a durable worker, real Docling, HF model adapters, review/index/retrieval/chat and a small UI. Its recorded 100 tests use explicit provider mocks, plus real Docling/tokenizer checks. They do not establish real Qwen accuracy or deployed full-product behavior.
- Root and back/front contract copies currently match; security behavior in the product Backend does not match their session requirement.
- HF repository links are not deployed model endpoints. Required endpoint URLs, provider token and production DB/Storage settings are not configured in the inspected workspace. No paid endpoints were created.
- Node/npm, Docker and psql were unavailable on the task PATH. Frontend historical README test claims were not rerun in this workspace.
- Product Backend and prototype dependency versions differ. Keep service-local environments/locks and reconcile compatibility instead of copying an environment or overwriting requirements.

1. RESOLVE THE USER/SESSION BOUNDARY FIRST
Explain the confirmed conflict: frontend/canonical contract require isolated anonymous sessions; product Backend implements a shared synthetic-only demo. Default to the original isolated no-login contract for PRIVATE user documents unless the owner explicitly chooses another release security model. Present any necessary decision before destructive migrations or contract changes. Never silently downgrade isolation by removing frontend session checks.
For isolated sessions, bind every private entry, original, page, benefit, job, thread/message, chunk and vector to the Backend-resolved session. Validate relationships as well as individual IDs. Filter ownership/scope/version BEFORE retrieval ranking. Private buckets and RLS do not replace Backend checks. Shared approved sample/reference material needs a separate explicit access class. If a shared public demo is explicitly selected instead, keep it synthetic-only and align UI wording, routes and contracts transparently.

2. CHOOSE ONE PRODUCT BACKEND AND MIGRATION PATH
Use back/services/backend/ as the product integration target. Port/adapt tested components from services/backend/ and services/llm/ deliberately; do not run two competing public Backends or duplicate ownership tables.
Preserve durable upload intent/idempotency recovery, capacity/rate limits, private Storage checks and safe failure handling. The product's Supabase sb_secret key is sent through apikey, not assumed to be a JWT. Keep secrets Backend-only.
Inspect actual migration history and live schema before applying changes. Back up relevant state and add new numbered forward migrations. Do not rerun migrations that intentionally fail on repetition, drop existing tables or blindly apply the prototype's different public schema to the product database. Keep original user files/reviews/model assets intact.
Implement every contract route used by shipped pages, with stable envelopes, versions, pagination, allowed status transitions, ownership and source identity. Protect the internal model service with a separate LLM_SERVICE_TOKEN. The LLM service remains stateless and has no DB/Storage credentials.

3. IMPLEMENT THE AGENT ROLES WITHOUT UNNECESSARY FRAMEWORKS
Treat agents as logical responsibilities behind existing service operations, not a reason to add an autonomous-agent framework:
- Ingestion/conversion: validate PDF/JPEG/PNG bytes (10 MB, 25 pages), preserve originals, normalize EXIF only for processing, reuse the prefetched Docling/RapidOCR converter.
- Relevance: classify readable content under Claimly policy. Printed supported title/period is useful evidence; filenames/folders/categories/document commands cannot force admission. A relevant bill needs no due date or benefits.
- Extraction: return the EXISTING ExtractionOutput with canonical pages, supported category, nullable facts and explicit benefit candidates. DoclingDocument JSON is an internal artifact, never the public row/extraction schema. Use deliberate internal checkpoint storage if implemented.
- Retrieval: deterministic chunking, pinned embedding identity and authorized evidence selection.
- Assistant/matching/assessment/drafting/reply analysis: implement the existing operations and grounded structured outputs required by the actual UI. No automatic sending of messages/claims.
Backend owns durable jobs, retries/leases, idempotency, usage state, final deadline calculations, case state, reminders and business actions. Model agents do not deduct services, promise refunds or change those states themselves.

4. CONNECT UPLOAD, REVIEW, INDEXING AND LIFECYCLE
Frontend creates the appropriate Entry, uploads actual bytes, receives a persistent Job, polls boundedly and refreshes entities from Backend. Durable workers must survive restarts, check leases/source versions and atomically publish complete results.
Keep relevance, readability/conversion quality, extracted fact accuracy and temporal/legal applicability separate. Out-of-scope, invalid, unreadable and unresolved sources cannot enter ordinary retrieval or populate an accepted Vault row. The unpopulated draft needed by the upload contract is not admission.
Preserve the source-bound quality gate. Reconcile operator source-quality approval with the product's existing user field/benefit-review UI; they are different reviews. Do not silently auto-approve OCR or use model confidence as verification. If an additional public review API is needed, propose and coordinate its contract first; a documented internal operator workflow is acceptable only when explicitly chosen for the release.
Keep original/version/hash/canonical text and provenance linked. Test repeated ingestion, index-profile changes, changed versions, partial embedding batches, deletion, tombstones and cleanup. Source deletion must also invalidate historical message/job citations and in-flight answers.

5. SELECT AND VERIFY MODEL EXECUTION
Selected embedding model: Qwen/Qwen3-Embedding-0.6B.
Selected chat/extraction model: Qwen/Qwen3.8-27B.
Use the exact commits in services/llm/hf-models.lock.json; the tokenizer, model weights, task instruction, pooling, dimension and normalization must agree.
Latest proposed deployment: local embeddings for development, application-server CPU embeddings for an initial MVP, hosted HF chat. Current code calls HF for both. Add a provider-neutral embedding adapter and implement/test the local Qwen option; keep remote TEI only as an explicitly selected alternative. Explicitly prefetch real embedding weights and benchmark bounded batches/CPU/MPS. Only tokenizer/config files have been verified locally. Do not claim local embedding performance from a tokenizer test.
Use the SAME embedding space for document/reference chunks and search questions. Store vectors once per eligible chunk/processing identity; do not regenerate the whole corpus for every chat message. Retain complete source/context text, page/item or legal-section mappings, hashes, neighbors and model/version metadata. No silent truncation.
Host chat through a protected HF-compatible endpoint and server adapter. Model page URLs are invalid inference URLs. Verify actual endpoint model/revision/configuration, structured-output behavior, context limits, timeouts and cold starts. The 80 GB GPU in the prepared plan is an initial unquantized sizing estimate, not a measured requirement. Check current official pricing, hardware availability and total cost before committing paid capacity; honor the user's actual hosting authorization and budget.
Do not run paid calls automatically on app startup, notebook opening or tests. Missing configuration returns a truthful unavailable state. Explicitly invoked live smoke tests use fictional data first.

6. CONNECT RETRIEVAL AND CHAT
Frontend -> Backend session/ownership -> persist question/job -> embed query -> filter allowed private documents and applicable approved references -> lexical/dense search and context expansion -> internal model service with authorized LlmContext -> hosted Qwen -> validate -> persist assistant message -> UI/source viewer.
Use bounded context with definitions, adjacent conditions, exclusions and table context. The chat model receives selected TEXT, not vectors. Resolve document EvidenceRefs against canonical Page text with exact document/version/page/quote checks. Keep benefit and action IDs restricted to supplied context.
Preserve hallucination mitigation: no usable pages means deterministic abstention without a model call; no citations means controlled insufficient-evidence wording and cleared benefit matches/actions; a follow-up question cannot authorize an unsupported assertion. Retain one repair maximum and reject fabricated citations. Strengthen prompts around unsupported claims, conflicts, dates/amounts/quantities and conditions. Exact quotes do not prove semantic entailment; measure real claim accuracy separately.

7. HANDLE THE REFERENCE CORPUS AS ITS OWN GATED TASK
Legal kit candidates remain inactive until reviewed. Parse machine-readable laws structurally, review exact source/version/jurisdiction/effective period/authority/scope, preserve definitions/exceptions/cross-references, and rebuild Qwen-aware chunks with exact source mappings. Legacy chunk hashes are parent hashes, and transformed whitespace prevents some exact substring matches. Historical MiniLM token counts are not Qwen limits.
Keep public reference sources separate from private user ownership. Never fabricate a page to fit an XML/HTML law into document EvidenceRef. Agree the internal/public legal citation/context boundary before enabling legal answers. If the legal layer is not release-ready, clearly keep legal inference unavailable rather than fill gaps with model knowledge. Backend retains final deadline calculations and missing anchors remain unknown.

8. CONNECT THE REAL FRONTEND AND COMPLETE ITS FLOWS
Use back/front/apps/frontend/, not the standalone HTML integration screen. Build with NEXT_PUBLIC_API_MODE=http and a browser-reachable HTTPS Backend base URL. Rebuild after changing NEXT_PUBLIC variables. No HF, internal-service, database or Supabase secret may be NEXT_PUBLIC.
Ensure MSW/sample templates cannot intercept production requests or fabricate missing backend functionality. Preserve automatic no-login session creation if using isolated sessions; configure exact CORS origins/methods/headers including X-Demo-Session, Idempotency-Key and the version header.
Wire upload/progress/review, Vault, benefits/unknown usage, source previews, assistant/thread history, matching, cases/assessment/drafts/replies/outcomes, and reminders/settings to their real supported API operations. Preserve null values, no-benefit documents, version conflicts, bounded polling, retries, session expiry, unavailable models and deleted-source behavior. Do not use mock-mode E2E success as proof of real integration.

9. PREPARE AND DEPLOY THE SERVER COMPONENTS
Choose explicit hosting targets for Next.js, FastAPI Backend, separate durable worker, internal LLM API, model serving, PostgreSQL and private object storage. Reuse existing provider accounts/infra when available. Expose frontend/public Backend through HTTPS; keep the model-service port and secrets private.
Create reproducible builds/locks and environment templates, separate process credentials and volumes, persistent model/index assets, health AND dependency-readiness checks, worker supervision, startup warmup, timeouts, resource/batch/concurrency limits and cleanup. Liveness 200 does not prove DB/Storage/model readiness.
Configure a domain or platform HTTPS URL, production CORS, trusted proxy settings, secret management, migrations, backups, deployment version/model/index identity and rollback. Verify current hosting/tool versions and provider requirements from primary docs at execution time. Use Docker only if it is the chosen supported route; configured CI/managed builds are a valid alternative.
Prepare deployable artifacts and a concrete resource/configuration/cost plan before any necessary approval step. Do not ask again for actions already clearly authorized. If an account, secret, spending decision or DNS ownership blocks progress, name the exact missing prerequisite, explain why it is required and continue independent work. Never invent deployment URLs, secrets or successful provider calls.

10. ACCEPTANCE GATES AND HANDOVER
Run real frontend typecheck/build/unit tests and product Backend tests in compatible service-local environments. Run shared contract/fixture validation and preserve the slice regressions. Add integration tests for the chosen actual product schema and lifecycle.
Run real browser E2E in HTTP mode against real Backend/worker/storage and explicitly configured model inference:
- First open creates one automatic isolated session (or an explicitly approved synthetic shared-demo mode); refresh preserves the correct space.
- A real fictional PDF and a photo convert or return explicit review reasons; unsupported/corrupt/oversized files stop correctly.
- Supported no-date/no-benefit documents remain eligible; unrelated content and prompt injection cannot force acceptance or invented benefits.
- Source review leads to complete indexing, then a known question returns supporting text and a working source reference.
- Wrong-session, stale/deleted/unapproved and wrong-profile records cannot enter retrieval/context.
- No-evidence and model failures are honest; hallucination/interpretation/conditions/numeric accuracy are measured with reviewed expectations and counts.
- Chat history, worker restarts/leases, retries/idempotency, source deletion and historical citation invalidation work against actual services.
- Required benefit/case/draft/outcome/reminder flows work without invented usage, double counting or automatic external sending.
- HTTPS URL is reachable from another browser/device, build uses HTTP mode, all required services are supervised, dependency readiness is checked and rollback is documented.

Report PASS/FAIL/NOT RUN per gate and explain unresolved failures. A passing mock suite is not live-model accuracy or deployment proof. Finish with actual product/API URLs, deployed versions/model commits, reproducible run/deploy commands, migrations applied, source/index lifecycle, measured test results and remaining limitations. Do not claim completion while required product flows or live deployment checks remain unimplemented/unverified.
```
