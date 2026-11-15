"""Durable worker: python -m app.worker. Survives restarts (Postgres-backed leases), retries with
limits, checks source versions/leases before atomically publishing results, never fabricates
model output. Backend owns admission, sources, vectors, usage, deadlines and case state."""

from __future__ import annotations

import hashlib
import logging
import os
import signal
import socket
import time
from datetime import datetime, timezone

from app import context as ctx
from app import lifecycle
from app.contract import validate
from app.db import Database, finish, find, get, lease_active, new_job, now, objects, put, uid, encoded, jobs
from app.errors import ApiError, as_api_error
from app.llm_client import HttpLlmClient
from app.settings import Settings
from app.storage import make_storage
from services.llm.app import contracts as llm_contracts
from services.llm.app.config import Settings as LlmSettings
from services.llm.rag.runtime import chunks_for_pages, page_hash

LOG = logging.getLogger("claimly.worker")
EMBED_BATCH = 16


class Worker:
    def __init__(self, settings: Settings | None = None, *, db=None, storage=None, llm=None, embedder=None):
        self.settings = settings or Settings.from_env()
        self.db = db or Database(self.settings)
        self._storage, self.llm, self._embedder = storage, llm or HttpLlmClient(self.settings), embedder
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"

    @property
    def storage(self):
        if self._storage is None:
            self._storage = make_storage(self.settings)
        return self._storage

    @property
    def embedder(self):
        if self._embedder is None:
            from services.llm.app.embeddings import make_embedder
            self._embedder = make_embedder(LlmSettings.env())
        return self._embedder

    # ── loop ─────────────────────────────────────────────────────────────────────────
    def once(self) -> bool:
        claimed = self.db.claim(self.worker_id)
        if claimed is None:
            return False
        handler = {"extract": self.extract, "answer": self.answer, "match_need": self.answer, "assess": self.assess,
                   "draft": self.draft, "draft_follow_up": self.draft, "analyze_reply": self.analyze_reply}.get(claimed["kind"])
        started = time.monotonic()
        try:
            with self.db.tx() as c:
                row = c.execute("SELECT expires_at FROM claimly.demo_sessions WHERE id=?", (claimed["session_id"],)).fetchone()
            if row is None or row["expires_at"] < time.time():
                raise ApiError(409, "STALE_INPUT", "The demo session expired.")
            if handler is None:
                raise ApiError(422, "VALIDATION_ERROR", "Unsupported job kind.")
            handler(claimed)
        except Exception as raw:  # noqa: BLE001 - every failure is converted to a curated public error
            error = as_api_error(raw) if hasattr(raw, "code") else ApiError(500, "INTERNAL_ERROR", "The worker could not complete this job.", True)
            if not hasattr(raw, "code"):
                LOG.error("job_error kind=%s type=%s", claimed["kind"], type(raw).__name__)
            self.fail(claimed, error)
        LOG.info("job kind=%s attempt=%s elapsed_ms=%d", claimed["kind"], claimed["attempts"], (time.monotonic() - started) * 1000)
        return True

    def fail(self, claimed: dict, error: ApiError) -> None:
        owner = claimed["session_id"]
        status = "stale" if error.code in ("STALE_INPUT", "NOT_FOUND") else None
        paths = []
        try:
            with self.db.tx(write=True) as c:
                body = finish(c, claimed, failure=error, status=status, max_attempts=self.settings.max_attempts)
                if claimed["kind"] != "extract" or body["status"] == "queued":
                    return
                found = find(c, owner, "document", claimed["payload"]["document_id"])
                if found is None:
                    return
                doc, private = found
                if error.code == "VALIDATION_ERROR" and error.message.startswith("Out of scope:"):
                    # Unrelated content never enters the Vault; original is deleted (tombstoned).
                    paths.append(lifecycle.delete_document(c, owner, doc, private))
                    entry = find(c, owner, "entry", doc["entry_id"])
                    if entry and not entry[1].get("admitted") and not entry[0]["document_ids"]:
                        paths += lifecycle.delete_entry(c, owner, *entry)
                elif body["status"] == "failed":
                    doc["status"] = "failed"
                    doc["review_flags"] = list(dict.fromkeys(doc["review_flags"] + [error.code]))
                    put(c, owner, "document", doc, private, doc["entry_id"])
        except ApiError:
            pass  # deletion/cancellation/lease replacement already made the job inactive
        for path in paths:
            self.purge(path)

    def purge(self, path: str) -> None:
        """Delete an original after its tombstone committed; maintenance retries failures."""
        try:
            self.storage.delete(path)
        except Exception:  # noqa: BLE001
            return
        with self.db.tx(write=True) as c:
            c.execute("DELETE FROM claimly.storage_tombstones WHERE storage_path=?", (path,))

    # ── extract → review gate → index → publish ──────────────────────────────────────
    def extract(self, claimed: dict) -> None:
        owner, doc_id = claimed["session_id"], claimed["payload"]["document_id"]
        with self.db.tx(write=True) as c:
            doc, private = get(c, owner, "document", doc_id)
            if doc["version"] != claimed["payload"]["version"]:
                raise ApiError(409, "STALE_INPUT", "The document version changed.")
            doc["status"] = "processing"
            put(c, owner, "document", doc, private, doc["entry_id"])
        output = private.get("extraction")
        if output is None:
            data = self.storage.download(private["storage_path"])
            if hashlib.sha256(data).hexdigest() != private["source_sha256"]:
                raise ApiError(409, "STALE_INPUT", "The stored original does not match its recorded hash.")
            metadata = {"request_id": claimed["id"], "contract_version": "2.0.0", "document_id": doc_id,
                        "document_version": doc["version"], "filename": doc["name"], "mime_type": doc["mime_type"]}
            output = self.llm.extract(data, metadata, datetime.now(timezone.utc).date().isoformat())
            llm_contracts.extraction_check(output, {"document_id": doc_id, "document_version": doc["version"], "pages": output["pages"]})
            with self.db.tx(write=True) as c:
                latest, lp = get(c, owner, "document", doc_id)
                if latest["version"] != doc["version"] or not lease_active(c, claimed):
                    raise ApiError(409, "STALE_INPUT", "The document changed during conversion.")
                lp.update(extraction=output, pages_sha256=page_hash(output["pages"]))
                put(c, owner, "document", latest, lp, latest["entry_id"])
                private = lp
        blocked = "quality:blocked" in output["review_flags"]
        uncertain_pages = any(p["needs_review"] for p in output["pages"])
        review = private.get("quality_review") or {}
        approved = review.get("source_sha256") == private["source_sha256"] and review.get("pages_sha256") == private["pages_sha256"]
        user_mode = self.settings.source_review_mode == "user_confirmation" and not blocked and not uncertain_pages
        if blocked or not (approved or user_mode):
            with self.db.tx(write=True) as c:
                latest, lp = get(c, owner, "document", doc_id)
                if latest["version"] != doc["version"]:
                    raise ApiError(409, "STALE_INPUT", "The document changed during conversion.")
                latest.update(status="needs_review", page_count=len(output["pages"]),
                              review_flags=list(dict.fromkeys(output["review_flags"] +
                                                              ([] if blocked else ["quality:operator_review_pending"]))))
                put(c, owner, "document", latest, lp, latest["entry_id"])
                finish(c, claimed, result={"type": "extract", "document_id": doc_id, "benefit_ids": [], "review_required": True})
            return
        embedder = self.embedder
        chunks = chunks_for_pages(doc_id, doc["version"], output["pages"], embedder)
        vectors = []
        for offset in range(0, len(chunks), EMBED_BATCH):
            vectors.extend(embedder.embed([x["contextualized_text"] for x in chunks[offset:offset + EMBED_BATCH]]))
        if not chunks or len(vectors) != len(chunks):
            raise ApiError(502, "INVALID_LLM_OUTPUT", "The index batch is incomplete.")
        profile = embedder.embedding_identity
        with self.db.tx(write=True) as c:
            latest, lp = get(c, owner, "document", doc_id)
            if latest["version"] != doc["version"] or lp.get("pages_sha256") != private["pages_sha256"]:
                raise ApiError(409, "STALE_INPUT", "The source changed during indexing.")
            entry, ep = get(c, owner, "entry", latest["entry_id"])
            finish(c, claimed, result=None)  # lease check before publishing any derived state (same transaction)
            c.execute("DELETE FROM claimly.session_chunks WHERE session_id=? AND document_id=?", (owner, doc_id))
            for chunk, vector in zip(chunks, vectors, strict=True):
                c.execute("INSERT INTO claimly.session_chunks (session_id, chunk_id, document_id, document_version, profile, chunk, vector) "
                          "VALUES (?,?,?,?,?,?,?)", (owner, chunk["chunk_id"], doc_id, latest["version"], profile, encoded(chunk), encoded(vector)))
            facts, candidates = output["facts"], output["benefits"]
            if user_mode and not approved:
                # No operator verified this conversion: every extracted fact/benefit requires user confirmation.
                facts = {k: dict(v, needs_review=True) for k, v in facts.items()}
                candidates = [dict(b, needs_review=True) for b in candidates]
                lp["quality_review"] = {"mode": "user_confirmation", "source_sha256": lp["source_sha256"],
                                        "pages_sha256": lp["pages_sha256"], "at": now()}
            entry["category"] = output["category"]  # readable content decides; filenames/user categories cannot
            if not ep.get("user_title"):
                entry["title"] = output["title"]
            entry["provider"] = entry["provider"] or output["provider"]
            entry["subject"] = entry["subject"] or output["subject"]
            for key, fact in facts.items():
                if entry["facts"].get(key, {}).get("origin") != "user":
                    entry["facts"][key] = fact
            prof = lifecycle.profile(c, owner, self.settings)
            benefit_ids = lifecycle.upsert_benefits(c, owner, entry, doc_id, candidates, prof["timezone"], prof)
            needs_user = any(f["needs_review"] for f in facts.values()) or any(b["needs_review"] for b in candidates)
            flags = [f for f in output["review_flags"] if f not in ("quality:source_review_required",)]
            latest.update(status="needs_review" if needs_user else "ready", facts=facts, page_count=len(output["pages"]),
                          review_flags=flags)
            lp.update(embedding_profile=profile, populated=True)
            put(c, owner, "document", latest, lp, entry["id"])
            ep["admitted"] = True
            put(c, owner, "entry", entry, ep)
            lifecycle.refresh_entry(c, owner, entry, ep)
            self._set_result(c, claimed, {"type": "extract", "document_id": doc_id, "benefit_ids": benefit_ids,
                                          "review_required": needs_user})

    def _set_result(self, c, claimed, result):
        import json
        row = c.execute("SELECT body FROM claimly.session_jobs WHERE id=? AND session_id=?", (claimed["id"], claimed["session_id"])).fetchone()
        body = json.loads(row["body"])
        body["result"] = result
        validate("Job", body, output=True)
        c.execute("UPDATE claimly.session_jobs SET body=? WHERE id=? AND session_id=?", (encoded(body), claimed["id"], claimed["session_id"]))

    # ── shared retrieval ─────────────────────────────────────────────────────────────
    def _retrieve(self, owner: str, question: str, *, entry_id=None, document_ids=None, include_all_small=False):
        embedder = self.embedder
        profile = embedder.embedding_identity
        with self.db.tx(write=True) as c:
            docs, stale = ctx.indexed_documents(c, owner, profile, entry_id=entry_id, document_ids=document_ids)
            for doc, _ in stale:
                # Index profile changed: re-index from the cached conversion (no new extraction call).
                if not any(j["kind"] == "extract" and j["target_id"] == doc["id"] for j in jobs(c, owner, active_only=True)):
                    new_job(c, owner, "extract", doc["id"], {"document_id": doc["id"], "version": doc["version"]})
            rows = ctx.candidate_rows(c, owner, docs, profile)
        query_vector = embedder.embed([question], query=True)[0] if rows else None
        return docs, ctx.select_pages(question, rows, query_vector, docs, include_all_small=include_all_small), profile

    def _verify_sources(self, c, owner, documents, entries, profile):
        for d in documents:
            found = find(c, owner, "document", d["document_id"])
            if (found is None or found[0]["version"] != d["document_version"] or not found[1].get("populated")
                    or found[1].get("embedding_profile") != profile):
                raise ApiError(409, "STALE_INPUT", "A supporting document changed while the result was generated.")
        for entry in entries:
            found = find(c, owner, "entry", entry["id"])
            if found is None or found[0]["data_version"] != entry["data_version"]:
                raise ApiError(409, "STALE_INPUT", "Entry facts changed while the result was generated.")

    # ── answer / match_need ──────────────────────────────────────────────────────────
    def answer(self, claimed: dict) -> None:
        owner, thread_id = claimed["session_id"], claimed["payload"]["thread_id"]
        with self.db.tx() as c:
            thread, _ = get(c, owner, "thread", thread_id)
            message, _ = get(c, owner, "message", claimed["payload"]["message_id"])
            case = get(c, owner, "case", thread["case_id"])[0] if thread["scope"] == "case" else None
            allowed = ctx.case_scope(c, owner, case) if case else None
            if thread["document_ids"]:
                allowed = set(thread["document_ids"]) if allowed is None else allowed & set(thread["document_ids"])
            hist = ctx.history(c, owner, thread_id, message["created_at"])
        docs, documents, profile = self._retrieve(owner, message["content"], entry_id=thread["entry_id"] if thread["scope"] == "entry" else None,
                                                  document_ids=allowed)
        with self.db.tx() as c:
            entries, benefits = ctx.related(c, owner, docs, extra_entry_ids=[thread["entry_id"]] if thread["entry_id"] else ())
            context = ctx.base_context(c, owner, self.settings, entries=entries, benefits=benefits, documents=documents,
                                       hist=hist, case=case)
        request = {"request_id": claimed["id"], "contract_version": "2.0.0", "question": message["content"], "context": context}
        output = (self.llm.match if claimed["kind"] == "match_need" else self.llm.answer)(request)
        llm_contracts.answer_check(output, context)  # defence in depth: citations/IDs re-checked by Backend
        with self.db.tx(write=True) as c:
            get(c, owner, "thread", thread_id)
            self._verify_sources(c, owner, documents, entries, profile)
            assistant = {"id": uid(), "thread_id": thread_id, "role": "assistant", "content": output["answer"],
                         "evidence_refs": output["evidence_refs"], "matched_benefit_ids": output["matched_benefit_ids"],
                         "questions": output["questions"], "next_actions": output["next_actions"], "created_at": now()}
            validate("ChatMessage", assistant, output=True)
            finish(c, claimed, result={"type": claimed["kind"], "assistant_message": assistant})
            put(c, owner, "message", assistant, parent=thread_id)

    # ── case operations ──────────────────────────────────────────────────────────────
    def _case(self, claimed: dict):
        owner = claimed["session_id"]
        with self.db.tx() as c:
            case, private = get(c, owner, "case", claimed["payload"]["case_id"])
            if private.get("content_version", 1) != claimed["payload"]["content_version"]:
                raise ApiError(409, "STALE_INPUT", "The case changed while this was running. Run it again.")
            allowed = ctx.case_scope(c, owner, case)
            benefit = find(c, owner, "benefit", case["benefit_id"]) if case["benefit_id"] else None
        question = " ".join(x for x in [case["title"], case["situation"], case["desired_result"] or "",
                                        benefit[0]["title"] if benefit else ""] if x)
        docs, documents, profile = self._retrieve(owner, question, document_ids=allowed, include_all_small=True)
        with self.db.tx() as c:
            entries, benefits = ctx.related(c, owner, docs, extra_entry_ids=case["entry_ids"])
            context = ctx.base_context(c, owner, self.settings, entries=entries, benefits=benefits, documents=documents,
                                       hist=[], case=case)
        return owner, case, context, profile

    def _publish_case(self, c, claimed, owner, context, profile):
        case, private = get(c, owner, "case", claimed["payload"]["case_id"])
        if private.get("content_version", 1) != claimed["payload"]["content_version"]:
            raise ApiError(409, "STALE_INPUT", "The case changed while this was running. Run it again.")
        self._verify_sources(c, owner, context["documents"], context["entries"], profile)
        return case, private

    def assess(self, claimed: dict) -> None:
        owner, case, context, profile = self._case(claimed)
        output = self.llm.assess({"request_id": claimed["id"], "contract_version": "2.0.0", "context": context})
        llm_contracts.guard_assessment(output, context)
        with self.db.tx(write=True) as c:
            case, private = self._publish_case(c, claimed, owner, context, profile)
            case["assessment"] = output
            finish(c, claimed, result={"type": "assess", "case_id": case["id"], "assessment": output})
            lifecycle.touch_case(c, owner, case, private)

    def draft(self, claimed: dict) -> None:
        owner, case, context, profile = self._case(claimed)
        kind = claimed["payload"]["kind"]
        reply = None
        if kind == "follow_up":
            with self.db.tx() as c:
                replies = sorted([e for e, _ in objects(c, owner, "event", case["id"]) if e["type"] == "company_reply"],
                                 key=lambda e: (e["event_date"], e["id"]))
            reply = replies[-1]["note"] if replies else None
        output = self.llm.draft({"request_id": claimed["id"], "contract_version": "2.0.0", "kind": kind, "context": context,
                                 "assessment": case["assessment"], "company_reply": reply})
        llm_contracts.guard_draft(output, context, reply or "")
        with self.db.tx(write=True) as c:
            case, private = self._publish_case(c, claimed, owner, context, profile)
            if kind == "initial" and case["status"] == "draft":
                case["status"] = "prepared"
            lifecycle.touch_case(c, owner, case, private)
            draft = {"id": uid(), "case_id": case["id"], "kind": kind, "content": output, "input_version": case["data_version"],
                     "user_edited": False, "stale": False, "updated_at": now()}
            validate("Draft", draft, output=True)
            put(c, owner, "draft", draft, parent=case["id"])
            put(c, owner, "event", {"id": uid(), "case_id": case["id"], "type": "draft_created", "event_date": now(),
                                    "note": "Follow-up draft prepared." if kind == "follow_up" else "Request draft prepared.",
                                    "attachment_document_ids": [], "new_status": None, "reply_analysis": None}, parent=case["id"])
            finish(c, claimed, result={"type": claimed["kind"], "draft": draft})

    def analyze_reply(self, claimed: dict) -> None:
        owner, case, context, profile = self._case(claimed)
        reply_ids = claimed["payload"]["document_ids"]
        with self.db.tx() as c:
            for doc_id in reply_ids:
                doc, private = get(c, owner, "document", doc_id)
                if not private.get("extraction"):
                    raise ApiError(422, "VALIDATION_ERROR", "A reply document has not finished processing yet.")
                if doc_id not in {d["document_id"] for d in context["documents"]}:
                    context["documents"].append({"document_id": doc_id, "document_version": doc["version"], "name": doc["name"],
                                                 "pages": private["extraction"]["pages"]})
        request = {"request_id": claimed["id"], "contract_version": "2.0.0", "context": context,
                   "reply_text": claimed["payload"]["reply_text"], "reply_document_ids": reply_ids}
        output = self.llm.analyze_reply(request)
        llm_contracts.guard_reply(output, context)
        with self.db.tx(write=True) as c:
            case, private = get(c, owner, "case", claimed["payload"]["case_id"])
            self._verify_sources(c, owner, [d for d in context["documents"] if d["document_id"] not in reply_ids],
                                 context["entries"], profile)
            for doc_id in reply_ids:
                found = find(c, owner, "document", doc_id)
                if found is None:
                    raise ApiError(409, "STALE_INPUT", "A reply document was deleted.")
            text = claimed["payload"]["reply_text"].strip()
            event = {"id": uid(), "case_id": case["id"], "type": "company_reply", "event_date": now(),
                     "note": text or "Company reply attached as a document.", "attachment_document_ids": reply_ids,
                     "new_status": None, "reply_analysis": output}
            validate("CaseEvent", event, output=True)
            put(c, owner, "event", event, parent=case["id"])
            finish(c, claimed, result={"type": "analyze_reply", "case_id": case["id"], "event": event})
            lifecycle.touch_case(c, owner, case, private)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from app.maintenance import Maintenance

    worker = Worker()
    maintenance = Maintenance(worker.settings, worker.db, lambda: worker.storage)
    stopping = {"flag": False}

    def stop(*_):
        stopping["flag"] = True  # finish the current job; unfinished leases are reclaimed after expiry
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    LOG.info("worker started id=%s", worker.worker_id)
    idle = 0.5
    while not stopping["flag"]:
        maintenance.tick()
        try:
            busy = worker.once()
        except ApiError as error:  # database unavailable: back off, never crash-loop
            LOG.warning("worker_unavailable code=%s", error.code)
            busy = False
            idle = min(30.0, idle * 2)
        else:
            idle = 0.5
        if not busy:
            time.sleep(idle)


if __name__ == "__main__":
    main()
