Claimly legal corpus kit — current local handoff (2026-11-15)

ENTRY POINTS
Use ../README.md for the architecture and processing order.
The ONE implementation prompt is ../../parsing/RAG_TESTING_PROMPT.md.
This kit contains source snapshots and candidate derived text, not an approved legal index.
The user-upload admission policy and the curated public legal corpus have separate gates.

WHAT IS HERE
catalog/federal_sources.csv: 47 source bundles.
catalog/state_sources.csv: 510 state/topic rows across 50 states and DC.
corpus/federal: 247 CFR + 103 U.S. Code records; 627 legacy chunks.
corpus/states: 987 records; 1,250 legacy chunks; 69 downloaded catalog rows.
State text covers CA, FL, IL, MI, NC, OH, PA, TX, MD, SC, UT only, with uneven topic coverage.
362 cited state catalog rows have no downloaded text; 79 rows have no citation.
NY/GA are coverage gaps. No catalog row is a substitute for missing source text.
reports/local_audit.json is the reproducible current inventory/integrity/token report.
catalog/retrieval_source_plan.json selects 14 starter bundles and 3 external validation/guidance references.
Its entries are inactive candidates, not verified entitlements or automatic indexing approval.

PROVENANCE AND DATE LIMITS
Federal CFR snapshot: 2026-11-12. U.S. Code release point: 119-142.
987 state records have no version_date/release_point. California came from pubinfo_2025.zip.
276 records have a native effective_date; none have normalized effective intervals.
A fetch timestamp does not prove the text applied on a transaction/event date.
Retain raw effective_date/history fields and confirm transitions, repeal, amendments, operative dates,
exceptions, enforcement notes and court effects using primary sources before applying a rule.
The catalog official label is an earlier verification claim; this audit checks files, not current law.
Never promote model-high/model-medium/source/snippet/rule-only labels to legal authority automatically.
eCFR is government-maintained, but is an unofficial editorial compilation; distinguish it from CFR
publication editions and the underlying Federal Register amendment. Record publication status.

CHUNKS NEED REPROCESSING
Do NOT embed legacy chunks directly with MiniLM and silently truncate.
1,264 / 1,877 legacy chunks exceed 256 MiniLM tokens including special tokens; maximum 1,785.
text_sha256 in a legacy chunk is the PARENT section hash. Store new source_text_sha256 and
contextualized_text_sha256 separately. All parent section hashes currently validate.
403 legacy chunk bodies are not exact parent substrings because split_chunks changes whitespace.
Rebuild token-aware chunks from canonical section text with tested source spans or explicit mappings.
Preserve definitions, exceptions, cross-references and neighboring clauses; count contextual headers.
Eight repeated-text groups are recorded in the audit. Distinct legal sections can share wording;
preserve citation aliases and distinguish true duplicates from separate authorities.
Do not invent PDF pages or EvidenceRef offsets for HTML/XML law records.

PROCESSING
Parse XML/HTML structurally; do not OCR machine-readable law. Docling remains the PDF/image path.
Keep raw bytes and provenance. Normalize sections deterministically, add exact pinpoint/subsection IDs,
review applicable versions, then create short embedding chunks linked to fuller parent sections.
Use separate document and legal collections. Filter authorized documents and applicable legal sources
before ranking. A source may be valid for historical retrieval without being current law.
Terms/policies from a merchant are another source class and need merchant/product/date applicability;
they are not statutes and must not override applicable law by prompt ordering.
Use real primary text only. Fictional rule fixtures belong in an isolated test namespace.

REPRODUCE OFFLINE AUDIT (run from workspace root)
services/llm/.venv/bin/python -B services/llm/rag/claimly_legal_corpus_kit/scripts/audit_corpus.py --tokenizer services/llm/parsing/.models/tokenizer --output services/llm/rag/claimly_legal_corpus_kit/reports/local_audit.json
No network/model generation is invoked. The tokenizer option uses installed tokenizers only.

DOWNLOADERS AND HISTORICAL MATERIAL
Keep downloaders, raw snapshots, CA bulk members, source URL sidecars, TLS certificate, CSV catalogs
and reports for rebuilding/provenance. Do not delete them as caches.
Downloader refreshes are explicit maintenance actions; do not run the full corpus by default.
A filtered download_states.py run writes a subset to its output: use a NEW output directory,
never the preserved corpus/states directory. Download success and keyword checks do not prove completeness.
catalog_build/ reconstructs the ORIGINAL seed catalog; never run it over the verified CSV catalog.
catalog/catalog_stats.json is refreshed from current CSV data; local_audit.json is current coverage.
reports/RUN_REPORT_RU.txt preserves the original collection report, not a new legal review.
catalog/compliance_notes_for_claimly_RU.txt is historical internal team material; exclude it from RAG.
The old README and PHASE2 prompt were removed; see reports/cleanup.json for the cleanup record.
