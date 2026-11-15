"""Contract coverage, sessions, CORS, cases, usage/outcomes, reminders and dispatch."""

import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.contract import validate
from conftest import ROOT, Rig

CONTRACT = json.loads((ROOT / "Claimly_Three_Parts/contracts/backend.openapi.json").read_text())
ORIGIN = "https://claimly-final.vercel.app"


def test_every_contract_operation_is_routed(rig):
    from app.routes import build_router
    routes = list(build_router(rig.app.state.api).routes) + [r for r in rig.app.routes if hasattr(r, "methods")]
    routed = {(m, re.sub(r"\{[^}]+\}", "{}", r.path)) for r in routes for m in r.methods}
    for path, operations in CONTRACT["paths"].items():
        for method in operations:
            if method in {"get", "post", "put", "patch", "delete"}:
                assert (method.upper(), re.sub(r"\{[^}]+\}", "{}", path)) in routed, (method, path)
    assert sum(1 for ops in CONTRACT["paths"].values() for m in ops if m in {"get", "post", "put", "patch", "delete"}) == 43


def test_contract_copies_are_identical():
    canonical = (ROOT / "Claimly_Three_Parts/contracts/backend.openapi.json").read_bytes()
    for copy in ["front/contracts", "back/front/contracts"]:
        assert (ROOT / copy / "backend.openapi.json").read_bytes() == canonical
        assert (ROOT / copy / "llm.openapi.json").read_bytes() == (ROOT / "Claimly_Three_Parts/contracts/llm.openapi.json").read_bytes()


def test_health_and_contract_headers(rig):
    response = rig.client.get("/health")
    assert response.status_code == 200 and response.headers["X-Contract-Version"] == "2.0.0"
    validate("HealthEnvelope", response.json())
    assert response.json()["data"]["status"] == "ok"


