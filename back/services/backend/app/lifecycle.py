"""State transitions shared by API routes, the worker and maintenance. All calls run inside one
caller-owned transaction and filter by the Backend-resolved session owner."""

from __future__ import annotations

import time
from uuid import UUID, uuid5

from app import domain
from app.contract import validate
from app.db import Connection, end_job, find, get, jobs, now, objects, put, remove
from app.settings import Settings

DELETED_ANSWER = "This response is unavailable because a supporting source was deleted."


def profile(c: Connection, owner: str, settings: Settings) -> dict:
    found = find(c, owner, "profile", owner)
    body = found[0] if found else domain.default_profile(settings.email_configured)
    body = {k: v for k, v in body.items() if k != "id"}
    body["email_configured"] = settings.email_configured
    return body


def save_profile(c: Connection, owner: str, body: dict) -> None:
    put(c, owner, "profile", dict(body, id=owner))


# ── reminders ────────────────────────────────────────────────────────────────────────
def regenerate(c: Connection, owner: str, reminder: dict, private: dict) -> None:
    """Cancel pending deliveries of the previous revision, then plan the new revision."""
    for note, np in objects(c, owner, "notification", reminder["id"]):
        if note["status"] == "pending":
            note["status"] = "cancelled"
            put(c, owner, "notification", note, np, reminder["id"])
    private["revision"] = private.get("revision", 0) + 1
    put(c, owner, "reminder", reminder, private, reminder.get("benefit_id") or reminder.get("case_id"))
    for note in domain.planned_notifications(reminder, private["revision"]):
        validate("Notification", note, output=True)
        if find(c, owner, "notification", note["id"]) is None:
            put(c, owner, "notification", note, {"attempts": 0}, reminder["id"])


def cancel_reminders(c: Connection, owner: str, *, benefit_ids=(), case_id: str | None = None) -> None:
    for reminder, rp in objects(c, owner, "reminder"):
        if reminder["status"] == "cancelled":
            continue
        if reminder["benefit_id"] in set(benefit_ids) or (case_id and reminder["case_id"] == case_id):
            reminder["status"] = "cancelled"
            regenerate(c, owner, reminder, rp)


def dispatch_due(c: Connection, owner: str | None, settings: Settings) -> dict:
    """Idempotent: a delivery row is sent at most once; repeats find no pending rows."""
    stamp = now()
    result = {"processed": 0, "sent": 0, "failed": 0, "cancelled": 0}
    sql = "SELECT session_id, body, private FROM claimly.session_objects WHERE kind='notification'"
    rows = c.execute(sql + (" AND session_id=?" if owner else ""), (owner,) if owner else ()).fetchall()
    import json
    for row in rows:
        note, private = json.loads(row["body"]), json.loads(row["private"])
        if note["status"] != "pending" or note["scheduled_at"] > stamp:
            continue
        reminder = find(c, row["session_id"], "reminder", note["reminder_id"])
        result["processed"] += 1
        if reminder is None or reminder[0]["status"] != "active":
            note["status"] = "cancelled"
            result["cancelled"] += 1
        elif note["channel"] == "email":
            # No email provider is configured/implemented: report failure honestly, never "sent".
            note["status"] = "failed"
            result["failed"] += 1
        else:
            note["status"], note["sent_at"] = "sent", stamp
            result["sent"] += 1
        put(c, row["session_id"], "notification", note, private, note["reminder_id"])
    return result


# ── benefits ─────────────────────────────────────────────────────────────────────────
def benefit_id(document_id: str, candidate_key: str) -> str:
    return str(uuid5(UUID(document_id), candidate_key))


