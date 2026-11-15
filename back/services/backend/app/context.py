"""Authorized LlmContext assembly. Ownership, scope, admission, version and embedding profile are
filtered BEFORE lexical/dense ranking; the model receives selected page TEXT, never vectors."""

from __future__ import annotations

import json

from app import lifecycle
from app.db import Connection, find, objects, now
from services.llm.rag.runtime import hybrid

HISTORY_LIMIT = 12
SMALL_CORPUS_PAGES = 6


def indexed_documents(c: Connection, owner: str, profile: str, *, entry_id=None, document_ids=None):
    """Admitted, indexed documents of this session (optionally restricted). Returns (current, stale_profile)."""
    current, stale = [], []
    for doc, private in objects(c, owner, "document"):
        if not private.get("populated") or not private.get("extraction"):
            continue
        if entry_id and doc["entry_id"] != entry_id:
            continue
        if document_ids is not None and doc["id"] not in document_ids:
            continue
        (current if private.get("embedding_profile") == profile else stale).append((doc, private))
    return current, stale


def candidate_rows(c: Connection, owner: str, docs, profile: str):
    allowed = {d["id"]: d for d, _ in docs}
    rows = []
    if not allowed:
        return rows
    for row in c.execute("SELECT document_id, document_version, chunk, vector FROM claimly.session_chunks "
                         "WHERE session_id=? AND profile=?", (owner, profile)).fetchall():
        doc = allowed.get(row["document_id"])
        if doc and row["document_version"] == doc["version"]:
            rows.append({"chunk": json.loads(row["chunk"]), "vector": json.loads(row["vector"])})
    return rows


def select_pages(question: str, rows, query_vector, docs, *, k: int = 3, include_all_small: bool = False):
    """Selected canonical pages per document, with neighbour context from hybrid()."""
    total_pages = sum(len(p["extraction"]["pages"]) for _, p in docs)
    if include_all_small and total_pages <= SMALL_CORPUS_PAGES:
        chosen = {(d["id"], d["version"], page["page"]) for d, p in docs for page in p["extraction"]["pages"]}
    else:
        selected = hybrid(question, rows, query_vector, k=k) if rows else []
        chosen = {(x["document_id"], x["document_version"], x["page"]) for x in selected}
    return [{"document_id": d["id"], "document_version": d["version"], "name": d["name"],
             "pages": [page for page in p["extraction"]["pages"] if (d["id"], d["version"], page["page"]) in chosen]}
            for d, p in docs if any(key[0] == d["id"] for key in chosen)]


def related(c: Connection, owner: str, docs, *, extra_entry_ids=()):
    entry_ids = {d["entry_id"] for d, _ in docs} | set(extra_entry_ids)
    entries = [e for e, p in objects(c, owner, "entry") if e["id"] in entry_ids and p.get("admitted")]
    admitted = {e["id"] for e in entries}
    benefits = [b for b, _ in objects(c, owner, "benefit") if b["entry_id"] in admitted]
    return entries, benefits


def history(c: Connection, owner: str, thread_id: str, before: str):
    items = [m for m, _ in objects(c, owner, "message", thread_id) if m["created_at"] < before]
    items.sort(key=lambda m: (m["created_at"], m["id"]))
    return [{"role": m["role"], "content": m["content"]} for m in items[-HISTORY_LIMIT:]]


def base_context(c: Connection, owner: str, settings, *, entries, benefits, documents, hist, case):
    prof = lifecycle.profile(c, owner, settings)
    return {"as_of": now(), "timezone": prof["timezone"], "entries": entries, "benefits": benefits,
            "documents": documents, "history": hist, "case": case}


def case_scope(c: Connection, owner: str, case: dict):
    """Only explicitly linked documents: case.document_ids plus the linked benefit's source document."""
    ids = set(case["document_ids"])
    if case["benefit_id"]:
        found = find(c, owner, "benefit", case["benefit_id"])
        if found and found[1].get("document_id"):
            ids.add(found[1]["document_id"])
    return ids
