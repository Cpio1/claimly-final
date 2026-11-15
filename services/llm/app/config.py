"""Server-side configuration. Opening the app never downloads models or makes inference calls."""
from dataclasses import dataclass
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODEL_EMBED = 'Qwen/Qwen3-Embedding-0.6B'
MODEL_CHAT = 'Qwen/Qwen3.8-27B'

@dataclass(frozen=True)
class Settings:
    service_token: str = ''
    hf_token: str = ''
    embedding_url: str = ''
    chat_url: str = ''
    embedding_model: str = MODEL_EMBED
    chat_model: str = MODEL_CHAT
    embedding_revision: str = ''
    chat_revision: str = ''
    embedding_dimension: int = 1024
    timeout: float = 90
    input_tokens: int = 24000
    output_tokens: int = 2048
    chunk_tokens: int = 768
    embedding_tokenizer: str = str(ROOT / 'services/llm/.hf-models/embedding')
    chat_tokenizer: str = str(ROOT / 'services/llm/.hf-models/chat')
    docling_assets: str = str(ROOT / 'services/llm/parsing/.models/docling')

    @classmethod
    def env(cls):
        lock_path = ROOT / 'services/llm/hf-models.lock.json'
        lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
        return cls(
            service_token=os.getenv('LLM_SERVICE_TOKEN', ''),
            hf_token=os.getenv('HF_TOKEN') or os.getenv('MODEL_PROVIDER_API_KEY', ''),
            embedding_url=os.getenv('HF_EMBEDDING_URL', ''),
            chat_url=os.getenv('MODEL_BASE_URL', ''),
            chat_model=os.getenv('MODEL_NAME', MODEL_CHAT),
            embedding_revision=os.getenv('HF_EMBEDDING_REVISION', lock.get('embedding', {}).get('revision', '')),
            chat_revision=os.getenv('HF_CHAT_REVISION', lock.get('chat', {}).get('revision', '')),
            timeout=float(os.getenv('MODEL_TIMEOUT_SECONDS', '90')),
            input_tokens=int(os.getenv('MODEL_INPUT_TOKENS', '24000')),
            output_tokens=int(os.getenv('MODEL_OUTPUT_TOKENS', '2048')),
            chunk_tokens=int(os.getenv('EMBEDDING_CHUNK_TOKENS', '768')),
            embedding_tokenizer=os.getenv('EMBEDDING_TOKENIZER_PATH', str(ROOT / 'services/llm/.hf-models/embedding')),
            chat_tokenizer=os.getenv('CHAT_TOKENIZER_PATH', str(ROOT / 'services/llm/.hf-models/chat')),
            docling_assets=os.getenv('DOCLING_ARTIFACTS_PATH', str(ROOT / 'services/llm/parsing/.models/docling')),
        )