def upsert_benefits(c: Connection, owner: str, entry: dict, document_id: str, candidates: list[dict], timezone: str,
                    prof: dict) -> list[str]:
    """Create/refresh benefits idempotently from candidates; usage and user edits are preserved."""
    ids = []
    for candidate in candidates:
        base = {k: v for k, v in candidate.items() if k != "candidate_key"}
        bid = benefit_id(document_id, candidate["candidate_key"])
        deadline, status, reminder_date, confirmed = domain.initial_deadline(candidate, entry["facts"])
        existing = find(c, owner, "benefit", bid)
        if existing:
            benefit, bp = existing
            keep = {k: benefit[k] for k in ("usage_state", "used_units", "remaining_units")}
            user_deadline = benefit["deadline_status"] == "user_set"
            user_title = bp.get("user_title")
            benefit.update(base, **keep)
            if user_title:
                benefit["title"] = user_title
            if not user_deadline:
                benefit.update(deadline_date=deadline, deadline_status=status)
            benefit["data_version"] += 1
        else:
            bp = {"document_id": document_id, "created_at": now()}
            benefit = dict(base, id=bid, entry_id=entry["id"], usage_state="unknown", used_units=None, remaining_units=None,
                           deadline_date=deadline, deadline_status=status, data_version=1)
        validate("Benefit", benefit, output=True)
        put(c, owner, "benefit", benefit, bp, entry["id"])
        ids.append(bid)
        if reminder_date:
            rid = str(uuid5(UUID(bid), "deadline"))
            found = find(c, owner, "reminder", rid)
            if found is None or found[0]["origin"] == "document":
                reminder = {"id": rid, "benefit_id": bid, "case_id": None, "title": benefit["title"], "date": reminder_date,
                            "timezone": prof["timezone"] if domain.valid_timezone(prof["timezone"]) else timezone,
                            "local_time": prof["local_notification_time"], "origin": "document",
                            "offset_days": list(prof["reminder_offsets"]), "channels": ["in_app"],
                            "status": "active" if confirmed else "needs_review",
                            "evidence_refs": (candidate["deadline_rule"] or {}).get("evidence_refs", [])}
                validate("Reminder", reminder, output=True)
                regenerate(c, owner, reminder, found[1] if found else {})
    return ids


# ── deletion and citation invalidation ───────────────────────────────────────────────
def _cites(refs, doc_id: str) -> bool:
    return any(r.get("document_id") == doc_id for r in refs or [])


def scrub_document(c: Connection, owner: str, doc_id: str) -> None:
    """Make every derived output that cites or depends on doc_id inaccessible/stale."""
    for job in jobs(c, owner):
        result = job["body"].get("result") or {}
        text = str(result)
        historical = doc_id in text
        active = job["status"] in ("queued", "running")
        if historical or (active and (job["payload"].get("document_id") == doc_id or job["kind"] in
                                      ("answer", "match_need", "assess", "draft", "draft_follow_up", "analyze_reply"))):
            if job["status"] in ("succeeded",) and not historical:
                continue
            end_job(c, owner, job["id"], "stale" if historical or job["status"] == "succeeded" else "cancelled")
    for message, mp in objects(c, owner, "message"):
        if _cites(message["evidence_refs"], doc_id):
            message.update(content=DELETED_ANSWER, evidence_refs=[], matched_benefit_ids=[], next_actions=[], questions=[])
            put(c, owner, "message", message, mp, message["thread_id"])
    for thread, tp in objects(c, owner, "thread"):
        if doc_id in thread["document_ids"]:
            thread["document_ids"] = [d for d in thread["document_ids"] if d != doc_id]
            put(c, owner, "thread", thread, tp, thread["entry_id"] or thread["case_id"])
    for case, cp in objects(c, owner, "case"):
        changed = False
        if doc_id in case["document_ids"]:
            case["document_ids"] = [d for d in case["document_ids"] if d != doc_id]
            changed = True
        if case["assessment"] and _cites(case["assessment"]["evidence_refs"], doc_id):
            case["assessment"] = None
            changed = True
        if changed:
            touch_case(c, owner, case, cp, content=True)
    for draft, dp in objects(c, owner, "draft"):
        if _cites(draft["content"]["evidence_refs"], doc_id):
            draft["content"]["evidence_refs"] = [r for r in draft["content"]["evidence_refs"] if r["document_id"] != doc_id]
            draft["stale"] = True
            put(c, owner, "draft", draft, dp, draft["case_id"])
    for event, ep in objects(c, owner, "event"):
        changed = doc_id in event["attachment_document_ids"]
        event["attachment_document_ids"] = [d for d in event["attachment_document_ids"] if d != doc_id]
        analysis = event["reply_analysis"]
        if analysis and _cites(analysis["evidence_refs"], doc_id):
            analysis.update(evidence_refs=[r for r in analysis["evidence_refs"] if r["document_id"] != doc_id],
                            comparison="Unavailable because a supporting source was deleted.")
            changed = True
        if changed:
            put(c, owner, "event", event, ep, event["case_id"])
    for reminder, rp in objects(c, owner, "reminder"):
        if _cites(reminder["evidence_refs"], doc_id):
            reminder["evidence_refs"] = [r for r in reminder["evidence_refs"] if r["document_id"] != doc_id]
            put(c, owner, "reminder", reminder, rp, reminder["benefit_id"] or reminder["case_id"])
    for outcome, op in objects(c, owner, "outcome"):
        if _cites(outcome["evidence_refs"], doc_id):
            outcome["evidence_refs"] = [r for r in outcome["evidence_refs"] if r["document_id"] != doc_id]
            put(c, owner, "outcome", outcome, op, outcome["case_id"])


