"""End-to-end Backend flows through the real worker and the real internal LLM API (HF HTTP mocked)."""

import time

from app.db import get
from app.contract import validate
from conftest import FIXTURES, Rig


def chunk_count(rig, owner=None):
    with rig.db.tx() as c:
        return c.execute("SELECT COUNT(*) AS n FROM claimly.session_chunks" + (" WHERE session_id=?" if owner else ""),
                         (owner,) if owner else ()).fetchone()["n"]


def test_upload_review_index_and_cited_answer(rig):
    result, doc_id = rig.indexed_document()
    validate("UploadAcceptedEnvelope", {"data": result, "request_id": "r"})
    doc = rig.client.get("/api/v1/documents/" + doc_id).json()["data"]
    assert doc["status"] == "ready" and doc["facts"]["purchase_date"]["value"] == "2026-01-04"
    entries = rig.client.get("/api/v1/entries").json()["data"]
    assert [e["title"] for e in entries] == ["Cedar Electronics limited warranty"] and entries[0]["category"] == "warranty"
    benefits = rig.client.get("/api/v1/benefits").json()["data"]
    assert len(benefits) == 1 and benefits[0]["usage_state"] == "unknown" and benefits[0]["used_units"] is None
    # Relative 24-month rule with unknown last-day inclusion: Backend computes the date but requires review.
    assert benefits[0]["deadline_status"] == "needs_review" and benefits[0]["deadline_date"] is None
    reminders = rig.client.get("/api/v1/reminders").json()["data"]
    assert reminders[0]["date"] == "2028-01-04" and reminders[0]["status"] == "needs_review"
    q = rig.ask(rig.thread()["id"])
    rig.run()
    job = rig.job(q["job"]["id"])
    validate("Job", job)
    assert job["status"] == "succeeded", job
    message = job["result"]["assistant_message"]
    assert message["evidence_refs"][0]["document_id"] == doc_id
    assert message["matched_benefit_ids"] == [benefits[0]["id"]]
    assert rig.client.get(f"/api/v1/documents/{doc_id}/content").content == (FIXTURES / "warranty.pdf").read_bytes()
    assert "test-hf-secret" not in str(job)
    assert any(path.endswith("/embed") and body["truncate"] is False for path, body in rig.provider.calls)


def test_repeated_extraction_does_not_duplicate_benefits_or_reminders(rig):
    _, doc_id = rig.indexed_document()
    again = rig.post(f"/api/v1/documents/{doc_id}/analyze", {"force": False})
    assert again.status_code == 202
    rig.run()
    assert len(rig.client.get("/api/v1/benefits").json()["data"]) == 1
    assert len(rig.client.get("/api/v1/reminders").json()["data"]) == 1


def test_operator_mode_keeps_unreviewed_conversion_out_of_vault_and_index(rig):
    result = rig.upload()
    rig.run()
    assert rig.job(result["job"]["id"])["result"]["review_required"] is True
    assert rig.client.get("/api/v1/documents/" + result["document"]["id"]).json()["data"]["status"] == "needs_review"
    assert chunk_count(rig) == 0
    assert rig.client.get("/api/v1/entries").json()["data"] == []
    assert not any(path.endswith("/embed") for path, _ in rig.provider.calls)


def test_user_confirmation_mode_admits_with_every_item_flagged_for_user_review(tmp_path):
    rig = Rig(tmp_path, source_review_mode="user_confirmation")
    result = rig.upload()
    rig.run()
    job = rig.job(result["job"]["id"])
    assert job["status"] == "succeeded" and job["result"]["review_required"] is True
    doc = rig.client.get("/api/v1/documents/" + result["document"]["id"]).json()["data"]
    assert doc["status"] == "needs_review" and all(f["needs_review"] for f in doc["facts"].values())
    assert all(b["needs_review"] for b in rig.client.get("/api/v1/benefits").json()["data"])
    assert chunk_count(rig) > 0 and len(rig.client.get("/api/v1/entries").json()["data"]) == 1


