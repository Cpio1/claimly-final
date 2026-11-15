# Browser parsing demo: specific instructions

The account's free ZeroGPU creation was rejected because it is under 30 days old.
Deploy a free **Static** Space. Do not subscribe, provision paid compute or call
an inference provider. This is a browser implementation, not Docling execution.
Preserve the prepared Docling Gradio bundle in the parent directory.

## Recommended implementation

- Use pinned PDF.js for PDF rendering/native text and pinned Tesseract.js for
  English OCR. Vendor the JS workers; fetch only public OCR runtime/language assets.
  Document bytes stay in browser memory. Do not send bytes to any API, analytics,
  logger, bucket or external parser. Do not store document data in localStorage.
- Validate actual PDF/JPEG/PNG signatures, 10 MiB, 25 PDF pages, encrypted/corrupt
  files and decoded image dimensions. No silent page omission.
- Prefer native PDF text. If raster images are present or native text is sparse,
  OCR the complete page to avoid accepting a native header over an unread scan.
- Apply browser EXIF orientation to image decoding. Preserve source bytes and SHA.
- Derive exact offsets from the displayed canonical text, never PDF byte offsets.
  Keep native PDF transforms or OCR boxes with each source mapping. A null box is
  better than a fabricated one. Identify OCR-derived text and confidence clearly.
- Show conversion quality separately from relevance/admission. No source approval,
  Vault, embeddings, structured benefits, legal reasoning or automatic acceptance.
- Use textContent for all source/filename/error text. Revoke object URLs, clear
  result state on new inputs/errors, serialize parsing and terminate OCR on Clear.
- Display honest cold-load/progress and errors, support responsive keyboard UI,
  include fictional samples, downloadable JSON, and a plain-language engine note.
- Release only an allowlist of static code, pinned vendor assets, attribution and
  fictional examples. Exclude secrets, docs-sm, real uploads, reviews and model data.

## Required validation

1. Validate the deployed Space revision and load it in a real browser. Do not treat
   HTTP 200 or RUNNING as proof that workers/WASM/OCR function.
2. Parse a native warranty and verify its exact conditions/exclusions; parse a scan,
   PNG and EXIF-rotated JPEG using real OCR. Check table amounts and both contract
   pages. Record timings and known OCR discrepancies; do not claim Docling parity.
3. Download JSON. Verify source SHA, all expected pages, distinct native/OCR methods,
   every text[start:end] mapping and the explicit not-evaluated/not-admitted states.
4. Blank/unreadable pages require review. Corrupt, encrypted, empty, unsupported,
   over-10-MiB and over-25-page files must clear output and fail explicitly.
5. Misleading names and embedded instructions remain untrusted text and cannot
   create approval, benefits, actions or legal conclusions.
6. Inspect browser network requests to confirm document bytes are never uploaded.
   Use independent page sessions to check results and source hashes do not mix.
7. Inspect desktop/mobile screenshots, focus/labels, error recovery, Clear and
   download states. Fix runtime errors before reporting a working demo.
8. Save actual evidence in the local reports directory. Rebuild the graph AST after
   code changes. Publishing remains private unless the user requests sharing.
