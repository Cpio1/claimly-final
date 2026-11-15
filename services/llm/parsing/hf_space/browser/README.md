---
title: Claimly Document Parser
emoji: 📄
colorFrom: blue
colorTo: indigo
sdk: static
app_file: index.html
short_description: Parse PDFs and images privately in your browser
tags:
  - document-parsing
  - ocr
  - pdf
---

# Claimly Document Parser

A free browser demo for PDF/JPEG/PNG parsing. Native PDF text uses PDF.js; scanned
pages and images use Tesseract.js English OCR. Original pages, canonical text,
source locations, quality diagnostics and a downloadable JSON report stay in the
browser. No uploaded document bytes are sent to a parsing server or saved remotely.
Public OCR engine/language files are downloaded when OCR is first used.

**This live browser demo does not run Docling.** Hugging Face rejected this account's
free ZeroGPU hosting because the account is under 30 days old. A separate Docling
Gradio release is prepared in the Claimly workspace for eligible server hosting.
The two engines have different layout/table/OCR behavior; this is not a parity test.

## Behavior and limits

- Actual PDF/JPEG/PNG bytes, 10 MiB, 25 PDF pages. Password-protected PDFs are rejected.
- Native text is preferred. Any page containing raster images is OCRed in full so
  that a native header cannot mask an unread scanned body. OCR needs initial public
  runtime/language downloads and can be slower or less accurate on small devices.
- Table text is preserved for inspection; browser OCR does not reconstruct Docling
  table cells. Compare dates, amounts and exclusions to the original.
- Offsets map into each page's canonical text. Native PDF transforms and available
  OCR boxes accompany spans. They are not offsets into the original file bytes.
- Conversion success never grants relevance or admission. Relevance is unevaluated,
  source review is required, and no Vault/index/benefits/legal answers are produced.
- Clear and new uploads discard in-memory results and revoke generated download
  URLs. No document content is stored in localStorage, a backend, or analytics.

Only fictional Claimly fixtures are bundled. The limits do not make browser OCR a
security boundary for production document admission. Existing Backend/source-review
contracts continue to govern the real Claimly pipeline.

See [AGENTS.md](AGENTS.md) for implementation/validation instructions and
the generated release file `THIRD_PARTY.md` for exact pinned library and asset
sources. The release builder creates that file alongside the deployed app.
