# Claimly upload/chat Backend

See [the integration guide](../llm/README.md) for setup, deployment, source review, exact contract scope and verification limits.

Run from the workspace root. Backend owns sessions, storage, durable jobs, admission and retrieval; the LLM service remains stateless. PostgreSQL/Supabase is the deployment path; `--local` explicitly selects SQLite/private local storage for development.