def test_review_hash_mismatch_cannot_activate(rig):
    import pytest
    from app.errors import ApiError
    from app.review import approve
    result = rig.upload()
    rig.run()
    with pytest.raises(ApiError, match="hashes"):
        approve(rig.db, rig.storage, rig.session["id"], result["document"]["id"], "0" * 64, "0" * 64)


def test_out_of_scope_removes_original_and_draft_entry(rig):
    result = rig.upload()
    rig.provider.mode = "out-of-scope"
    rig.run()
    assert rig.client.get("/api/v1/documents/" + result["document"]["id"]).status_code == 404
    assert not [p for p in (rig.tmp / "originals").rglob("*") if p.is_file()]
    assert rig.client.get("/api/v1/entries/" + result["document"]["entry_id"]).status_code == 404
    job = rig.job(result["job"]["id"])
    assert job["status"] == "failed" and job["error"]["code"] == "VALIDATION_ERROR"


def test_sessions_are_isolated_for_reads_content_jobs_and_retrieval(rig):
    result, doc_id = rig.indexed_document()
    other = rig.new_session()["session_token"]
    for path in ["/api/v1/documents/" + doc_id, f"/api/v1/documents/{doc_id}/content", "/api/v1/jobs/" + result["job"]["id"],
                 "/api/v1/entries/" + result["document"]["entry_id"]]:
        assert rig.client.get(path, headers={"X-Demo-Session": other}).status_code == 404
    assert rig.client.get("/api/v1/benefits", headers={"X-Demo-Session": other}).json()["data"] == []
    rig.client.headers["X-Demo-Session"] = other
    q = rig.ask(rig.thread()["id"])
    rig.run()
    message = rig.job(q["job"]["id"])["result"]["assistant_message"]
    assert message["evidence_refs"] == [] and "no approved document" in message["content"]
    # Cross-session thread creation with a foreign document is rejected.
    assert rig.post("/api/v1/threads", {"scope": "vault", "entry_id": None, "case_id": None, "document_ids": [doc_id]}).status_code == 404


def test_upload_replay_does_not_duplicate_jobs_or_files(rig):
    entry = rig.entry()
    first = rig.upload(entry=entry, key="same-upload-key")
    second = rig.upload(entry=entry, key="same-upload-key")
    assert first == second
    with rig.db.tx() as c:
        assert c.execute("SELECT COUNT(*) AS n FROM claimly.session_jobs").fetchone()["n"] == 1
    assert len([p for p in (rig.tmp / "originals").rglob("*") if p.is_file()]) == 1


def test_document_deletion_removes_vectors_and_invalidates_citations(rig):
    result, doc_id = rig.indexed_document()
    q = rig.ask(rig.thread()["id"])
    rig.run()
    assert rig.client.delete("/api/v1/documents/" + doc_id).status_code == 204
    assert chunk_count(rig) == 0
    messages = rig.client.get(f"/api/v1/threads/{q['message']['thread_id']}/messages").json()["data"]
    assert all(not m["evidence_refs"] for m in messages)
    historical = rig.job(q["job"]["id"])
    assert historical["status"] == "stale" and historical["result"] is None
    assert rig.client.get(f"/api/v1/documents/{doc_id}/content").status_code == 404
    assert rig.client.get("/api/v1/benefits").json()["data"] == []
    assert all(r["status"] == "cancelled" for r in rig.client.get("/api/v1/reminders").json()["data"])
    assert not [p for p in (rig.tmp / "originals").rglob("*") if p.is_file()]


def test_inflight_deletion_cannot_publish_answer(rig):
    _, doc_id = rig.indexed_document()
    q = rig.ask(rig.thread()["id"])
    rig.provider.hook = lambda system: rig.client.delete("/api/v1/documents/" + doc_id) if "Answer only" in system else None
    rig.run()
    job = rig.job(q["job"]["id"])
    assert job["status"] in {"cancelled", "stale"} and job["result"] is None
    assert [m["role"] for m in rig.client.get(f"/api/v1/threads/{q['message']['thread_id']}/messages").json()["data"]] == ["user"]


