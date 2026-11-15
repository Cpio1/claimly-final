# Claimly internal LLM service (stateless; no DB/Storage credentials). Build context: repository root.
#   docker build -f services/llm/Dockerfile -t claimly-llm .
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY services/llm/requirements-runtime.lock.txt services/llm/requirements-runtime.lock.txt
RUN pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu && pip install -r services/llm/requirements-runtime.lock.txt
COPY Claimly_Three_Parts/contracts/ Claimly_Three_Parts/contracts/
COPY services/llm/app/ services/llm/app/
COPY services/llm/parsing/ingestion_lab.py services/llm/parsing/prefetch_models.py services/llm/parsing/model-assets.lock.json services/llm/parsing/
COPY services/llm/rag/runtime.py services/llm/rag/runtime.py
COPY services/llm/hf-models.lock.json services/llm/hf-models.lock.json
COPY services/llm/check_hf.py services/llm/check_hf.py
COPY services/llm/.hf-models/ services/llm/.hf-models/
COPY services/envfile.py services/envfile.py
# One-time public Docling/RapidOCR asset download at BUILD time, verified against model-assets.lock.json.
# No model weights for Qwen chat are downloaded; no paid inference runs during build or startup.
RUN cd services/llm/parsing && python prefetch_models.py
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
RUN useradd --system --uid 10001 claimly && chown -R claimly /app
USER claimly
EXPOSE 8001
# Private only: bind :: for Railway's IPv6 private network; never attach a public domain.
CMD ["sh", "-c", "exec python -B -m uvicorn services.llm.app.main:app --host :: --port ${PORT:-8001} --no-access-log"]
