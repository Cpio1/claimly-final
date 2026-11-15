// Claimly on Railway — Infrastructure as Code DRAFT (not applied).
//
// Review with `railway config plan` BEFORE any `railway config apply`; applying creates billable
// resources (3 services, PostgreSQL, a bucket). Secrets are never written here: preserve() keeps
// values you set in the Railway dashboard (Variables tab). Connect the GitHub repo per service in
// the dashboard (or add `source: github("<owner>/<repo>")`), then set the variables listed below.
//
// Unverified DSL points (Railway reference docs, 2026-11): concatenated variable references and
// bucket env field names are not documented for the TS DSL. Each is written in Railway's standard
// ${{service.VAR}} reference syntax; confirm in the plan output, or set them in the dashboard.
import { bucket, defineRailway, postgres, preserve, project, service } from "railway/iac";

export default defineRailway(() => {
  const db = postgres("postgres");
  const originals = bucket("claimly-originals"); // Railway Buckets are private (no public URLs)

  const llm = service("llm", {
    // Private only: no `domains`. Reached at http://llm.railway.internal:8001 from the worker.
    env: {
      RAILWAY_DOCKERFILE_PATH: "services/llm/Dockerfile",
      PORT: "8001",
      LLM_SERVICE_TOKEN: preserve(),          // random ≥32 bytes; same value on worker
      HF_TOKEN: preserve(),                   // HF token with access to YOUR protected endpoints
      MODEL_BASE_URL: preserve(),             // HF vLLM endpoint root or /v1 base (not a model page)
      HF_EMBEDDING_URL: preserve(),           // only if EMBEDDING_PROVIDER=hf_endpoint on the worker
      MODEL_NAME: "Qwen/Qwen3.8-27B",
      MODEL_TIMEOUT_SECONDS: "90",
      MODEL_INPUT_TOKENS: "24000",
      MODEL_OUTPUT_TOKENS: "2048",
    },
    healthcheck: "/health",
    healthcheckTimeout: 120,
  });

  const shared = {
    DATABASE_URL: db.env.DATABASE_URL,
    STORAGE_BACKEND: "s3",
    S3_ENDPOINT: "${{claimly-originals.ENDPOINT}}",
    S3_BUCKET: "${{claimly-originals.BUCKET}}",
    S3_REGION: "${{claimly-originals.REGION}}",
    S3_ACCESS_KEY_ID: "${{claimly-originals.ACCESS_KEY_ID}}",
    S3_SECRET_ACCESS_KEY: "${{claimly-originals.SECRET_ACCESS_KEY}}",
    S3_ADDRESSING_STYLE: "virtual",
    FRONTEND_ORIGINS: "https://claimly-final.vercel.app",
    DEMO_SESSION_TTL_HOURS: "168",
    SOURCE_REVIEW_MODE: preserve(),           // operator (default) or user_confirmation — owner decision
  };

  const api = service("api", {
    env: {
      ...shared,
      RAILWAY_DOCKERFILE_PATH: "back/services/backend/Dockerfile.api",
      FORWARDED_ALLOW_IPS: "*",               // only the Railway edge can reach the container
      SCHEDULER_SECRET: preserve(),           // Bearer secret for POST /internal/v1/reminders/dispatch
    },
    preDeploy: "python -m app.migrate",       // forward-only, idempotent; recorded in claimly.schema_migrations
    healthcheck: "/health",
    healthcheckTimeout: 60,
    // Public HTTPS: generate a Railway domain (or add `domains: ["api.<your-domain>"]`).
  });

  const worker = service("worker", {
    env: {
      ...shared,
      RAILWAY_DOCKERFILE_PATH: "back/services/backend/Dockerfile.worker",
      LLM_BASE_URL: "http://${{llm.RAILWAY_PRIVATE_DOMAIN}}:8001",
      LLM_SERVICE_TOKEN: preserve(),
      EMBEDDING_PROVIDER: preserve(),         // hf_endpoint (needs HF_TOKEN+HF_EMBEDDING_URL) or local
      HF_TOKEN: preserve(),
      HF_EMBEDDING_URL: preserve(),
      JOB_LEASE_SECONDS: "1200",
      QUARANTINE_HOURS: "72",
    },
    // No public domain, no healthcheck path: a supervised background process (restart on failure).
  });

  return project("claimly", { resources: [db, originals, llm, api, worker] });
});
