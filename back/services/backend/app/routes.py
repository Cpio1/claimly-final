"""All public contract routes (backend.openapi.json 2.0.0), bound to isolated demo sessions."""

from __future__ import annotations

import hmac
import secrets
import time
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from app import domain, lifecycle
from app.contract import validate
from app.db import encoded, end_job, find, get, jobs, new_job, now, objects, put, remove, sha, uid, get_job
from app.errors import ApiError, conflict, invalid, not_found
from app.file_validation import MAX_FILE_BYTES, validate_file
from app.storage import StorageError
from app.support import Api, client_ip, envelope, identity, limit_hit, page, sort_key, token_hash

Limit = Annotated[int, Query(ge=1, le=100)]
CASE_JOB_KINDS = ("assess", "draft", "draft_follow_up", "analyze_reply")


def expect_version(actual: int, expected) -> None:
    if actual != expected:
        raise conflict()


def build_router(api: Api) -> APIRouter:
    r = APIRouter()
    settings = api.settings

    # ── sessions ─────────────────────────────────────────────────────────────────────
    @r.post("/api/v1/demo/sessions", status_code=201)
    def create_session(request: Request):
        creator = token_hash("creator:" + client_ip(request))
        token, session_id, stamp = secrets.token_urlsafe(32), uid(), time.time()
        expires = stamp + settings.session_hours * 3600
        with api.db.tx(write=True) as c:
            if limit_hit(c, "session:" + creator, settings.session_creations_per_hour, 3600):
                raise ApiError(429, "RATE_LIMITED", "Too many demo sessions from this network. Try again later.", True)
            c.execute("INSERT INTO claimly.demo_sessions (id, token_hash, creator_hash, created_at, expires_at) VALUES (?,?,?,?,?)",
                      (session_id, token_hash(token), creator, stamp, expires))
            lifecycle.save_profile(c, session_id, domain.default_profile(settings.email_configured))
        data = {"id": session_id, "session_token": token,
                "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")}
        validate("DemoSession", data, output=True)
        return JSONResponse(envelope(request, data), status_code=201)

    # ── profile and dashboard ────────────────────────────────────────────────────────
    @r.get("/api/v1/profile")
    def get_profile(request: Request):
        with api.read(request) as (c, owner):
            return envelope(request, lifecycle.profile(c, owner, settings))

    @r.patch("/api/v1/profile")
    def patch_profile(request: Request, body: dict):
        validate("ProfilePatch", body)
        if "timezone" in body and not domain.valid_timezone(body["timezone"]):
            raise invalid("timezone must be an IANA time zone.")
        if "local_notification_time" in body and not domain.TIME_RE.match(body["local_notification_time"]):
            raise invalid("local_notification_time must be HH:MM.")
        if body.get("notification_email") is not None and not domain.EMAIL_RE.match(body["notification_email"]):
            raise invalid("notification_email must be a valid email.")
        if body.get("email_notification_opt_in") and not settings.email_configured:
            raise invalid("Email delivery is not configured on this server.")
        with api.write(request) as (c, owner):
            current = lifecycle.profile(c, owner, settings)
            current.update(body)
            validate("Profile", current, output=True)
            lifecycle.save_profile(c, owner, current)
            return envelope(request, current)

    @r.get("/api/v1/dashboard")
    def get_dashboard(request: Request):
        with api.read(request) as (c, owner):
            data = domain.dashboard([b for b, _ in objects(c, owner, "benefit")], [x for x, _ in objects(c, owner, "case")],
                                    [o for o, _ in objects(c, owner, "outcome")], [x for x, _ in objects(c, owner, "reminder")],
                                    datetime.now(timezone.utc).date().isoformat())
        validate("Dashboard", data, output=True)
        return envelope(request, data)

    # ── entries ──────────────────────────────────────────────────────────────────────
    @r.get("/api/v1/entries")
    def list_entries(request: Request, category: str | None = None, q: str | None = None,
                     cursor: str | None = None, limit: Limit = 25):
        with api.read(request) as (c, owner):
            items = [e for e, p in objects(c, owner, "entry") if p.get("admitted")]
        if category:
            items = [e for e in items if e["category"] == category]
        if q and q.strip():
            needle = q.strip().lower()
            items = [e for e in items if any(needle in (x or "").lower() for x in (e["title"], e["provider"], e["subject"]))]
        items.sort(key=lambda e: e["id"])
        items.sort(key=lambda e: e["created_at"], reverse=True)
        return page(request, items, cursor, limit)

    @r.post("/api/v1/entries", status_code=201)
    def create_entry(request: Request, body: dict):
        validate("EntryCreate", body)
        if not body["title"].strip():
            raise invalid("title is required.")
        with api.write(request) as (c, owner):
            def operation():
                if len(objects(c, owner, "entry")) >= settings.max_entries_per_session:
                    raise ApiError(429, "RATE_LIMITED", "This demo session reached its entry limit.")
                stamp = now()
                entry = {"id": uid(), "title": body["title"].strip(), "category": body["category"],
                         "provider": body.get("provider"), "subject": body.get("subject"), "facts": {}, "data_version": 1,
                         "document_ids": [], "benefit_ids": [], "created_at": stamp, "updated_at": stamp}
                validate("Entry", entry, output=True)
                put(c, owner, "entry", entry, {"admitted": False})
                return entry
            return api.idempotent(c, request, owner, body, 201, operation)

    @r.get("/api/v1/entries/{entry_id}")
    def get_entry(entry_id: str, request: Request):
        with api.read(request) as (c, owner):
            return envelope(request, get(c, owner, "entry", identity(entry_id))[0])

    @r.patch("/api/v1/entries/{entry_id}")
    def patch_entry(entry_id: str, request: Request, body: dict):
        validate("EntryPatch", body)
        if "title" in body and not body["title"].strip():
            raise invalid("title must not be empty.")
        with api.write(request) as (c, owner):
            entry, private = get(c, owner, "entry", identity(entry_id))
            expect_version(entry["data_version"], body["expected_version"])
            for key in ("title", "provider", "subject"):
                if key in body:
                    entry[key] = body[key].strip() if key == "title" else body[key]
            if "title" in body:
                private["user_title"] = True  # later extraction must not overwrite a user-chosen title
            for key, fact in (body.get("facts") or {}).items():
                entry["facts"][key] = fact
            entry["data_version"] += 1
            entry["updated_at"] = now()
            validate("Entry", entry, output=True)
            put(c, owner, "entry", entry, private)
            return envelope(request, entry)

    @r.delete("/api/v1/entries/{entry_id}", status_code=204)
    def delete_entry(entry_id: str, request: Request):
        with api.write(request) as (c, owner):
            entry, private = get(c, owner, "entry", identity(entry_id))
            paths = lifecycle.delete_entry(c, owner, entry, private)
        purge(paths)
        return Response(status_code=204)

    def purge(paths):
        """Best effort after commit; tombstones keep failed deletions retryable by maintenance."""
        for path in paths:
            try:
                api.storage.delete(path)
            except (StorageError, ApiError, Exception):
                continue
            with api.db.tx(write=True) as c:
                c.execute("DELETE FROM claimly.storage_tombstones WHERE storage_path=?", (path,))

    # ── documents ────────────────────────────────────────────────────────────────────
    @r.post("/api/v1/documents", status_code=202)
    async def upload_document(request: Request):
        key = request.headers.get("Idempotency-Key", "")
        if not 8 <= len(key) <= 128:
            raise invalid("Idempotency-Key must contain 8 to 128 characters.")
        try:
            async with request.form(max_files=1, max_fields=1, max_part_size=MAX_FILE_BYTES) as form:
                if len(form.multi_items()) != 2 or set(form) != {"entry_id", "file"} or not isinstance(form["file"], UploadFile):
                    raise invalid("Provide exactly one entry_id and one file.")
                entry_id = identity(form["entry_id"])
                incoming = form["file"]
                content = await incoming.read(MAX_FILE_BYTES + 1)
                file = await run_in_threadpool(validate_file, incoming.filename or "", incoming.content_type or "", content)
        except HTTPException:
            raise invalid("Invalid multipart upload (one file and entry_id required).") from None
        return await run_in_threadpool(store_upload, request, entry_id, file, key)

    def store_upload(request: Request, entry_id: str, file, key: str):
        route, key_hash = "POST /api/v1/documents", token_hash(key)
        digest = sha([entry_id, file.name, file.mime_type, file.sha256])
        document_id, job_id = uid(), uid()
        with api.write(request) as (c, owner):
            c.lock(owner + route + key_hash)
            old = c.execute("SELECT * FROM claimly.session_requests WHERE session_id=? AND route=? AND key_hash=?",
                            (owner, route, key_hash)).fetchone()
            if old:
                if old["request_hash"] != digest:
                    raise conflict("This Idempotency-Key was already used with a different upload.")
                if old["state"] == "completed":
                    import json
                    return JSONResponse(json.loads(old["response"]), status_code=old["status"])
                raise ApiError(409, "CONFLICT", "This upload is still pending. Retry the same request shortly.", True)
            entry, _ = get(c, owner, "entry", entry_id)
            docs = objects(c, owner, "document")
            pending = c.execute("SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes), 0) AS b FROM claimly.session_requests "
                                "WHERE session_id=? AND state IN ('reserved','cleanup_required')", (owner,)).fetchone()
            in_entry = sum(1 for d, _ in docs if d["entry_id"] == entry_id)
            total_bytes = sum(p.get("size_bytes", 0) for _, p in docs) + pending["b"] + len(file.content)
            if (in_entry >= settings.max_files_per_entry or len(docs) + pending["n"] >= settings.max_documents_per_session
                    or total_bytes > settings.max_session_bytes):
                raise ApiError(429, "RATE_LIMITED", f"Demo file limit reached ({settings.max_files_per_entry} per entry, "
                                                    f"{settings.max_documents_per_session} per session).")
            path = f"sessions/{owner}/{document_id}/v1.{file.extension}"
            c.execute("INSERT INTO claimly.session_requests (session_id, route, key_hash, request_hash, state, storage_path, "
                      "metadata, size_bytes, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                      (owner, route, key_hash, digest, "reserved", path, encoded({"entry_id": entry_id}), len(file.content), time.time()))
        # Storage is written outside the transaction; the committed intent tracks the path durably.
        try:
            api.storage.ensure_private()
            api.storage.upload(path, file.content, file.mime_type)
        except Exception as error:
            with api.db.tx(write=True) as c:
                c.execute("UPDATE claimly.session_requests SET state='cleanup_required' WHERE session_id=? AND route=? "
                          "AND key_hash=? AND state='reserved'", (owner, route, key_hash))
            if isinstance(error, ApiError):
                raise
            raise ApiError(503, "INTERNAL_ERROR", "Private file storage is unavailable. Retry later.", True) from None
        with api.db.tx(write=True) as c:
            intent = c.execute("SELECT state FROM claimly.session_requests WHERE session_id=? AND route=? AND key_hash=?",
                               (owner, route, key_hash)).fetchone()
            found = find(c, owner, "entry", entry_id)
            if intent is None or intent["state"] != "reserved" or found is None:
                lifecycle.tombstone(c, path)
                c.execute("UPDATE claimly.session_requests SET state='cleanup_required' WHERE session_id=? AND route=? AND key_hash=?",
                          (owner, route, key_hash))
                raise not_found("Entry")
            entry, ep = found
            stamp = now()
            doc = {"id": document_id, "entry_id": entry_id, "name": file.name, "mime_type": file.mime_type, "version": 1,
                   "status": "uploaded", "page_count": file.page_count, "facts": {}, "review_flags": [], "created_at": stamp}
            validate("Document", doc, output=True)
            put(c, owner, "document", doc, {"source_sha256": file.sha256, "storage_path": path, "size_bytes": len(file.content)}, entry_id)
            entry["document_ids"].append(document_id)
            entry["data_version"] += 1
            entry["updated_at"] = stamp
            put(c, owner, "entry", entry, ep)
            job = new_job(c, owner, "extract", document_id, {"document_id": document_id, "version": 1})
            result = envelope(request, {"document": doc, "job": job})
            c.execute("UPDATE claimly.session_requests SET state='completed', status=202, response=? WHERE session_id=? "
                      "AND route=? AND key_hash=?", (encoded(result), owner, route, key_hash))
        return JSONResponse(result, status_code=202)

    @r.get("/api/v1/documents/{document_id}")
    def get_document(document_id: str, request: Request):
        with api.read(request) as (c, owner):
            return envelope(request, get(c, owner, "document", identity(document_id))[0])

    @r.get("/api/v1/documents/{document_id}/content")
    def get_document_content(document_id: str, request: Request):
        with api.read(request) as (c, owner):
            doc, private = get(c, owner, "document", identity(document_id))
        data = api.storage.download(private["storage_path"])
        return Response(data, media_type=doc["mime_type"], headers={
            "Content-Disposition": "inline; filename*=UTF-8''" + quote(doc["name"], safe=""),
            "Cache-Control": "private, no-store"})

    @r.post("/api/v1/documents/{document_id}/analyze", status_code=202)
    def analyze_document(document_id: str, request: Request, body: dict):
        validate("AnalyzeRequest", body)
        with api.write(request) as (c, owner):
            doc, private = get(c, owner, "document", identity(document_id))

            def operation():
                running = [j for j in jobs(c, owner, active_only=True) if j["kind"] == "extract" and j["target_id"] == doc["id"]]
                if running and not body["force"]:
                    return running[0]["body"]
                for job in running:
                    end_job(c, owner, job["id"], "stale")
                if body["force"]:
                    private.pop("extraction", None)  # fresh conversion; source review stays hash-bound
                doc["status"] = "uploaded"
                put(c, owner, "document", doc, private, doc["entry_id"])
                return new_job(c, owner, "extract", doc["id"], {"document_id": doc["id"], "version": doc["version"]})
            return api.idempotent(c, request, owner, body, 202, operation)

    @r.delete("/api/v1/documents/{document_id}", status_code=204)
    def delete_document(document_id: str, request: Request):
        with api.write(request) as (c, owner):
            doc, private = get(c, owner, "document", identity(document_id))
            path = lifecycle.delete_document(c, owner, doc, private)
        purge([path])
        return Response(status_code=204)

    # ── benefits ─────────────────────────────────────────────────────────────────────
    @r.get("/api/v1/benefits")
    def list_benefits(request: Request, entry_id: str | None = None, usage_state: str | None = None, q: str | None = None,
                      cursor: str | None = None, limit: Limit = 25):
        with api.read(request) as (c, owner):
            if entry_id:
                get(c, owner, "entry", identity(entry_id))
            rows = objects(c, owner, "benefit", identity(entry_id) if entry_id else None)
        items = [(b, p) for b, p in rows if (not usage_state or b["usage_state"] == usage_state)]
        if q and q.strip():
            needle = q.strip().lower()
            items = [(b, p) for b, p in items if needle in (b["title"] + " " + b["description"]).lower()]
        items.sort(key=lambda bp: (sort_key(bp[0]["deadline_date"]), bp[1].get("created_at", ""), bp[0]["id"]))
        return page(request, [b for b, _ in items], cursor, limit)

    @r.get("/api/v1/benefits/{benefit_id}")
    def get_benefit(benefit_id: str, request: Request):
        with api.read(request) as (c, owner):
            return envelope(request, get(c, owner, "benefit", identity(benefit_id))[0])

    @r.patch("/api/v1/benefits/{benefit_id}")
    def patch_benefit(benefit_id: str, request: Request, body: dict):
        validate("BenefitPatch", body)
        if "title" in body and not body["title"].strip():
            raise invalid("title must not be empty.")
        with api.write(request) as (c, owner):
            benefit, private = get(c, owner, "benefit", identity(benefit_id))
            expect_version(benefit["data_version"], body["expected_version"])
            if "title" in body:
                benefit["title"] = private["user_title"] = body["title"].strip()
            if body.get("confirmed_review") is True:
                benefit["needs_review"] = False
            if "deadline_date" in body:
                benefit["deadline_date"] = body["deadline_date"]
                benefit["deadline_status"] = domain.deadline_status_after_patch(benefit, body.get("deadline_origin"))
                for reminder, rp in objects(c, owner, "reminder", benefit["id"]):
                    if reminder["case_id"] is None and reminder["status"] != "cancelled" and benefit["deadline_date"]:
                        reminder.update(date=benefit["deadline_date"], status="active")
                        lifecycle.regenerate(c, owner, reminder, rp)
            benefit["data_version"] += 1
            validate("Benefit", benefit, output=True)
            put(c, owner, "benefit", benefit, private, benefit["entry_id"])
            return envelope(request, benefit)

    @r.put("/api/v1/benefits/{benefit_id}/usage")
    def set_benefit_usage(benefit_id: str, request: Request, body: dict):
        validate("UsagePut", body)
        with api.write(request) as (c, owner):
            benefit, private = get(c, owner, "benefit", identity(benefit_id))

            def operation():
                if benefit["units_total"] is not None and body["used_units"] > benefit["units_total"]:
                    raise invalid(f"used_units can't exceed {benefit['units_total']}.")
                expect_version(benefit["data_version"], body["expected_version"])
                domain.apply_usage(benefit, body["used_units"])
                put(c, owner, "benefit", benefit, private, benefit["entry_id"])
                stamp = now()
                c.execute("INSERT INTO claimly.usage_events (id, session_id, benefit_id, outcome_id, source, used_units, quantity, "
                          "note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                          (uid(), owner, benefit["id"], None, "user_usage", body["used_units"], None, body["note"][:2000], stamp, stamp))
                if benefit["usage_state"] == "used":
                    lifecycle.cancel_reminders(c, owner, benefit_ids=[benefit["id"]])
                return benefit
            return api.idempotent(c, request, owner, body, 200, operation)

    # ── threads and messages ─────────────────────────────────────────────────────────
    @r.post("/api/v1/threads", status_code=201)
    def create_thread(request: Request, body: dict):
        validate("ThreadCreate", body)
        scope = body["scope"]
        if scope == "entry" and not body["entry_id"]:
            raise invalid("entry_id is required for entry threads.")
        if scope == "case" and not body["case_id"]:
            raise invalid("case_id is required for case threads.")
        if scope == "vault" and (body["entry_id"] or body["case_id"]):
            raise invalid("Vault threads cannot specify entry_id or case_id.")
        with api.write(request) as (c, owner):
            if body["entry_id"]:
                get(c, owner, "entry", body["entry_id"])
            if body["case_id"]:
                get(c, owner, "case", body["case_id"])
            for doc_id in body["document_ids"]:
                doc, _ = get(c, owner, "document", doc_id)
                if scope == "entry" and doc["entry_id"] != body["entry_id"]:
                    raise invalid("Thread documents must belong to the selected entry.")

            def operation():
                thread = dict(body, id=uid(), created_at=now())
                put(c, owner, "thread", thread, parent=body["entry_id"] or body["case_id"])
                return thread
            return api.idempotent(c, request, owner, body, 201, operation)

    @r.get("/api/v1/threads")
    def list_threads(request: Request, scope: str | None = None, entry_id: str | None = None, case_id: str | None = None,
                     cursor: str | None = None, limit: Limit = 25):
        with api.read(request) as (c, owner):
            items = [t for t, _ in objects(c, owner, "thread") if (not scope or t["scope"] == scope)
                     and (not entry_id or t["entry_id"] == entry_id) and (not case_id or t["case_id"] == case_id)]
        items.sort(key=lambda t: (t["created_at"], t["id"]))
        return page(request, items, cursor, limit)

    @r.get("/api/v1/threads/{thread_id}/messages")
    def list_messages(thread_id: str, request: Request, cursor: str | None = None, limit: Limit = 25):
        with api.read(request) as (c, owner):
            get(c, owner, "thread", identity(thread_id))
            items = [m for m, _ in objects(c, owner, "message", thread_id)]
        items.sort(key=lambda m: (m["created_at"], 0 if m["role"] == "user" else 1, m["id"]))
        return page(request, items, cursor, limit)

    @r.post("/api/v1/threads/{thread_id}/messages", status_code=202)
    def send_message(thread_id: str, request: Request, body: dict):
        validate("MessageCreate", body)
        if not body["content"].strip() or len(body["content"]) > 12000:
            raise invalid("Provide a question of 1 to 12,000 characters.")
        with api.write(request) as (c, owner):
            thread, _ = get(c, owner, "thread", identity(thread_id))

            def operation():
                message = {"id": uid(), "thread_id": thread["id"], "role": "user", "content": body["content"],
                           "evidence_refs": [], "matched_benefit_ids": [], "questions": [], "next_actions": [], "created_at": now()}
                put(c, owner, "message", message, parent=thread["id"])
                job = new_job(c, owner, body["purpose"], thread["id"], {"thread_id": thread["id"], "message_id": message["id"]})
                return {"message": message, "job": job}
            return api.idempotent(c, request, owner, body, 202, operation)

    # ── cases ────────────────────────────────────────────────────────────────────────
    @r.get("/api/v1/cases")
    def list_cases(request: Request, status: str | None = None, entry_id: str | None = None,
                   cursor: str | None = None, limit: Limit = 25):
        with api.read(request) as (c, owner):
            items = [x for x, _ in objects(c, owner, "case") if (not status or x["status"] == status)
                     and (not entry_id or entry_id in x["entry_ids"])]
        items.sort(key=lambda x: x["id"])
        items.sort(key=lambda x: x["updated_at"], reverse=True)
        return page(request, items, cursor, limit)

    def check_links(c, owner, entry_ids, document_ids, benefit_id):
        for eid in entry_ids:
            get(c, owner, "entry", eid)
        for did in document_ids:
            get(c, owner, "document", did)
        if benefit_id:
            get(c, owner, "benefit", benefit_id)

    @r.post("/api/v1/cases", status_code=201)
    def create_case(request: Request, body: dict):
        validate("CaseCreate", body)
        if not body["title"].strip():
            raise invalid("title is required.")
        with api.write(request) as (c, owner):
            check_links(c, owner, body["entry_ids"], body["document_ids"], body["benefit_id"])

            def operation():
                stamp, case_id = now(), uid()
                thread = {"id": uid(), "scope": "case", "entry_id": None, "case_id": case_id,
                          "document_ids": list(body["document_ids"]), "created_at": stamp}
                case = dict(body, id=case_id, title=body["title"].strip(), status="draft", assessment=None,
                            requested_amount_cents=None, approved_amount_cents=None, data_version=1,
                            thread_id=thread["id"], created_at=stamp, updated_at=stamp)
                validate("Case", case, output=True)
                put(c, owner, "case", case, {"content_version": 1})
                put(c, owner, "thread", thread, parent=case_id)
                return case  # creating a case never deducts benefit usage
            return api.idempotent(c, request, owner, body, 201, operation)

    @r.get("/api/v1/cases/{case_id}")
    def get_case(case_id: str, request: Request):
        with api.read(request) as (c, owner):
            return envelope(request, get(c, owner, "case", identity(case_id))[0])

    @r.patch("/api/v1/cases/{case_id}")
    def patch_case(case_id: str, request: Request, body: dict):
        validate("CasePatch", body)
        with api.write(request) as (c, owner):
            case, private = get(c, owner, "case", identity(case_id))
            expect_version(case["data_version"], body["expected_version"])
            check_links(c, owner, [], body.get("document_ids", []), None)
            for key in ("situation", "incident_date", "desired_result", "document_ids"):
                if key in body:
                    case[key] = body[key]
            if "document_ids" in body:
                thread = find(c, owner, "thread", case["thread_id"])
                if thread:
                    thread[0]["document_ids"] = list(body["document_ids"])
                    put(c, owner, "thread", thread[0], thread[1], case["id"])
            lifecycle.touch_case(c, owner, case, private, content=True)
            return envelope(request, case)

    def case_job(request, case_id, kind, payload_extra, idem_payload):
        with api.write(request) as (c, owner):
            case, private = get(c, owner, "case", identity(case_id))

            def operation():
                payload = {"case_id": case["id"], "content_version": private.get("content_version", 1), **payload_extra}
                return new_job(c, owner, kind, case["id"], payload)
            return api.idempotent(c, request, owner, idem_payload, 202, operation)

    @r.post("/api/v1/cases/{case_id}/assess", status_code=202)
    def assess_case(case_id: str, request: Request):
        return case_job(request, case_id, "assess", {}, {"assess": case_id})

    @r.post("/api/v1/cases/{case_id}/status")
    def set_case_status(case_id: str, request: Request, body: dict):
        validate("StatusChange", body)
        with api.write(request) as (c, owner):
            case, private = get(c, owner, "case", identity(case_id))

            def operation():
                expect_version(case["data_version"], body["expected_version"])
                case["status"] = body["status"]
                if body["approved_amount_cents"] is not None:
                    case["approved_amount_cents"] = body["approved_amount_cents"]
                lifecycle.touch_case(c, owner, case, private)
                event = {"id": uid(), "case_id": case["id"], "type": "status_change", "event_date": body["event_date"],
                         "note": body["note"], "attachment_document_ids": [], "new_status": case["status"], "reply_analysis": None}
                put(c, owner, "event", event, parent=case["id"])
                if case["status"] == "resolved":
                    lifecycle.cancel_reminders(c, owner, case_id=case["id"])
                return case
            return api.idempotent(c, request, owner, body, 200, operation)

    @r.get("/api/v1/cases/{case_id}/events")
    def list_case_events(case_id: str, request: Request, cursor: str | None = None, limit: Limit = 25):
        with api.read(request) as (c, owner):
            get(c, owner, "case", identity(case_id))
            items = [e for e, _ in objects(c, owner, "event", case_id)]
        items.sort(key=lambda e: (e["event_date"], e["id"]))
        return page(request, items, cursor, limit)

    @r.post("/api/v1/cases/{case_id}/events", status_code=201)
    def add_case_note(case_id: str, request: Request, body: dict):
        validate("EventCreate", body)
        if not body["note"].strip():
            raise invalid("note must not be empty.")
        with api.write(request) as (c, owner):
            case, _ = get(c, owner, "case", identity(case_id))
            check_links(c, owner, [], body["attachment_document_ids"], None)

            def operation():
                event = {"id": uid(), "case_id": case["id"], "type": "note", "event_date": body["event_date"], "note": body["note"],
                         "attachment_document_ids": body["attachment_document_ids"], "new_status": None, "reply_analysis": None}
                put(c, owner, "event", event, parent=case["id"])
                return event
            return api.idempotent(c, request, owner, body, 201, operation)

    @r.post("/api/v1/cases/{case_id}/replies", status_code=202)
    def analyze_company_reply(case_id: str, request: Request, body: dict):
        validate("ReplyCreate", body)
        if not body["reply_text"].strip() and not body["document_ids"]:
            raise invalid("Paste the reply text or choose a document.")
        if len(body["reply_text"]) > 20000:
            raise invalid("reply_text must be at most 20,000 characters.")
        with api.read(request) as (c, owner):
            check_links(c, owner, [], body["document_ids"], None)
        return case_job(request, case_id, "analyze_reply", {"reply_text": body["reply_text"], "document_ids": body["document_ids"]}, body)

    @r.get("/api/v1/cases/{case_id}/drafts")
    def list_drafts(case_id: str, request: Request, cursor: str | None = None, limit: Limit = 25):
        with api.read(request) as (c, owner):
            get(c, owner, "case", identity(case_id))
            items = [d for d, _ in objects(c, owner, "draft", case_id)]
        items.sort(key=lambda d: d["id"])
        items.sort(key=lambda d: d["updated_at"], reverse=True)
        return page(request, items, cursor, limit)

    @r.post("/api/v1/cases/{case_id}/drafts", status_code=202)
    def create_draft(case_id: str, request: Request, body: dict):
        validate("DraftCreate", body)
        kind = "draft_follow_up" if body["kind"] == "follow_up" else "draft"
        return case_job(request, case_id, kind, {"kind": body["kind"]}, body)

    @r.patch("/api/v1/drafts/{draft_id}")
    def edit_draft(draft_id: str, request: Request, body: dict):
        validate("DraftPatch", body)
        with api.write(request) as (c, owner):
            draft, private = get(c, owner, "draft", identity(draft_id))
            if body["expected_input_version"] != draft["input_version"]:
                raise conflict("This draft was regenerated. Reload it before saving your edits.")
            draft["content"] = dict(draft["content"], subject=body["subject"], body=body["body"])
            draft.update(user_edited=True, updated_at=now())
            validate("Draft", draft, output=True)
            put(c, owner, "draft", draft, private, draft["case_id"])
            return envelope(request, draft)  # drafts are never sent automatically

    @r.get("/api/v1/cases/{case_id}/outcome")
    def get_outcome(case_id: str, request: Request):
        with api.read(request) as (c, owner):
            get(c, owner, "case", identity(case_id))
            found = [o for o, _ in objects(c, owner, "outcome", case_id)]
        if not found:
            raise not_found("Outcome")
        return envelope(request, found[0])

    @r.put("/api/v1/cases/{case_id}/outcome")
    def set_outcome(case_id: str, request: Request, body: dict):
        validate("OutcomePut", body)
        if body["kind"] == "cash_refund" and body["cash_amount_cents"] is None:
            raise invalid("cash_amount_cents is required for cash_refund.")
        if body["kind"] != "cash_refund" and body["cash_amount_cents"] is not None:
            raise invalid("cash_amount_cents must be null for non-cash outcomes.")
        with api.write(request) as (c, owner):
            case, cp = get(c, owner, "case", identity(case_id))
            if body["benefit_id"]:
                get(c, owner, "benefit", body["benefit_id"])
            for ref in body["evidence_refs"]:
                get(c, owner, "document", ref["document_id"])
            return api.idempotent(c, request, owner, body, 200, lambda: apply_outcome(c, owner, case, cp, body))

    def apply_outcome(c, owner, case, cp, body):
        previous = [o for o, _ in objects(c, owner, "outcome", case["id"])]
        outcome_id = previous[0]["id"] if previous else uid()
        outcome = dict(body, id=outcome_id, case_id=case["id"])
        validate("Outcome", outcome, output=True)
        event = c.execute("SELECT * FROM claimly.usage_events WHERE session_id=? AND outcome_id=?", (owner, outcome_id)).fetchone()
        # 1) Revert this outcome's single usage event (quantity stores the delta actually applied).
        if event:
            found = find(c, owner, "benefit", event["benefit_id"])
            if found:
                change_usage(c, owner, *found, -(event["quantity"] or 0))
            c.execute("DELETE FROM claimly.usage_events WHERE session_id=? AND outcome_id=?", (owner, outcome_id))
        # 2) Apply the corrected quantity once, linked to outcome_id; repeats converge to the same state.
        wanted = (body["quantity"] or 0) if body["kind"] in ("service_used", "voucher_used") and body["benefit_id"] else 0
        if wanted:
            benefit, bp = get(c, owner, "benefit", body["benefit_id"])
            applied = change_usage(c, owner, benefit, bp, wanted)
            stamp = now()
            c.execute("INSERT INTO claimly.usage_events (id, session_id, benefit_id, outcome_id, source, used_units, quantity, "
                      "note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (uid(), owner, benefit["id"], outcome_id, "outcome", benefit["used_units"] or 0, applied,
                       body["note"][:2000], stamp, stamp))
        put(c, owner, "outcome", outcome, {}, case["id"])
        note = body["note"] or "Outcome: " + body["kind"].replace("_", " ")
        put(c, owner, "event", {"id": uid(), "case_id": case["id"], "type": "outcome", "event_date": body["confirmed_at"],
                                "note": note, "attachment_document_ids": [], "new_status": None, "reply_analysis": None},
            parent=case["id"])
        lifecycle.touch_case(c, owner, case, cp)
        return outcome

    def change_usage(c, owner, benefit, bp, delta: int) -> int:
        """Apply a usage delta; returns the delta actually applied (bounded by 0 and units_total)."""
        before = benefit["used_units"] or 0
        after = max(0, before + delta)
        if benefit["units_total"] is not None:
            after = min(benefit["units_total"], after)
        if benefit["usage_state"] == "unknown":
            # Prior usage baseline is unknown: record the known minimum, never compute a full remainder.
            benefit.update(used_units=after or None, remaining_units=None)
            benefit["data_version"] += 1
        else:
            domain.apply_usage(benefit, after)
        put(c, owner, "benefit", benefit, bp, benefit["entry_id"])
        return after - before

    # ── reminders and notifications ──────────────────────────────────────────────────
    def reminder_checks(body):
        if "date" in body and not domain.valid_date(body["date"]):
            raise invalid("date must be YYYY-MM-DD.")
        if "timezone" in body and not domain.valid_timezone(body["timezone"]):
            raise invalid("timezone must be an IANA time zone.")
        if "local_time" in body and not domain.TIME_RE.match(body["local_time"]):
            raise invalid("local_time must be HH:MM.")
        if "email" in body.get("channels", []) and not settings.email_configured:
            raise invalid("Email delivery is not configured on this server.")

    @r.get("/api/v1/reminders")
    def list_reminders(request: Request, from_date: str | None = None, to_date: str | None = None, benefit_id: str | None = None,
                       case_id: str | None = None, cursor: str | None = None, limit: Limit = 25):
        with api.read(request) as (c, owner):
            items = [x for x, _ in objects(c, owner, "reminder") if (not from_date or x["date"] >= from_date)
                     and (not to_date or x["date"] <= to_date) and (not benefit_id or x["benefit_id"] == benefit_id)
                     and (not case_id or x["case_id"] == case_id)]
        items.sort(key=lambda x: (x["date"], x["local_time"], x["id"]))
        return page(request, items, cursor, limit)

    @r.post("/api/v1/reminders", status_code=201)
    def create_reminder(request: Request, body: dict):
        validate("ReminderCreate", body)
        if not body["title"].strip():
            raise invalid("title is required.")
        reminder_checks(body)
        with api.write(request) as (c, owner):
            if body["benefit_id"]:
                get(c, owner, "benefit", body["benefit_id"])
            if body["case_id"]:
                get(c, owner, "case", body["case_id"])
            for ref in body["evidence_refs"]:
                get(c, owner, "document", ref["document_id"])

            def operation():
                reminder = dict(body, id=uid())
                validate("Reminder", reminder, output=True)
                lifecycle.regenerate(c, owner, reminder, {})
                return reminder
            return api.idempotent(c, request, owner, body, 201, operation)

    @r.patch("/api/v1/reminders/{reminder_id}")
    def patch_reminder(reminder_id: str, request: Request, body: dict):
        validate("ReminderPatch", body)
        reminder_checks(body)
        with api.write(request) as (c, owner):
            reminder, private = get(c, owner, "reminder", identity(reminder_id))
            reminder.update(body)
            validate("Reminder", reminder, output=True)
            lifecycle.regenerate(c, owner, reminder, private)  # old pending deliveries are cancelled
            return envelope(request, reminder)

    @r.get("/api/v1/notifications")
    def list_notifications(request: Request, cursor: str | None = None, limit: Limit = 25):
        with api.read(request) as (c, owner):
            items = [n for n, _ in objects(c, owner, "notification") if n["status"] != "cancelled"]
        items.sort(key=lambda n: n["id"])
        items.sort(key=lambda n: n["scheduled_at"], reverse=True)
        return page(request, items, cursor, limit)

    @r.post("/internal/v1/reminders/dispatch")
    def dispatch_reminders(request: Request):
        expected = "Bearer " + settings.scheduler_secret
        if not settings.scheduler_secret or not hmac.compare_digest(request.headers.get("Authorization", ""), expected):
            raise ApiError(401, "UNAUTHORIZED", "A scheduler secret is required.")
        with api.db.tx(write=True) as c:
            c.lock("claimly-dispatch")
            data = lifecycle.dispatch_due(c, None, settings)
        validate("DispatchResult", data, output=True)
        return envelope(request, data)

    # ── jobs ─────────────────────────────────────────────────────────────────────────
    @r.get("/api/v1/jobs/{job_id}")
    def get_job_route(job_id: str, request: Request):
        with api.read(request) as (c, owner):
            body, _ = get_job(c, owner, identity(job_id))
        return envelope(request, body)

    return r
