# RAG input handoff

Use `index_input_manifest.json` as the only default index allowlist. `default_active` selects one primary checkpoint per source group. There are 20 preserved approved experiment checkpoints (22 chunks); 12 default-active groups (13 chunks). Bill variants are withheld pending manual-review reconciliation; duplicate variants are robustness tests, not extra active documents. The uploaded certificate is active under the user-confirmed title-plus-period rule. The blank PNG and receipt with an OCR amount error remain excluded.

Run `finalize_stage.verify_checkpoint` to validate integrity and source spans without OCR. `retrieval_questions.json` supplies 12 source-grounded tuning checks with existing EvidenceRef shapes; it is not a blind held-out benchmark. Demo sessions are local test assignments only.

`sources/` preserves byte-identical originals locally and is ignored for Git by default. Checkpoints/page images provide reusable conversion evidence, but production must retain authorized originals in Backend private storage. The final stage report and `RAG_TESTING_PROMPT.md` define the next experiment.
