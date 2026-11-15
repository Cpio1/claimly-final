# Finalized Stage 1 entry points

- **[Final report and navigable architecture](FINAL_STAGE_1.md)** — stage scope, measured outcomes, current-date sample findings, cleanup and step-by-step RAG plan.
- **[Next-agent RAG testing prompt](RAG_TESTING_PROMPT.md)** — copy-ready notebook implementation/tuning task.
- **[Verified RAG handoff](rag-handoff/README.md)** — 20 checkpoints; 12 default-active source groups / 13 chunks.
- **[Uploaded-sample notebook](generated_test_review.ipynb)** and `generated_test_review.html` — current-date samples, source/OCR issues and exclusion reasons.
- Main `parsing_tests.ipynb` sections 13–14 contain the same sample/closing evidence. Existing reviews are preserved in `manual_reviews.json` and the review-results views.

The stage is finalized as a local notebook/export experiment, with review failures explicit; production, semantic retrieval, legal/rules reasoning and chatbot implementation remain later work.

---

# Docling parsing lab (Phase 1)

Open `parsing_tests.ipynb` with the **Claimly Docling** kernel. It is executed and contains the PDF/JPEG conversion, review gate, JSON reload, canonical evidence, and chunk inspection results. The earlier direct-model notebook is preserved byte-for-byte as `.local/archive/parsing_tests.legacy.ipynb`.

## Reproduce

Run from the workspace root:

```sh
python3 -m venv services/llm/.venv
services/llm/.venv/bin/python -m pip install -r services/llm/parsing/requirements.lock.txt
services/llm/.venv/bin/python services/llm/parsing/prefetch_models.py
services/llm/.venv/bin/python -m ipykernel install --user --name claimly-docling --display-name 'Claimly Docling'
services/llm/.venv/bin/python -m pytest services/llm/parsing/test_ingestion_lab.py -q
services/llm/.venv/bin/python services/llm/parsing/run_lab.py --output runs/final
```

The lock records the installed Python 3.13/macOS ARM environment. Other platforms may need different platform wheels. Docling is pinned at 2.150.1, RapidOCR at 3.10.0, and ONNX Runtime at 1.32.0. The user-provided `docling-main/` source checkout declares the same Docling version; the environment uses the pinned wheel rather than an editable install. That checkout is a read-only API reference.

Prefetch explicitly downloads local layout/table/English OCR models and the tokenizer, verifies `model-assets.lock.json`, and records resolved versions. Conversion uses offline Hugging Face settings. No paid calls, embedding vectors, agent framework or vector database are used. Tokenization alone is not an embedding.

To run one case or an explicit retry:

```sh
services/llm/.venv/bin/python services/llm/parsing/run_lab.py --case mixed_pdf --output runs/mixed-check
services/llm/.venv/bin/python services/llm/parsing/run_lab.py --case exif_rotated --force-full-page-ocr --output runs/explicit-ocr-retry
```

A retry gets a different processing identity. It does not silently replace the standard configuration. The normal batch is bounded to the 55 manifest cases; it never scans all 5,000 images for OCR.

`build_fixtures.py` can recreate authored fixtures and the initial manifest. **It overwrites the manifest**, so preserve any human-reviewed labels before using it. `prepare_notebook.py` regenerates notebook cells and clears executed outputs; do not run it merely to open the notebook.

## Files and responsibilities

- `ingestion_lab.py`: notebook helpers for validation, orientation preparation, standard conversion, quality/relevance checks, canonical source mappings, review and immutable checkpoint export.
- `evaluation_manifest.json`: sorted one-per-folder docs-sm smoke sample plus fictional coverage. Labels are agent visual-review proposals or fixture-author expectations, not human-reviewed labels. Unreviewed cases stay unscored.
- `model-assets.lock.json`, `requirements.lock.txt`: local model/tokenizer hashes and resolved package pins.
- `runs/final/run_report.json`: complete per-case measured outcomes, timings, warnings, source checks, admission, and held-out metrics with denominators.
- `FINAL_STAGE_1.md`: readable results, unresolved cases and scope limits.
- `runs/*/diagnostics/`: rejected/review/invalid diagnostics, separated from accepted conversion artifacts.
- `runs/*/accepted/<document_id>/<version>/<processing_hash>/`: reviewed internal Docling JSON, manifest, canonical pages, source-linked JSONL chunks, and page images.

