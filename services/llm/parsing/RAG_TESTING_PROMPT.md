# Next-chat RAG analysis prompt

The current full handoff is **[NEXT_CHAT_HANDOFF.md](../rag/NEXT_CHAT_HANDOFF.md)**. It supersedes the earlier retrieval-only/MiniLM implementation prompt. Its starter prompt is the single current invocation; the earlier prompt is preserved locally under `.local/archive/` for audit.

```text
Read services/llm/rag/NEXT_CHAT_HANDOFF.md, services/llm/README.md and services/backend/reports/verification.json. Follow AGENTS.md and query graphify before source browsing.

Trace the current upload-to-chat pipeline in code. Distinguish implemented behavior, explicit test mocks, missing live connections and recommendations. Analyze how to move from current HF embeddings + HF chat to local/application-server Qwen3-Embedding-0.6B + hosted Qwen3.8-27B, preserving source admission, exact citations, session isolation and existing contracts.

Start with an architecture/gap analysis and prioritized implementation/validation plan. No automatic paid calls, paid endpoint provisioning or secret disclosure. Leave back/ unchanged unless I explicitly request complete-product work. Preserve source documents, model assets and human reviews; reuse the implemented components.
```
