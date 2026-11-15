---
title: Claimly Document Parser
emoji: 📄
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 6.32.0
app_file: app.py
python_version: "3.12"
short_description: Inspect PDF and image text, tables and source provenance
startup_duration_timeout: 30m
tags:
  - docling
  - ocr
  - document-parsing
preload_from_hub:
  - docling-project/docling-layout-heron config.json,preprocessor_config.json,model.safetensors 8f39ad3c0b4c58e9c2d2c84a38465abf757272d8
  - docling-project/docling-models model_artifacts/tableformer/accurate/tableformer_accurate.safetensors,model_artifacts/tableformer/accurate/tm_config.json,model_artifacts/tableformer/fast/tableformer_fast.safetensors,model_artifacts/tableformer/fast/tm_config.json fc0f2d45e2218ea24bce5045f58a389aed16dc23
---

# Claimly Document Parser

Upload a PDF, JPEG or PNG and inspect canonical page text, tables and source
locations beside the original pages. Download the Docling document, canonical
mapping and conversion report in one ZIP. Examples are fictional test documents.

This demo runs **Docling + RapidOCR on CPU**. It makes no hosted-model requests,
creates no Vault entries and performs no semantic relevance classification,
benefit extraction, legal reasoning or source approval. A successful conversion
still requires comparison to the original. OCR can misread dates and amounts.

## Limits and temporary files

- 10 MiB per document; 25 PDF pages; PDF/JPEG/PNG only.
- Files are processed on this Space. Use fictional or redacted examples.
- Gradio upload/result files and request artifacts are cached temporarily, with
  periodic cleanup after one hour. Clear removes the displayed result; it does
  not promise immediate erasure of the server cache. No bucket is configured.
- Work is serialized to keep the shared CPU converter bounded. The first document
  may be slower; model assets are preloaded and hash-verified before requests.

## Reproducible release

From the Claimly workspace, run:

```sh
services/llm/.venv/bin/python -B services/llm/parsing/hf_space/build_release.py
```

The builder writes `.local/parsing-space-release/` from a strict allowlist. It
copies the original `ingestion_lab.py` unchanged as `claimly_parser.py`, records
its hash and includes only approved fictional examples and the three public OCR
assets already pinned by Stage 1. It never uploads the workspace as a whole.

The README pins build-time public layout/table downloads. `assets.py` reads only
the local HF cache and verifies every required file against the Stage 1 lock.
Missing assets fail startup. Models are not downloaded in upload handlers.

The free-account hosting target is `zero-a10g`, using the official CPU-only
pattern with a registered private GPU marker that is never called by parsing.
No hourly billed hardware, paid endpoint, inference token or database is needed.

## Live validation

For the Gradio variant, discover the deployed API with `gradio_client`, then
exercise `/parse_document` using the cases specified in AGENTS.md. Inspect the
JSON/ZIP contents as well as the response status; no Gradio deployment is claimed
until the account can host it and those live checks pass.

The current free Static Space uses `browser/`. Its isolated browser checks are in
`validate_browser.html` and `validate_headless.py`; `qa_proxy.py` retrieves the exact
private deployed revision for testing without sending credentials to the browser.
Test harnesses and reports are excluded from both deployment bundles.

See [AGENTS.md](AGENTS.md) for the specific implementation and validation rules,
and `THIRD_PARTY.md` for public model attribution. The generated release manifest
records exact source, dependency and artifact hashes.
