# Claimly parsing Space: implementation and validation

Build a bounded parsing demonstration, using the existing Stage 1 converter. Follow
the project AGENTS.md and query graphify before exploring more source files.

**Hosting constraint observed:** the account cannot create a free ZeroGPU Space
until it is 30 days old (HF returned HTTP 402). The live deployment therefore uses
the free Static SDK and `browser/AGENTS.md`. The Docling bundle below is prepared
for a future eligible account; do not imply it is the deployed browser engine.

## Implementation

- Reuse `../ingestion_lab.py` byte-for-byte through `build_release.py`; do not fork
  validation, OCR, canonical serialization or the quality gate into the UI.
- Accept PDF/JPEG/PNG bytes, at most 10 MiB and 25 PDF pages. Preserve input bytes;
  apply EXIF orientation only to the processing/preview copy. Reject unsupported,
  corrupt, encrypted and empty sources explicitly.
- Run standard Docling on CPU with RapidOCR ONNX and table structure. Reuse one
  converter, serialize work, limit the queue and report actual elapsed time.
- Preload pinned public layout/table weights at Space build time. Bundle only the
  three hash-verified public RapidOCR assets. Resolve models offline at runtime;
  an absent/mismatched asset must fail startup rather than trigger a download.
- Use Gradio managed SDK packages. On a free account use the documented ZeroGPU
  CPU-only pattern: register one private, unused GPU marker; parsing never enters
  a GPU reservation. Never select hourly billed hardware or call paid inference.
- Treat outputs as inspection artifacts. Conversion success does not establish
  relevance, source approval, field accuracy, or eligibility. Do not populate a
  Vault, index documents, infer benefits/deadlines, or add an approval bypass.
- Show original-page previews beside plain canonical text. Expose quality reasons,
  page coverage, exact item/page spans and downloadable Docling/canonical JSON.
  Never render document text as executable HTML or Markdown.
- Use unique per-request artifact paths; keep documents out of logs and global
  state. Permit no user URLs or arbitrary server-file reads. Clean temporary input
  and output caches after one hour; no bucket or permanent upload storage.
- Publish only the explicit release allowlist and fictional fixtures. Exclude
  `.env`, private documents, docs-sm, reviews, checkpoints, databases, tokenizers,
  unrelated model weights, the product in `back/`, and local validation reports.

## Validation

1. Check syntax and release provenance locally; validate runtime on the Space.
2. Confirm the deployed revision, actual hardware and startup logs, not just RUNNING.
3. Discover `/parse_document` via the live Gradio client and exercise it. Check the
   output archive, source hash, page coverage, quality state, serializer identity,
   and every canonical item span. Confirm no inference-provider fallback.
4. Test a native warranty, scanned PDF, PNG, EXIF-rotated JPEG, table bill and
   two-page contract. Inspect dates/amounts/exclusions against the fictional source.
5. Test blank, corrupt, encrypted, empty, unsupported, over-10-MiB and over-25-page
   files. Invalid files must return no parsed content or downloadable archive;
   blank/incomplete documents must remain review-required.
6. Test a misleading filename and embedded instructions. They may be transcribed,
   but can never authorize admission, invented fields or actions.
7. Call through two independent clients. Each result must have unique artifact
   paths and its own source hash/text. Clear stale outputs after errors.
8. Inspect desktop/mobile UI and source previews. Record the real live results and
   unresolved failures separately from existing mocked integration-test results.
9. Run `graphify update .` after code changes, AST-only and without paid calls.

Reference skill: https://github.com/huggingface/skills/tree/main/skills/huggingface-spaces
