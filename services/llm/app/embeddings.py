"""Provider-neutral embeddings for Qwen/Qwen3-Embedding-0.6B.

EMBEDDING_PROVIDER selects the execution:
- ``hf_endpoint`` (default): the existing dedicated HF TEI endpoint client (HFClient.embed).
- ``local``: in-process CPU/MPS inference with pinned local weights (transformers + torch).

Both produce the same contract: L2-normalised 1024-d vectors, query instruction prefix only for
queries, no truncation (inputs over the token budget are rejected), and an ``embedding_identity``
that changes whenever the model, revision, provider, pooling or serializer changes so stored
vectors from another identity are never mixed into retrieval.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from functools import cached_property
from pathlib import Path

from .contracts import Failure
from .hf import QUERY_INSTRUCTION, HFClient, TokenBudget


def make_embedder(settings, *, transport=None, budget=None):
    provider = os.getenv('EMBEDDING_PROVIDER', 'hf_endpoint').strip().lower()
    if provider == 'local':
        return LocalQwenEmbedder(settings, budget=budget)
    if provider != 'hf_endpoint':
        raise Failure('AI_NOT_CONFIGURED', 'EMBEDDING_PROVIDER must be hf_endpoint or local.', 503)
    return HFClient(settings, transport=transport, budget=budget)


class LocalQwenEmbedder:
    """Last-token pooling with left padding, as specified for Qwen3-Embedding; fp32 on CPU."""

    provider = 'local-transformers'

    def __init__(self, settings, *, budget=None, model_dir=None, weights_sha256=None, batch_size=None):
        self.settings = settings
        self.budget = budget or TokenBudget(settings)
        self.model_dir = Path(model_dir or os.getenv('EMBEDDING_MODEL_PATH', '') or settings.embedding_tokenizer)
        self.weights_sha256 = (weights_sha256 or os.getenv('EMBEDDING_WEIGHTS_SHA256', '')).strip().lower()
        self.batch_size = int(batch_size or os.getenv('EMBEDDING_BATCH_SIZE', '8'))
        self.device_name = os.getenv('EMBEDDING_DEVICE', 'cpu')
        self._lock = threading.Lock()

    @property
    def embedding_identity(self):
        s = self.settings
        if not re.fullmatch(r'[a-f0-9]{40}', s.embedding_revision):
            raise Failure('AI_NOT_CONFIGURED', 'Pin the embedding revision to the commit in hf-models.lock.json.', 503)
        if not re.fullmatch(r'[a-f0-9]{64}', self.weights_sha256):
            raise Failure('AI_NOT_CONFIGURED', 'Set EMBEDDING_WEIGHTS_SHA256 for the pinned local embedding weights.', 503)
        config = {'model': s.embedding_model, 'revision': s.embedding_revision, 'weights_sha256': self.weights_sha256,
                  'provider': self.provider, 'dimension': s.embedding_dimension, 'normalization': 'l2',
                  'pooling': 'last_token', 'query_instruction': QUERY_INSTRUCTION,
                  'serializer': 'claimly-qwen-page-spans-v1', 'chunk_tokens': s.chunk_tokens}
        return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()

    @cached_property
    def _model(self):
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError:
            raise Failure('AI_NOT_CONFIGURED', 'Install torch and transformers for EMBEDDING_PROVIDER=local.', 503) from None
        weights = self.model_dir / 'model.safetensors'
        if not weights.is_file():
            raise Failure('AI_NOT_CONFIGURED', 'Prefetch the pinned embedding weights (model.safetensors) before indexing.', 503)
        self.embedding_identity  # requires pinned revision and weight hash
        digest = hashlib.sha256()
        with weights.open('rb') as handle:
            for block in iter(lambda: handle.read(8 * 1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != self.weights_sha256:
            raise Failure('AI_NOT_CONFIGURED', 'Local embedding weights do not match EMBEDDING_WEIGHTS_SHA256.', 503)
        config = json.loads((self.model_dir / 'config.json').read_text())
        if config.get('hidden_size') != self.settings.embedding_dimension:
            raise Failure('AI_NOT_CONFIGURED', 'Local embedding config dimension does not match the pinned profile.', 503)
        tokenizer = AutoTokenizer.from_pretrained(self.model_dir, local_files_only=True, padding_side='left')
        model = AutoModel.from_pretrained(self.model_dir, local_files_only=True, torch_dtype=torch.float32)
        model.eval().to(self.device_name)
        torch.set_num_threads(max(1, int(os.getenv('EMBEDDING_THREADS', str(os.cpu_count() or 1)))))
        return torch, tokenizer, model

    def embed(self, texts, *, query=False):
        self.embedding_identity
        prepared = [('Instruct: ' + QUERY_INSTRUCTION + '\nQuery: ' + t) if query else t for t in texts]
        if not prepared:
            return []
        if any(self.budget.embedding_count(t) > self.settings.chunk_tokens for t in prepared):
            raise Failure('VALIDATION_ERROR', 'Embedding input exceeds the configured token budget; no truncation was performed.')
        torch, tokenizer, model = self._model
        out = []
        with self._lock, torch.inference_mode():
            for start in range(0, len(prepared), self.batch_size):
                batch = tokenizer(prepared[start:start + self.batch_size], padding=True, truncation=False, return_tensors='pt')
                batch = {k: v.to(self.device_name) for k, v in batch.items()}
                hidden = model(**batch).last_hidden_state
                # Left padding: the final position holds each sequence's last real token.
                pooled = torch.nn.functional.normalize(hidden[:, -1].float(), p=2, dim=1)
                out.extend(pooled.cpu().tolist())
        for vector in out:
            if len(vector) != self.settings.embedding_dimension or any(not math.isfinite(x) for x in vector):
                raise Failure('INVALID_LLM_OUTPUT', 'Local embedding produced an invalid vector.', 502)
        return out