def test_cors_preflight_allows_frontend_origin_and_session_header(rig):
    response = rig.client.options("/api/v1/entries", headers={
        "Origin": ORIGIN, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-demo-session,idempotency-key,content-type"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "x-demo-session" in allowed and "idempotency-key" in allowed
    evil = rig.client.options("/api/v1/entries", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in evil.headers


def test_session_required_and_unknown_token(rig):
    assert rig.client.get("/api/v1/entries", headers={"X-Demo-Session": ""}).json()["error"]["code"] == "DEMO_SESSION_REQUIRED"
    assert rig.client.get("/api/v1/entries", headers={"X-Demo-Session": "z" * 43}).status_code == 401
    validate("DemoSessionEnvelope", rig.client.post("/api/v1/demo/sessions").json())


def test_session_creation_is_rate_limited(tmp_path):
    from dataclasses import replace
    rig = Rig(tmp_path)
    from app.main import create_app
    from fastapi.testclient import TestClient
    # The rig already created one session from this client address.
    client = TestClient(create_app(replace(rig.settings, session_creations_per_hour=3), database=rig.db, storage=rig.storage))
    codes = [client.post("/api/v1/demo/sessions").status_code for _ in range(3)]
    assert codes == [201, 201, 429]


def test_idempotency_replay_and_conflict(rig):
    body = {"title": "Receipt", "category": "receipt"}
    first, second = rig.post("/api/v1/entries", body, key="entry-key-1"), rig.post("/api/v1/entries", body, key="entry-key-1")
    assert first.json() == second.json()
    assert rig.post("/api/v1/entries", dict(body, title="Other"), key="entry-key-1").status_code == 409
    assert rig.client.post("/api/v1/entries", json=body).status_code == 422  # key required


def test_file_limits_and_signatures(rig):
    entry = rig.entry()
    def send(name, data, mime):
        return rig.client.post("/api/v1/documents", headers={"Idempotency-Key": rig.key()}, data={"entry_id": entry["id"]},
                               files={"file": (name, data, mime)})
    assert send("x.txt", b"hello", "text/plain").json()["error"]["code"] == "VALIDATION_ERROR"
    assert send("x.pdf", b"\x89PNG\r\n\x1a\n" + b"0" * 20, "application/pdf").status_code == 422
    assert send("big.pdf", b"%PDF-" + b"0" * (10 * 1024 * 1024 + 10), "application/pdf").status_code == 413
    corrupt = (ROOT / "services/llm/parsing/fixtures/corrupt_jpeg.jpg").read_bytes()
    assert send("c.jpg", corrupt, "image/jpeg").json()["error"]["code"] == "UNREADABLE_DOCUMENT"
    photo = (ROOT / "services/llm/parsing/fixtures/clear_simulated_photo.jpg").read_bytes()
    assert send("p.jpg", photo, "image/jpeg").status_code == 202


def test_pagination_is_stable_and_validated(tmp_path):
    rig = Rig(tmp_path, source_review_mode="user_confirmation")
    for _ in range(3):
        rig.upload()
        rig.run()
    first = rig.client.get("/api/v1/entries?limit=2").json()
    assert len(first["data"]) == 2 and first["next_cursor"]
    second = rig.client.get(f"/api/v1/entries?limit=2&cursor={first['next_cursor']}").json()
    assert len(second["data"]) == 1 and second["next_cursor"] is None
    assert {e["id"] for e in first["data"]}.isdisjoint({e["id"] for e in second["data"]})
    assert rig.client.get("/api/v1/entries?cursor=bogus").status_code == 422
    assert rig.client.get("/api/v1/entries?limit=101").status_code == 422
    validate("EntryList", first)


def test_profile_patch_validation(rig):
    assert rig.client.patch("/api/v1/profile", json={"timezone": "Mars/Base"}).status_code == 422
    assert rig.client.patch("/api/v1/profile", json={"email_notification_opt_in": True}).status_code == 422  # no email provider
    ok = rig.client.patch("/api/v1/profile", json={"timezone": "America/Los_Angeles", "reminder_offsets": [14, 1]})
    assert ok.status_code == 200 and ok.json()["data"]["timezone"] == "America/Los_Angeles"
    validate("ProfileEnvelope", ok.json())


def test_entry_patch_version_conflict_and_user_facts(rig):
    entry = rig.entry()
    fact = {"value": "2026-02-01", "origin": "user", "evidence_refs": [], "needs_review": False}
    ok = rig.client.patch("/api/v1/entries/" + entry["id"], json={"facts": {"purchase_date": fact}, "expected_version": 1})
    assert ok.status_code == 200 and ok.json()["data"]["data_version"] == 2
    assert rig.client.patch("/api/v1/entries/" + entry["id"], json={"title": "x", "expected_version": 1}).status_code == 409


def test_user_fact_survives_extraction(tmp_path):
    rig = Rig(tmp_path, source_review_mode="user_confirmation")
    entry = rig.entry()
    fact = {"value": "2026-03-03", "origin": "user", "evidence_refs": [], "needs_review": False}
    rig.client.patch("/api/v1/entries/" + entry["id"], json={"facts": {"purchase_date": fact}, "expected_version": 1})
    rig.upload(entry=entry)
    rig.run()
    assert rig.client.get("/api/v1/entries/" + entry["id"]).json()["data"]["facts"]["purchase_date"]["origin"] == "user"


def benefit_of(rig):
    rig.indexed_document()
    return rig.client.get("/api/v1/benefits").json()["data"][0]


def usage(rig, benefit, used, key=None):
    return rig.client.put(f"/api/v1/benefits/{benefit['id']}/usage", headers={"Idempotency-Key": key or rig.key()},
                          json={"used_units": used, "confirmed_at": "2026-11-15T10:00:00Z", "note": "", "expected_version": benefit["data_version"]})


def test_usage_is_absolute_versioned_and_bounded(rig):
    benefit = benefit_of(rig)
    assert usage(rig, benefit, 3).status_code == 422  # units_total = 2
    first = usage(rig, benefit, 1, key="usage-key-1")
    assert first.status_code == 200 and first.json()["data"]["remaining_units"] == 1
    assert usage(rig, benefit, 1, key="usage-key-1").json() == first.json()  # replay
    assert usage(rig, benefit, 1).status_code == 409  # stale expected_version


def outcome(rig, case, qty, kind="service_used", benefit_id=None, key=None):
    body = {"benefit_id": benefit_id, "kind": kind, "cash_amount_cents": None, "estimated_value_cents": None,
            "value_origin": "not_known", "quantity": qty, "currency": "USD", "confirmation_source": "user_reported",
            "confirmed_at": "2026-11-15T12:00:00Z", "evidence_refs": [], "note": ""}
    return rig.client.put(f"/api/v1/cases/{case['id']}/outcome", headers={"Idempotency-Key": key or rig.key()}, json=body)


def new_case(rig, benefit=None, docs=()):
    body = {"title": "Laptop repair", "type": "warranty", "entry_ids": [benefit["entry_id"]] if benefit else [],
            "document_ids": list(docs), "benefit_id": benefit["id"] if benefit else None,
            "situation": "The laptop stopped charging.", "incident_date": "2026-11-01", "desired_result": "Free repair"}
    response = rig.post("/api/v1/cases", body)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_baseline_usage_outcome_repeat_and_correction_without_double_counting(rig):
    benefit = benefit_of(rig)
    benefit = usage(rig, benefit, 0).json()["data"]  # baseline confirmed: unused
    case = new_case(rig, benefit)
    assert rig.client.get("/api/v1/benefits/" + benefit["id"]).json()["data"]["used_units"] == 0  # case creation deducts nothing
    assert outcome(rig, case, 1, benefit_id=benefit["id"]).status_code == 200
    assert rig.client.get("/api/v1/benefits/" + benefit["id"]).json()["data"]["used_units"] == 1
    outcome(rig, case, 1, benefit_id=benefit["id"])  # repeat with a new key
    assert rig.client.get("/api/v1/benefits/" + benefit["id"]).json()["data"]["used_units"] == 1
    outcome(rig, case, 2, benefit_id=benefit["id"])  # correction
    state = rig.client.get("/api/v1/benefits/" + benefit["id"]).json()["data"]
    assert state["used_units"] == 2 and state["usage_state"] == "used" and state["remaining_units"] == 0
    dash = rig.client.get("/api/v1/dashboard").json()["data"]
    assert dash["services_used_units"] == 2
    with rig.db.tx() as c:
        assert c.execute("SELECT COUNT(*) AS n FROM claimly.usage_events WHERE outcome_id IS NOT NULL").fetchone()["n"] == 1
    outcome(rig, case, None, kind="denied")  # outcome no longer uses the benefit: usage reverted
    assert rig.client.get("/api/v1/benefits/" + benefit["id"]).json()["data"]["used_units"] == 0


def test_unknown_baseline_never_computes_full_remainder(rig):
    benefit = benefit_of(rig)
    case = new_case(rig, benefit)
    outcome(rig, case, 1, benefit_id=benefit["id"])
    state = rig.client.get("/api/v1/benefits/" + benefit["id"]).json()["data"]
    assert state["usage_state"] == "unknown" and state["used_units"] == 1 and state["remaining_units"] is None


def test_cash_outcome_and_dashboard_money(rig):
    case = new_case(rig)
    bad = rig.client.put(f"/api/v1/cases/{case['id']}/outcome", headers={"Idempotency-Key": rig.key()}, json={
        "benefit_id": None, "kind": "cash_refund", "cash_amount_cents": None, "estimated_value_cents": None, "value_origin": "not_known",
        "quantity": None, "currency": "USD", "confirmation_source": "user_reported", "confirmed_at": "2026-11-15T12:00:00Z",
        "evidence_refs": [], "note": ""})
    assert bad.status_code == 422
    case = rig.client.post(f"/api/v1/cases/{case['id']}/status", headers={"Idempotency-Key": rig.key()}, json={
        "status": "approved", "event_date": "2026-11-15T12:00:00Z", "note": "", "approved_amount_cents": 5000,
        "expected_version": case["data_version"]}).json()["data"]
    assert rig.client.get("/api/v1/dashboard").json()["data"]["approved_not_received_cents"] == 5000
    body = {"benefit_id": None, "kind": "cash_refund", "cash_amount_cents": 4200, "estimated_value_cents": 900, "value_origin": "user_estimate",
            "quantity": None, "currency": "USD", "confirmation_source": "user_reported", "confirmed_at": "2026-11-15T12:00:00Z",
            "evidence_refs": [], "note": "Refunded"}
    assert rig.client.put(f"/api/v1/cases/{case['id']}/outcome", headers={"Idempotency-Key": rig.key()}, json=body).status_code == 200
    dash = rig.client.get("/api/v1/dashboard").json()["data"]
    assert dash["cash_recovered_cents"] == 4200 and dash["approved_not_received_cents"] == 0
    validate("OutcomeEnvelope", rig.client.get(f"/api/v1/cases/{case['id']}/outcome").json())


def test_case_assess_draft_edit_and_reply_flow(rig):
    benefit = benefit_of(rig)
    doc_id = rig.client.get("/api/v1/documents/" + rig.client.get("/api/v1/entries").json()["data"][0]["document_ids"][0]).json()["data"]["id"]
    case = new_case(rig, benefit, [doc_id])
    assess = rig.client.post(f"/api/v1/cases/{case['id']}/assess", headers={"Idempotency-Key": rig.key()})
    assert assess.status_code == 202
    rig.run()
    job = rig.job(assess.json()["data"]["id"])
    assert job["status"] == "succeeded", job
    assert job["result"]["assessment"]["status"] == "possible" and job["result"]["assessment"]["evidence_refs"]
    draft_job = rig.post(f"/api/v1/cases/{case['id']}/drafts", {"kind": "initial"}).json()["data"]
    rig.run()
    draft = rig.job(draft_job["id"])["result"]["draft"]
    current = rig.client.get(f"/api/v1/cases/{case['id']}").json()["data"]
    assert current["status"] == "prepared" and draft["input_version"] == current["data_version"]
    edited = rig.client.patch("/api/v1/drafts/" + draft["id"], json={"subject": "S", "body": "B", "expected_input_version": draft["input_version"]})
    assert edited.status_code == 200 and edited.json()["data"]["user_edited"] is True
    assert rig.client.patch("/api/v1/drafts/" + draft["id"], json={"subject": "S", "body": "B", "expected_input_version": 999}).status_code == 409
    reply = rig.post(f"/api/v1/cases/{case['id']}/replies", {"reply_text": "Please send your receipt.", "document_ids": []}).json()["data"]
    rig.run()
    event = rig.job(reply["id"])["result"]["event"]
    assert event["type"] == "company_reply" and event["reply_analysis"]["missing_info"] == ["Receipt"]
    events = rig.client.get(f"/api/v1/cases/{case['id']}/events").json()
    validate("CaseEventList", events)
    assert {e["type"] for e in events["data"]} == {"draft_created", "company_reply"}


def test_case_change_makes_running_assessment_stale(rig):
    benefit = benefit_of(rig)
    case = new_case(rig, benefit)
    job = rig.client.post(f"/api/v1/cases/{case['id']}/assess", headers={"Idempotency-Key": rig.key()}).json()["data"]
    rig.client.patch(f"/api/v1/cases/{case['id']}", json={"situation": "Changed", "expected_version": case["data_version"]})
    rig.run()
    assert rig.job(job["id"])["status"] == "stale"


def test_uncited_positive_assessment_is_rejected(rig):
    benefit = benefit_of(rig)
    case = new_case(rig, benefit)
    rig.provider.mode = "uncited-positive"
    job = rig.client.post(f"/api/v1/cases/{case['id']}/assess", headers={"Idempotency-Key": rig.key()}).json()["data"]
    rig.run()
    assert rig.job(job["id"])["error"]["code"] == "INVALID_LLM_OUTPUT"


def test_invented_draft_contact_is_rejected(rig):
    benefit = benefit_of(rig)
    case = new_case(rig, benefit)
    rig.provider.mode = "invented-contact"
    job = rig.post(f"/api/v1/cases/{case['id']}/drafts", {"kind": "initial"}).json()["data"]
    rig.run()
    assert rig.job(job["id"])["error"]["code"] == "INVALID_LLM_OUTPUT"


def test_case_without_documents_assesses_insufficient_without_model_call(rig):
    case = new_case(rig)
    job = rig.client.post(f"/api/v1/cases/{case['id']}/assess", headers={"Idempotency-Key": rig.key()}).json()["data"]
    rig.run()
    assessment = rig.job(job["id"])["result"]["assessment"]
    assert assessment["status"] == "insufficient_evidence" and assessment["evidence_refs"] == []
    assert rig.provider.calls == []


def reminder_body(**overrides):
    body = {"benefit_id": None, "case_id": None, "title": "Use dental cleaning", "date": "2026-11-10", "timezone": "America/New_York",
            "local_time": "09:00", "origin": "user", "offset_days": [7, 0], "channels": ["in_app"], "status": "active", "evidence_refs": []}
    body.update(overrides)
    return body


def test_reminder_deliveries_respect_dst_and_regenerate(rig):
    created = rig.post("/api/v1/reminders", reminder_body())
    assert created.status_code == 201
    notes = sorted(rig.client.get("/api/v1/notifications").json()["data"], key=lambda n: n["scheduled_at"])
    # 2026-11-03 09:00 EST (after DST ended) = 14:00Z; 2026-11-10 09:00 EST = 14:00Z.
    assert [n["scheduled_at"] for n in notes] == ["2026-11-03T14:00:00Z", "2026-11-10T14:00:00Z"]
    rid = created.json()["data"]["id"]
    rig.client.patch("/api/v1/reminders/" + rid, json={"date": "2026-10-20"})
    notes = rig.client.get("/api/v1/notifications").json()["data"]
    # 2026-10-20 09:00 EDT = 13:00Z; old pending deliveries are cancelled (hidden from the list).
    assert sorted(n["scheduled_at"] for n in notes) == ["2026-10-13T13:00:00Z", "2026-10-20T13:00:00Z"]
    assert rig.post("/api/v1/reminders", reminder_body(channels=["email"])).status_code == 422


def test_dispatch_requires_secret_and_is_idempotent(rig):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    rig.post("/api/v1/reminders", reminder_body(date=past, offset_days=[0]))
    assert rig.client.post("/internal/v1/reminders/dispatch").status_code == 401
    headers = {"Authorization": "Bearer scheduler-secret-for-tests"}
    first = rig.client.post("/internal/v1/reminders/dispatch", headers=headers).json()["data"]
    second = rig.client.post("/internal/v1/reminders/dispatch", headers=headers).json()["data"]
    assert first["sent"] == 1 and second == {"processed": 0, "sent": 0, "failed": 0, "cancelled": 0}
    assert rig.client.get("/api/v1/notifications").json()["data"][0]["status"] == "sent"


def test_entry_deletion_cascades_and_keeps_case(rig):
    benefit = benefit_of(rig)
    case = new_case(rig, benefit)
    assert rig.client.delete("/api/v1/entries/" + benefit["entry_id"]).status_code == 204
    assert rig.client.get("/api/v1/benefits").json()["data"] == []
    kept = rig.client.get("/api/v1/cases/" + case["id"]).json()["data"]
    assert kept["entry_ids"] == [] and kept["benefit_id"] is None


@pytest.mark.parametrize("path", ["/api/v1/cases/{}", "/api/v1/benefits/{}", "/api/v1/drafts/{}"])
def test_invalid_uuid_and_unknown_ids(rig, path):
    assert rig.client.get(path.format("not-a-uuid")).status_code in (404, 405, 422)