The original bytes stay unchanged in `docs-sm/` or `fixtures/`. Original photos are never overwritten by EXIF normalization. Accepted JSON does not replace the original.

## Acceptance and review

The content-only baseline is intentionally limited: supported title plus substantive terms, recognized unrelated content rejection, otherwise review. It does not use filename, folder, category hints or evaluation labels. Embedded model instructions trigger review. It is not a production semantic classifier.

An export requires successful conversion, complete page/provenance checks, no conversion warnings, relevant content, and a quality review bound to both the original SHA-256 and canonical conversion hash. A review cannot override semantic rejection or conversion/mapping problems. Real-source review is manual. Fictional fixtures can use an explicit all-authored-passages/header/footer quality check. A missing due date or absent benefits does not block a supported bill. No field-extraction output or Vault row is invented.

Canonical offsets map only to the deterministic `claimly-pages-v2` strings. Text character spans are checked; body and furniture are preserved with layer annotations. Tables use an explicit row-major tab/newline representation. A multi-page table without exact page/cell mapping requires review. Chunk metadata names whole source items and their page/box references; it does not pretend transformed or contextualized chunk text is an exact page substring.

Checkpoints are immutable per processing identity and integrity-checked on reuse. There is no active index in this milestone, so update/deletion/session lifecycle behavior is **not implemented or validated**. Backend retains ownership of production acceptance, storage, identity, authorization, indexing and cleanup. Shared contracts are unchanged.

## Before production approval

Human-review expected labels and fix unresolved conversion/relevance cases; add genuine phone photographs and broader realistic consumer documents; evaluate a stronger semantic classifier and blind held-out outcomes; tune the chunk budget on longer clauses/tables; test later retrieval/session/version boundaries. Text-model field extraction remains a separate branch from this notebook. See `DOCLING_PLAN.md`, `FINAL_STAGE_1.md`, and [the current LLM service guide](../README.md) for scope and integration limits. Earlier planning notes are retained in the ignored local archive.

Official APIs were checked against the local source and [pipeline options](https://docling-project.github.io/docling/usage/advanced_options/), [chunking](https://docling-project.github.io/docling/concepts/chunking/), and [serialization](https://docling-project.github.io/docling/_generated/examples/serialization/).

## Manual source / text / token review

Open `manual_review.html`, or expand section 11 of `parsing_tests.ipynb`. Both show 12 selected cases with raw originals, complete canonical text, MiniLM token counts/pieces, conversion warnings and experimental relevance decisions. The HTML also lets you record and download manual reviews without changing the evaluation manifest or accepting documents. Paths are relative.

Regenerate only the diagnostic sample (11 corpus images plus one fictional bill):

```sh
services/llm/.venv/bin/python services/llm/parsing/review_gallery.py
```

Use `--reuse-data` to rebuild the HTML from saved diagnostic output without OCR. Rejected/review source text stays under `runs/manual-review/`; it is never exported as ordinary retrieval chunks. Tokens are local MiniLM WordPiece tokens, excluding special tokens, not billed API/image tokens. Originals are unchanged.

## Completed human reviews

`manual_reviews.json` preserves the exact 12-review browser export. `review_results.html` and the executed `review_results.ipynb` show labels, readability, verbatim notes, predictions, and follow-up questions. The main notebook contains the same comparison in section 12. The current comparison has 5 matching predictions and 7 differences; reviews were made with predictions visible, so these are descriptive counts, not blind held-out accuracy.

`manual_review_notes.json` records the user's downstream laws/rules/terms/consumer-protection clarification for deadline assessment. Printed dates and later rule-derived deadline candidates remain distinct; Backend retains final calculations. No external rules corpus or legal-inference branch was implemented here.

To rebuild the review reports after updating the exported review file:

```sh
services/llm/.venv/bin/python services/llm/parsing/review_results.py --reviews services/llm/parsing/manual_reviews.json
```

The import validates source identities and SHA-256 hashes, preserves notes and labels, and restores submitted selections in the HTML. It does not merge labels into the evaluation manifest, change classifier rules, accept uploads, or index documents. The report flags OCR-only relevance explanations and readability/relevance confusion for reconciliation before scoring or tuning. Changed review exports retain a timestamped previous copy.