def test_fabricated_citation_fails_after_single_repair(rig):
    rig.indexed_document()
    q = rig.ask(rig.thread()["id"])
    rig.provider.mode = "bad-citation"
    rig.run()
    job = rig.job(q["job"]["id"])
    assert job["status"] == "failed" and job["error"]["code"] == "INVALID_LLM_OUTPUT"
    assert len([p for p in rig.provider.chat_paths() if "Answer only" in p]) == 2


def test_no_usable_evidence_abstains_without_model_call(rig):
    q = rig.ask(rig.thread()["id"])
    rig.run()
    message = rig.job(q["job"]["id"])["result"]["assistant_message"]
    assert message["evidence_refs"] == [] and message["matched_benefit_ids"] == [] and message["next_actions"] == []
    assert rig.provider.calls == []


def test_model_unavailable_is_retried_then_reported_honestly(rig):
    rig.indexed_document()
    q = rig.ask(rig.thread()["id"])
    rig.provider.mode = "unavailable"
    for _ in range(3):
        with rig.db.tx(write=True) as c:
            c.execute("UPDATE claimly.session_jobs SET available_at=0")
        rig.run()
    job = rig.job(q["job"]["id"])
    assert job["status"] == "failed" and job["error"]["code"] == "LLM_UNAVAILABLE" and job["result"] is None


def test_missing_ai_configuration_is_explicit(tmp_path):
    rig = Rig(tmp_path, llm_service_token="")
    result = rig.upload()
    rig.run()
    job = rig.job(result["job"]["id"])
    assert job["status"] == "failed" and job["error"]["code"] == "AI_NOT_CONFIGURED"


def test_expired_worker_lease_is_recovered_after_restart(rig):
    result = rig.upload()
    claimed = rig.db.claim("crashed-worker")
    assert claimed["id"] == result["job"]["id"]
    assert rig.db.claim("second-worker") is None  # lease still active
    with rig.db.tx(write=True) as c:
        c.execute("UPDATE claimly.session_jobs SET lease_until=? WHERE id=?", (time.time() - 1, claimed["id"]))
    rig.run()
    assert rig.job(result["job"]["id"])["status"] == "succeeded"


def test_stale_lease_cannot_publish(rig):
    from app.db import finish
    import pytest
    from app.errors import ApiError
    result = rig.upload()
    claimed = rig.db.claim("w1")
    with rig.db.tx(write=True) as c:
        c.execute("UPDATE claimly.session_jobs SET lease_token='replaced' WHERE id=?", (claimed["id"],))
    with pytest.raises(ApiError, match="lease"):
        with rig.db.tx(write=True) as c:
            finish(c, claimed, result=None)
    assert rig.job(result["job"]["id"])["status"] == "running"


def test_session_expiry_rejects_requests_and_cleanup_removes_originals(rig):
    from app.maintenance import Maintenance
    rig.upload()
    with rig.db.tx(write=True) as c:
        c.execute("UPDATE claimly.demo_sessions SET created_at=?, expires_at=?", (time.time() - 10, time.time() - 1))
    response = rig.client.get("/api/v1/entries")
    assert response.status_code == 401 and response.json()["error"]["code"] == "DEMO_SESSION_EXPIRED"
    report = Maintenance(rig.settings, rig.db, lambda: rig.storage).run()
    assert report["expired_sessions"] == 1 and report["purged"] == 1
    assert not [p for p in (rig.tmp / "originals").rglob("*") if p.is_file()]
    with rig.db.tx() as c:
        assert c.execute("SELECT COUNT(*) AS n FROM claimly.session_objects").fetchone()["n"] == 0


