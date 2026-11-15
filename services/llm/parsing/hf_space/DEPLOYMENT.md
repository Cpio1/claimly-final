# Parsing demo deployment and verification

Space: https://huggingface.co/spaces/junglemvn/claimly-parsing-demo

- Visibility: **private**; sign into the `junglemvn` account to open it.
- SDK: **Static**, no compute hardware or inference endpoint.
- Verified application revision: `0735c19080e3129fb1edb4e7dfd07f6cc0d908de`.
- HF reported `RUNNING`. Static Spaces expose no container run logs; the logs
  command returned “No logs available”. Browser runtime checks were used instead.

## Hosting decision

The request to create a free ZeroGPU Gradio Space returned HTTP 402: the account
must be at least 30 days old or have PRO. No subscription, paid hardware, bucket
or paid inference was created. The free Static Space runs PDF.js 6.5.438 and
Tesseract.js/core 7.0.0 in the browser. It **does not run Docling**.

The parent `app.py`, `demo_engine.py`, `assets.py` and `build_release.py` retain a
prepared Docling Gradio variant. That variant copies the existing parser unchanged
and checks the existing Stage 1 model hashes. It has not been deployed or claimed
as verified on Hugging Face. No existing product code or shared contract changed.

## Source and reproducibility

The deployed source is `browser/`. Specific implementation and validation rules
are in `browser/AGENTS.md`; the server variant has separate parent instructions.

`build_static_release.py` assembles `.local/parsing-static-release/` from an
allowlist. Four pinned vendor files must already exist under its `vendor/` folder:

```text
https://cdn.jsdelivr.net/npm/pdfjs-dist@6.5.438/build/pdf.mjs
https://cdn.jsdelivr.net/npm/pdfjs-dist@6.5.438/build/pdf.worker.mjs
https://cdn.jsdelivr.net/npm/tesseract.js@7.0.0/dist/tesseract.min.js
https://cdn.jsdelivr.net/npm/tesseract.js@7.0.0/dist/worker.min.js
```

The builder records file hashes in `release-manifest.json`. Only five fictional
examples accompany the application; real uploads, docs-sm, private reviews,
checkpoints, secrets, database files and model weights are excluded.

```sh
services/llm/.venv/bin/python -B services/llm/parsing/hf_space/build_static_release.py
hf upload junglemvn/claimly-parsing-demo .local/parsing-static-release . --repo-type space --exclude '**/__pycache__/**'
hf spaces info junglemvn/claimly-parsing-demo --expand sdk,sha,private,runtime --format json
```

## Actual verification

The deployed private repository revision was fetched through a loopback-only QA
bridge. Credentials stayed in that server process. An isolated temporary Chrome
profile exercised those deployed bytes with the same pinned external OCR assets.
This verifies the deployed application code, not the private Hub login/iframe flow.

`reports/browser-verification.json`: **19 passed, 0 failed**:

- Native warranty text and exact exclusion wording.
- Real OCR of a scan PDF, PNG and EXIF-rotated JPEG.
- Table bill amount, no-date bill and both pages of a service contract.
- Blank-page review state; misleading filename and embedded instructions remain
  inspection text, with relevance unevaluated and admission not performed.
- Explicit reasons and no retained results for corrupt, encrypted, empty,
  unsupported, over-10-MiB and over-25-page files.
- Source SHA and every exported canonical text span checked.
- Independent browser-frame results, unique output URLs, Clear, and no document
  upload requests to the app origin.

`reports/browser-ui.json`: no uncaught JavaScript errors; no horizontal overflow
at desktop or 390-pixel mobile width. Desktop/source comparison and mobile
screenshots were visually inspected. Files are in `reports/` and are not deployed.

Measured fixture times in this test environment: native warranty 0.551 seconds;
scan PDF including first OCR load 3.619 seconds; PNG 0.736 seconds; rotated JPEG
0.755 seconds. These are observations for these synthetic files, not general
latency guarantees or held-out OCR accuracy measurements.

The existing parsing/backend suite was also rerun: **100 passed**, with existing
dependency deprecation warnings. Its provider mocks remain separate from the real
browser OCR checks above.

To repeat on this Mac, run `qa_proxy.py` with the installed HF CLI's Python
environment (requires huggingface_hub and httpx2), then run `validate_headless.py`
with the existing service Python environment (requires websockets). The bridge
binds only `127.0.0.1:8873`; the browser profile is temporary and separate from the
user's browser. Stop the bridge after validation.

## Limits

English browser OCR may misread amounts, dates and layout. It does not reconstruct
Docling table cells, classify relevance, extract benefits, approve a source, index
anything, or answer questions. Original-to-text review remains required. Native
PDF extraction and OCR have different representations and are labeled per page.
The existing Claimly Backend remains the production authorization/admission path.
