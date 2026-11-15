"""Test rig. Explicit test doubles only: HF HTTP is an in-memory MockTransport and PDF text comes
from a native parser instead of Docling. The Backend API, worker, storage adapter, internal LLM API,
prompts and evidence/ID guards are the real implementations. No paid inference, no network."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from app.db import Database  # noqa: E402
from app.llm_client import HttpLlmClient  # noqa: E402
from app.main import create_app  # noqa: E402
from app.migrate import run as migrate  # noqa: E402
from app.settings import Settings  # noqa: E402
from app.storage import LocalStorage  # noqa: E402
from app.worker import Worker  # noqa: E402
from services.llm.app.config import Settings as LlmSettings  # noqa: E402
from services.llm.app.hf import HFClient  # noqa: E402
from services.llm.app.main import create_app as llm_app  # noqa: E402
from services.llm.app.processing import Processor  # noqa: E402

FIXTURES = ROOT / "services/llm/parsing/fixtures"
SERVICE_TOKEN = "test-service-token-" + "x" * 24


class Budget:
    def embedding_count(self, text):
        return len(text.split()) + 2

    def chat_count(self, messages):
        return sum(len(m["content"].split()) for m in messages) + 20


class NativeFixtureParser:
    """Test-only native PDF text; production always uses DoclingParser."""

    def parse(self, data, metadata):
        pages = [{"page": i, "text": p.extract_text(), "needs_review": False} for i, p in enumerate(PdfReader(BytesIO(data)).pages, 1)]
        return pages, {"passed": True}


def ref(payload_doc, page, quote):
    return {"document_id": payload_doc["document_id"], "document_version": payload_doc["document_version"], "page": page["page"], "quote": quote}


class Provider:
    """Mock HF TEI + chat endpoint. Returns contract-shaped JSON citing supplied text only."""

    def __init__(self):
        self.calls, self.mode, self.hook = [], "normal", None

    def chat_paths(self):
        return [body["messages"][0]["content"][:40] for path, body in self.calls if path.endswith("/chat/completions")]

    def __call__(self, request):
        data = json.loads(request.content)
        self.calls.append((request.url.path, data))
        if request.url.path.endswith("/embed"):
            return httpx.Response(200, json=[[1.0, 0.0, 0.0] for _ in data["inputs"]])
        if self.mode == "unavailable":
            return httpx.Response(503, json={"error": "test only"})
        system = data["messages"][0]["content"]
        payload = json.loads(data["messages"][1]["content"].split("\n", 1)[1])
        if self.hook:
            self.hook(system)
        if "benefit-to-need matching" in system or "You are Claimly. Answer only" in system:
            docs = payload["context"]["documents"]
            page = docs[0]["pages"][0]
            quote = page["text"].splitlines()[3]
            r = ref(docs[0], page, quote)
            if self.mode == "bad-citation":
                r["quote"] = "INVENTED TEXT THAT IS NOT IN SOURCE"
            benefits = [b["id"] for b in payload["context"]["benefits"]][:1]
            value = {"answer": "The document states: " + quote, "evidence_refs": [r], "matched_benefit_ids": benefits,
                     "questions": [], "next_actions": [{"type": "open_benefit", "label": "View", "target_id": benefits[0]}] if benefits else []}
            if self.mode == "foreign-id":
                value["matched_benefit_ids"] = ["00000000-0000-4000-8000-000000000000"]
        elif "case assessment" in system:
            docs = payload["context"]["documents"]
            page = docs[0]["pages"][0]
            value = {"status": "possible", "summary": "Coverage is described.", "reasons": ["Coverage lasts 24 months."],
                     "evidence_refs": [ref(docs[0], page, "Coverage lasts 24 months from purchase.")], "missing_info": [],
                     "next_actions": [{"type": "open_case", "label": "Prepare", "target_id": payload["context"]["case"]["id"]}]}
            if self.mode == "uncited-positive":
                value["evidence_refs"] = []
        elif "request drafting" in system:
            docs = payload["context"]["documents"]
            refs = [ref(docs[0], docs[0]["pages"][0], "Coverage lasts 24 months from purchase.")] if docs else []
            value = {"subject": "Warranty request", "body": "Hello, my laptop needs repair.", "attachments": [], "contact": None,
                     "contact_origin": "unknown", "evidence_refs": refs, "missing_info": ["Provider contact"]}
            if self.mode == "invented-contact":
                value.update(contact="support@invented.example", contact_origin="document")
        elif "company-reply analysis" in system:
            docs = payload["context"]["documents"]
            value = {"summary": "The company asks for a receipt.", "company_position": "Asks for more information.",
                     "comparison": "The document states coverage lasts 24 months.",
                     "evidence_refs": [ref(docs[0], docs[0]["pages"][0], "Coverage lasts 24 months from purchase.")] if docs else [],
                     "missing_info": ["Receipt"], "next_actions": []}
        elif "Extract only" in system:
            page = payload["pages"][0]
            doc = {"document_id": payload["document_id"], "document_version": payload["document_version"]}
            purchase = "Laptop model L1 purchased on 2026-01-04."
            coverage = "Coverage lasts 24 months from purchase."
            value = {"category": "warranty", "title": "Cedar Electronics limited warranty", "provider": "Fictional Cedar Electronics",
                     "subject": "Laptop model L1",
                     "facts": {"purchase_date": {"value": "2026-01-04", "origin": "document", "evidence_refs": [ref(doc, page, purchase)],
                                                 "needs_review": False}},
                     "benefits": [{"candidate_key": "coverage", "title": "Repair coverage", "type": "warranty_coverage",
                                   "description": "Laptop defect coverage.", "conditions": ["Excludes accidental damage and liquid damage."],
                                   "units_total": 2, "stated_value_cents": None, "currency": None,
                                   "deadline_rule": {"kind": "relative", "semantics": "coverage_end", "date": None,
                                                     "anchor_field": "purchase_date", "duration_value": 24,
                                                     "duration_unit": "calendar_months", "last_day_inclusion": "unknown",
                                                     "evidence_refs": [ref(doc, page, coverage)]},
                                   "instructions": [], "evidence_refs": [ref(doc, page, coverage)], "needs_review": False}],
                     "review_flags": []}
        elif "Classify actual readable content only" in system:
            page = payload["pages"][0]
            value = {"outcome": "out_of_scope" if self.mode == "out-of-scope" else "relevant", "category": "warranty",
                     "reason": "Fixture.", "evidence_refs": [ref({"document_id": payload["document_id"],
                                                                  "document_version": payload["document_version"]}, page, page["text"].splitlines()[1])]}
        else:
            raise AssertionError("unexpected prompt")
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(value)}}]})


class AppTransport(httpx.BaseTransport):
    """Route HttpLlmClient requests to the real internal LLM FastAPI app in-process."""

    def __init__(self, app):
        self.client = TestClient(app)

    def handle_request(self, request):
        response = self.client.request(request.method, request.url.path, headers=dict(request.headers), content=request.read())
        return httpx.Response(response.status_code, headers=response.headers, content=response.content)


PG_URL = os.environ.get("CLAIMLY_TEST_DATABASE_URL", "")


def make_settings(tmp_path, **overrides):
    base = Settings(database_url=PG_URL or "sqlite:///" + str(tmp_path / "claimly.sqlite"), local_dev=True, storage_backend="local",
                    local_storage_dir=str(tmp_path / "originals"), llm_base_url="http://llm.internal", llm_service_token=SERVICE_TOKEN,
                    scheduler_secret="scheduler-secret-for-tests", frontend_origins=("https://claimly-final.vercel.app",),
                    contracts_dir=str(ROOT / "Claimly_Three_Parts/contracts"))
    return replace(base, **overrides).checked()


class Rig:
    def __init__(self, tmp_path, **overrides):
        self.tmp = tmp_path
        self.settings = make_settings(tmp_path, **overrides)
        self.db = Database(self.settings)
        if self.db.postgres:
            with self.db.tx(write=True) as c:  # isolated schema per test on the dedicated test database
                c.execute("DROP SCHEMA IF EXISTS claimly CASCADE")
        migrate(self.db, out=lambda *_: None)
        self.storage = LocalStorage(self.settings.local_storage_dir)
        self.provider = Provider()
        self.llm_settings = LlmSettings(service_token=SERVICE_TOKEN, hf_token="test-hf-secret", embedding_url="https://embedding.test/embed",
                                        chat_url="https://chat.test/v1", embedding_revision="a" * 40, chat_revision="b" * 40,
                                        embedding_dimension=3, chunk_tokens=128)
        self.hf = HFClient(self.llm_settings, transport=httpx.MockTransport(self.provider), budget=Budget())
        self.llm_app = llm_app(self.llm_settings, processor=Processor(self.hf, NativeFixtureParser()))
        self.llm = HttpLlmClient(self.settings, transport=AppTransport(self.llm_app))
        self.worker = Worker(self.settings, db=self.db, storage=self.storage, llm=self.llm, embedder=self.hf)
        self.app = create_app(self.settings, database=self.db, storage=self.storage)
        self.client = TestClient(self.app)
        self.session = self.new_session()
        self.client.headers["X-Demo-Session"] = self.session["session_token"]
        self._keys = 0

    def new_session(self):
        response = self.client.post("/api/v1/demo/sessions", headers={"X-Demo-Session": ""})
        assert response.status_code == 201, response.text
        return response.json()["data"]

    def key(self, prefix="key"):
        self._keys += 1
        return f"{prefix}-{self._keys:06d}"

    def post(self, path, body=None, *, key=None, headers=None):
        return self.client.post(path, json=body, headers={"Idempotency-Key": key or self.key(), **(headers or {})})

    def entry(self, title="Pending document", category="other"):
        response = self.post("/api/v1/entries", {"title": title, "category": category})
        assert response.status_code == 201, response.text
        return response.json()["data"]

    def upload(self, name="warranty.pdf", *, entry=None, key=None, mime="application/pdf", data=None):
        entry = entry or self.entry()
        content = data if data is not None else (FIXTURES / name).read_bytes()
        response = self.client.post("/api/v1/documents", headers={"Idempotency-Key": key or self.key("upload")},
                                    data={"entry_id": entry["id"]}, files={"file": (name, content, mime)})
        assert response.status_code == 202, response.text
        return response.json()["data"]

    def run(self, n=1):
        for _ in range(n):
            assert self.worker.once()

    def job(self, job_id):
        return self.client.get("/api/v1/jobs/" + job_id).json()["data"]

    def approve(self, document_id):
        from app.db import get
        from app.review import approve
        with self.db.tx() as c:
            _, private = get(c, self.session["id"], "document", document_id)
        return approve(self.db, self.storage, self.session["id"], document_id, private["source_sha256"], private["pages_sha256"])

    def indexed_document(self):
        """Upload -> convert -> operator approval -> index. Returns (upload result, document id)."""
        result = self.upload()
        self.run()
        doc_id = result["document"]["id"]
        approved = self.approve(doc_id)
        self.run()
        assert self.job(approved["id"])["status"] == "succeeded", self.job(approved["id"])
        return result, doc_id

    def thread(self, scope="vault", entry_id=None, case_id=None, document_ids=()):
        response = self.post("/api/v1/threads", {"scope": scope, "entry_id": entry_id, "case_id": case_id, "document_ids": list(document_ids)})
        assert response.status_code == 201, response.text
        return response.json()["data"]

    def ask(self, thread_id, text="What does this warranty cover?", purpose="answer"):
        response = self.post(f"/api/v1/threads/{thread_id}/messages", {"content": text, "purpose": purpose})
        assert response.status_code == 202, response.text
        return response.json()["data"]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)
