# Stage 1: text PDF to a populated Vault row

> Current plan: [Docling ingestion: raw file to JSON and retrieval-ready chunks](../services/llm/parsing/DOCLING_PLAN.md). The sections below retain the earlier text-PDF-only proposal and the n8n reference review; the current plan includes scan/photo OCR and retrieval preparation.

## Scope and reference hierarchy

Stage 1 accepts PDFs with usable text, extracts evidence-backed fields, and returns a result that Backend can save and display as a Vault row. Image-only scans and uncertain mixed pages are detected and deferred for a later OCR stage. Chat, retrieval-based question answering, and claims workflows are outside this stage.

Authoritative requirements:
- [LLM specification](03_LLM_TZ.txt), especially sections 1–4 and 8–10.
- [Shared architecture](00_START_HERE.txt).
- [LLM contract](contracts/llm.openapi.json) and [Backend contract](contracts/backend.openapi.json), version 2.0.0.
- [Product specification](99_Product_MVP_Source.txt), sections 6.2–8.
- [Extraction fixture](fixtures/llm_extraction.json) and [Entry fixture](fixtures/entry.json).

Implementation reference designated by the user:
- [n8n-rag-main](n8n-rag-main/README.md).
- [Hosted ingestion example](n8n-rag-main/using_apis/app.py).
- [Local ingestion example](n8n-rag-main/local-rag/app.py).

Use this directory for ingestion patterns. Claimly's specifications and contracts govern behavior and interfaces.

## What the reference actually implements

The hosted example downloads Google Drive bytes, decodes them as UTF-8, splits text into overlapping character chunks, generates embeddings, and stores vectors in Pinecone. It tracks file modification times and vector IDs in processed_files.json.

The local example reads UTF-8 text files from documents/, generates embeddings with SentenceTransformer, and stores chunks in ChromaDB. Its file listing explicitly selects .txt files.

Both examples illustrate ingestion, segmentation, source identity, change tracking, and deletion cleanup. The inspected directory contains Python examples; no exported n8n workflow JSON appears in its file inventory.

## How to adapt the patterns

| Reference pattern | Stage 1 application |
| --- | --- |
| Download/read source | Receive validated PDF bytes from Backend. |
| process_file orchestration | Separate validation, page inspection, text extraction, field extraction, validation, and result assembly. |
| Chunking with overlap | Preserve canonical pages first. Add page-aware chunks with exact offsets only when needed. |
| file_id/file_name metadata | Use Backend-issued document_id, document_version, and page numbers; keep filenames as labels. |
| Processed-file tracking | Backend owns durable jobs and idempotency. Include source version and extraction configuration in internal processing identity. |
| Update/delete lifecycle | Reject stale results and remove or invalidate derived data when the source changes or is deleted. |

Embeddings, Pinecone, ChromaDB, Google Drive integration, and chat are outside Stage 1 requirements. Dependencies should be selected for the PDF-to-row flow independently.

## Important implementation gaps

- UTF-8 decoding does not parse PDF structure. Add real page-by-page PDF extraction.
- The reference has no scanned/native/mixed-page detector or OCR implementation.
- Its 500-character chunks with 100-character overlap carry no page references or character offsets.
- The hosted example stores only the first 200 characters of each chunk as text metadata. Claimly must preserve complete canonical page text.
- There is no structured field schema, exact-quote validation, or table-row projection in the ingestion examples.
- Per-chunk failures can still be followed by a processed-state write. Claimly should mark success only after required outputs validate and persist.
- File modification times and local JSON state are insufficient for durable, session-isolated production processing.

## Ordered delivery plan

1. Define the row projection: title, category, provider, subject, separate date meanings, amount/currency, and document review status. Agree on names for flexible facts; retain current DTOs.
2. Implement a local PDF inspection harness first. Validate signatures, 10 MB size, 25-page limit, corruption, encryption, and processing bounds.
3. Extract every page using a PDF parser. Preserve page numbers and a stable canonical text representation. Keep original bytes available through Backend.
4. Inspect text quality and drawn image coverage per page. Distinguish usable native text, likely OCR overlays, image-only pages, mixed content, blank pages, and uncertain extraction.
5. Defer image-dependent or uncertain documents with clear review reasons. Preserve readable pages; do not label partial processing complete. Keep public document statuses within the existing enum.
6. Add a server-side text-model extraction adapter. Submit complete canonical pages within the context budget and request the existing ExtractionOutput, including facts, explicit benefit candidates, and review flags. Use null for unknown values. A missing key returns AI_NOT_CONFIGURED.
7. Validate schema, document/version/page references, exact quotes after whitespace normalization, dates, cents, and required evidence. Allow one model-output repair attempt. Retain duration/deadline rules; Backend calculates final dates and owns usage state.
8. Exercise the existing protected POST /internal/v1/extract using multipart metadata and file bytes. Keep parsing steps separately callable internally for key-free tests; no additional public endpoint is required by this plan.
9. Integrate Backend upload/job/storage and row display. Backend creates a draft Entry before document upload, assigns document identity, saves validated outputs transactionally, preserves user edits, and rejects stale results. The website calls Backend.
10. Validate with known text-PDF examples, missing and conflicting values, multi-page/column layouts, malformed files, repeated requests, and scan/mixed-page deferral. Inspect field meaning as well as quote existence.

## PDF type detection

Classify extractability per page. PDF filename, producer metadata, image presence, or one character-count threshold cannot establish origin or completeness.

Combine coherent text, replacement/garbled characters, reading order, text placement, and drawn image coverage. A full-page image plus a text overlay suggests previous OCR; selectable text alone does not establish native digital origin. Treat classification as a heuristic and keep an uncertain route.

For Stage 1, prioritize native text PDFs. A suspected scan, poor OCR overlay, or mixed-content document retains its original and explicit review reasons for the next stage.

## Acceptance

A known text PDF produces the expected row and documented benefit candidates with traceable facts. Missing values remain null; no usage balance or final legal deadline is invented. Retries do not duplicate rows or benefits. Scans are clearly deferred. Backend owns storage and sessions; the LLM service returns validated JSON.