def touch_case(c: Connection, owner: str, case: dict, private: dict, *, content: bool = False) -> None:
    case["data_version"] += 1
    case["updated_at"] = now()
    if content:
        private["content_version"] = private.get("content_version", 1) + 1
        for draft, dp in objects(c, owner, "draft", case["id"]):
            if not draft["stale"]:
                draft["stale"] = True
                put(c, owner, "draft", draft, dp, case["id"])
    put(c, owner, "case", case, private)


def refresh_entry(c: Connection, owner: str, entry: dict, private: dict) -> None:
    docs = [(d, p) for d, p in objects(c, owner, "document", entry["id"])]
    entry["document_ids"] = [d["id"] for d, _ in docs]
    entry["benefit_ids"] = [b["id"] for b, _ in objects(c, owner, "benefit", entry["id"])]
    user = {k: v for k, v in entry["facts"].items() if v["origin"] == "user"}
    derived = {}
    for d, p in docs:
        if d["status"] in ("ready", "needs_review") and p.get("populated"):
            derived.update(d["facts"])
    entry["facts"] = {**derived, **user}
    private["admitted"] = any(p.get("populated") for _, p in docs)
    entry["data_version"] += 1
    entry["updated_at"] = now()
    put(c, owner, "entry", entry, private)


def delete_document(c: Connection, owner: str, doc: dict, private: dict, *, refresh: bool = True) -> str:
    """Delete DB state and tombstone the original in the same transaction; returns its storage path."""
    scrub_document(c, owner, doc["id"])
    removed = [b["id"] for b, bp in objects(c, owner, "benefit", doc["entry_id"]) if bp.get("document_id") == doc["id"]]
    cancel_reminders(c, owner, benefit_ids=removed)
    for bid in removed:
        remove(c, owner, bid)
        for case, cp in objects(c, owner, "case"):
            if case["benefit_id"] == bid:
                case["benefit_id"] = None
                touch_case(c, owner, case, cp, content=True)
    c.execute("DELETE FROM claimly.session_chunks WHERE session_id=? AND document_id=?", (owner, doc["id"]))
    tombstone(c, private["storage_path"])
    remove(c, owner, doc["id"])
    if refresh:
        found = find(c, owner, "entry", doc["entry_id"])
        if found:
            refresh_entry(c, owner, *found)
    return private["storage_path"]


def tombstone(c: Connection, path: str) -> None:
    c.execute("INSERT INTO claimly.storage_tombstones (storage_path, created_at) VALUES (?, ?) ON CONFLICT (storage_path) DO NOTHING",
              (path, time.time()))


def delete_entry(c: Connection, owner: str, entry: dict, private: dict) -> list[str]:
    paths = [delete_document(c, owner, d, p, refresh=False) for d, p in objects(c, owner, "document", entry["id"])]
    remaining = [b["id"] for b, _ in objects(c, owner, "benefit", entry["id"])]
    cancel_reminders(c, owner, benefit_ids=remaining)
    for bid in remaining:
        remove(c, owner, bid)
    for thread, _ in objects(c, owner, "thread"):
        if thread["scope"] == "entry" and thread["entry_id"] == entry["id"]:
            for message, _ in objects(c, owner, "message", thread["id"]):
                remove(c, owner, message["id"])
            remove(c, owner, thread["id"])
    for case, cp in objects(c, owner, "case"):
        if entry["id"] in case["entry_ids"] or case["benefit_id"] in remaining:
            case["entry_ids"] = [e for e in case["entry_ids"] if e != entry["id"]]
            if case["benefit_id"] in remaining:
                case["benefit_id"] = None
            touch_case(c, owner, case, cp, content=True)
    remove(c, owner, entry["id"])
    return paths