def test_orphaned_upload_intent_is_cleaned(rig):
    from app.maintenance import INTENT_GRACE_SECONDS, Maintenance
    entry = rig.entry()

    class FailingStorage(type(rig.storage)):
        def upload(self, path, content, mime_type):
            super().upload(path, content, mime_type)  # bytes may land even though the call "fails"
            from app.storage import fail
            fail("upload", "timeout")
    rig.app.state.api._storage = FailingStorage(rig.settings.local_storage_dir)
    response = rig.client.post("/api/v1/documents", headers={"Idempotency-Key": "orphan-key-1"}, data={"entry_id": entry["id"]},
                               files={"file": ("warranty.pdf", (FIXTURES / "warranty.pdf").read_bytes(), "application/pdf")})
    assert response.status_code == 503 and response.json()["error"]["retryable"] is True
    retry = rig.client.post("/api/v1/documents", headers={"Idempotency-Key": "orphan-key-1"}, data={"entry_id": entry["id"]},
                            files={"file": ("warranty.pdf", (FIXTURES / "warranty.pdf").read_bytes(), "application/pdf")})
    assert retry.status_code == 409 and retry.json()["error"]["retryable"] is True
    with rig.db.tx(write=True) as c:
        c.execute("UPDATE claimly.session_requests SET created_at=?", (time.time() - INTENT_GRACE_SECONDS - 1,))
    report = Maintenance(rig.settings, rig.db, lambda: rig.storage).run()
    assert report["intents"] == 1 and report["purged"] == 1
    assert not [p for p in (rig.tmp / "originals").rglob("*") if p.is_file()]


def test_foreign_benefit_id_in_model_output_is_rejected(rig):
    rig.indexed_document()
    q = rig.ask(rig.thread()["id"])
    rig.provider.mode = "foreign-id"
    rig.run()
    assert rig.job(q["job"]["id"])["error"]["code"] == "INVALID_LLM_OUTPUT"


def test_entry_scope_retrieval_excludes_other_entries(rig):
    _, doc_id = rig.indexed_document()
    other_entry = rig.entry("Another", "receipt")
    q = rig.ask(rig.thread("entry", entry_id=other_entry["id"])["id"])
    rig.run()
    message = rig.job(q["job"]["id"])["result"]["assistant_message"]
    assert message["evidence_refs"] == []


def test_embedding_profile_change_triggers_reindex_not_mixed_retrieval(rig):
    _, doc_id = rig.indexed_document()
    with rig.db.tx(write=True) as c:
        doc, private = get(c, rig.session["id"], "document", doc_id)
        private["embedding_profile"] = "old-profile"
        from app.db import put
        put(c, rig.session["id"], "document", doc, private, doc["entry_id"])
    q = rig.ask(rig.thread()["id"])
    rig.run()
    assert rig.job(q["job"]["id"])["result"]["assistant_message"]["evidence_refs"] == []  # old profile excluded
    rig.run()  # queued re-index uses the cached conversion
    with rig.db.tx() as c:
        assert get(c, rig.session["id"], "document", doc_id)[1]["embedding_profile"] == rig.hf.embedding_identity


def test_indexing_with_real_pinned_qwen_tokenizer(tmp_path):
    import httpx
    import pytest
    pytest.importorskip("transformers")
    from services.llm.app.hf import HFClient, TokenBudget
    rig = Rig(tmp_path)
    real = HFClient(rig.llm_settings, transport=httpx.MockTransport(rig.provider), budget=TokenBudget(rig.llm_settings))
    rig.worker._embedder = real
    _, doc_id = rig.indexed_document()
    with rig.db.tx() as c:
        rows = c.execute("SELECT chunk FROM claimly.session_chunks").fetchall()
    import json
    chunks = [json.loads(r["chunk"]) for r in rows]
    assert chunks and all(real.budget.embedding_count(ch["contextualized_text"]) <= 128 for ch in chunks)
    page = (FIXTURES / "warranty.pdf")
    assert "".join(ch["source_text"] for ch in sorted(chunks, key=lambda x: x["order"]))  # exact spans reassemble
