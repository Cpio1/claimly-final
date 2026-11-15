# Claimly LLM service

This folder contains the internal extraction/answer API, Docling parsing lab,
retrieval helpers, regulatory corpus preparation and the parsing Space source.
The product backend is `back/services/backend/`; its source is unchanged.
The duplicate backend, old combined launcher and obsolete planning documents
are preserved in the ignored `.local/archive/` folder.

## Components

| Path | Responsibility |
| --- | --- |
| `app/` | Stateless FastAPI API, model adapters, schema and citation validation |
| `parsing/` | PDF/JPEG/PNG validation, Docling/OCR, canonical text, review and checkpoints |
| `rag/runtime.py` | Exact page-span chunks and hybrid ranking over already-authorized candidates |
| `rag/claimly_legal_corpus_kit/` | Regulatory snapshots, source catalogs, integrity audits and preparation scripts |
| `rag/SUPERVISED_AGENT.md` | Evidence-first answering and explicit abstention instructions |
| `parsing/hf_space/` | Static browser demo and separately prepared Docling Space source |
| `hf-models.lock.json` | Pinned Qwen model revisions and tokenizer hashes |

Shared contracts remain in `Claimly_Three_Parts/contracts/`. No contract or
product backend change is required to start the LLM service itself.

## Run the internal API

From the repository root, use Python 3.13 and the service-local environment:

```sh
python3 -m venv services/llm/.venv
services/llm/.venv/bin/python -m pip install -r services/llm/requirements-runtime.lock.txt
cp services/llm/.env.example services/llm/.env
```

Set `LLM_SERVICE_TOKEN` to a random secret shared only with the backend HTTP
client. Set `HF_TOKEN`, `HF_EMBEDDING_URL` and `MODEL_BASE_URL` only when running
hosted inference. Do not put Supabase or database credentials in this service.
The launcher loads `services/llm/.env`; existing environment variables win.

```sh
services/llm/.venv/bin/python -B -m services.llm.run
```

The default address is `127.0.0.1:8001`. `GET /health` returns service status;
`degraded` is expected when hosted-model settings are absent. Health and startup
perform no model downloads, database access or inference. Model endpoints require
`Authorization: Bearer <LLM_SERVICE_TOKEN>` and fail closed without it.

## Backend interface

- `POST /internal/v1/extract`: multipart `file` and JSON `metadata` matching
  `ExtractRequest`. Returns the existing `ExtractionOutput` envelope. The optional
  `X-Claimly-As-Of` header supplies the relevance-check date.
- `POST /internal/v1/answer`: JSON `AnswerRequest` with authorized `LlmContext`.
  Returns `LlmAnswer` after schema, exact-quote and allowed-object checks.
- Backend owns source/session authorization, originals, review approval, durable
  jobs, indexing, retrieval filters, usage and final deadline calculations.
- The LLM service does not persist uploads or connect directly to Supabase.

The preserved backend currently accepts uploads and leaves AI jobs queued.
Its worker-to-LLM connection, approved-source retrieval and chat persistence
remain integration work. Starting this API does not enable those features.
The local retrieval helper also requires the caller to filter ownership,
version, scope and embedding profile before ranking.

## Models and assets

The current adapters call hosted Qwen3-Embedding-0.6B and Qwen3.8-27B endpoints;
local tokenizer files do not perform embedding inference. Revisions and hashes
are pinned in `hf-models.lock.json`; serving models must match them. Endpoint
URLs must be prediction URLs, not Hugging Face download pages.

Explicit setup downloads public assets:

```sh
services/llm/.venv/bin/python -B -m services.llm.prefetch_hf_tokenizers
services/llm/.venv/bin/python -B services/llm/parsing/prefetch_models.py
services/llm/.venv/bin/python -B -m services.llm.check_hf
```

`check_hf` without flags validates local assets and configuration only. Its
`--live` option invokes hosted inference and may incur charges; do not run it
without an approved inference budget. Missing assets/configuration are explicit
failures, with no sample-answer fallback. The Dockerfile packages only the LLM
code and unchanged contracts; model directories must be mounted separately.
Docker image execution and live hosted-model accuracy are not validated here.

## Parsing, regulations and evidence

Start with [the parsing guide](parsing/README.md), [Docling plan](parsing/DOCLING_PLAN.md)
and [Stage 1 measured report](parsing/FINAL_STAGE_1.md).
See [RAG preparation](rag/README.md) and [the current handoff](rag/NEXT_CHAT_HANDOFF.md).
The regulatory kit is candidate evidence pending jurisdiction, version,
effective-date, applicability and citation review. It is not an active legal
index or a reviewed training dataset. HTML/XML law must not be given invented
PDF page citations.

With no usable document pages, the answer path abstains without model inference.
Uncited model output becomes a controlled insufficient-evidence response.
Exact matching verifies quote resolution, not semantic entailment or legal
correctness; those require reviewed evaluations. This chat's weights cannot be
modified by processing the corpus.

## Validation

```sh
services/llm/.venv/bin/python -B -m pytest services/llm/tests services/llm/parsing/test_ingestion_lab.py -q -p no:cacheprovider
services/llm/.venv/bin/python -B Claimly_Three_Parts/contracts/validate_contracts.py
```

The API tests use explicit test-only providers and do not contact hosted models.
Earlier 100-test combined-backend results are historical; the removed demo
backend's tests and reports are retained with its archived source. The parsing
Space has a browser implementation; it is distinct from Docling execution.
