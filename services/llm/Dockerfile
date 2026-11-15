FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY services/llm/requirements-runtime.lock.txt services/llm/requirements-runtime.lock.txt
RUN pip install --no-cache-dir torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r services/llm/requirements-runtime.lock.txt
COPY Claimly_Three_Parts/contracts/ Claimly_Three_Parts/contracts/
COPY services/llm/app/ services/llm/app/
COPY services/llm/parsing/ingestion_lab.py services/llm/parsing/ingestion_lab.py
COPY services/llm/rag/runtime.py services/llm/rag/runtime.py
COPY services/llm/hf-models.lock.json services/llm/hf-models.lock.json
COPY services/llm/check_hf.py services/llm/check_hf.py
COPY services/backend/ services/backend/
COPY services/envfile.py services/envfile.py
ENV PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1
CMD ["python","-B","-m","uvicorn","services.llm.app.main:app","--host","0.0.0.0","--port","8001","--no-access-log"]
