"""Trusted operator source-quality review (SOURCE_REVIEW_MODE=operator). No browser admin token.

  python -m app.review --list
  python -m app.review DOCUMENT_ID --session-id SESSION_ID            # show hashes + canonical pages
  python -m app.review DOCUMENT_ID --session-id SESSION_ID --approve --source-sha ... --pages-sha ...

Approval binds to the exact original bytes and canonical pages; a semantically blocked conversion
(quality:blocked: unreadable/uncertain relevance) cannot be overridden here. Field and benefit review
remains the user's job in the product review UI.
"""

from __future__ import annotations

import argparse
import hashlib
import json

from app.db import Database, get, new_job, now, put
from app.errors import ApiError
from app.settings import Settings
from app.storage import make_storage
from services.llm.rag.runtime import page_hash


def approve(db: Database, storage, owner: str, document_id: str, source_sha: str, pages_sha: str) -> dict:
    data = None
    with db.tx() as c:
        _, private = get(c, owner, "document", document_id)
    data = storage.download(private["storage_path"])
    with db.tx(write=True) as c:
        doc, private = get(c, owner, "document", document_id)
        output = private.get("extraction")
        if output is None or "quality:blocked" in output["review_flags"]:
            raise ApiError(422, "VALIDATION_ERROR", "This conversion is incomplete or semantically unresolved; review cannot override its gate.")
        if (source_sha != private["source_sha256"] or hashlib.sha256(data).hexdigest() != source_sha
                or page_hash(output["pages"]) != pages_sha):
            raise ApiError(409, "STALE_INPUT", "Review hashes do not match the current original and canonical pages.")
        private["quality_review"] = {"mode": "operator", "source_sha256": source_sha, "pages_sha256": pages_sha, "approved_at": now()}
        doc["status"] = "processing"
        doc["review_flags"] = [f for f in doc["review_flags"] if f != "quality:operator_review_pending"]
        put(c, owner, "document", doc, private, doc["entry_id"])
        return new_job(c, owner, "extract", document_id, {"document_id": document_id, "version": doc["version"]})


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("document_id", nargs="?")
    p.add_argument("--session-id")
    p.add_argument("--list", action="store_true")
    p.add_argument("--approve", action="store_true")
    p.add_argument("--source-sha")
    p.add_argument("--pages-sha")
    args = p.parse_args(argv)
    settings = Settings.from_env()
    db = Database(settings)
    if args.list:
        with db.tx() as c:
            for row in c.execute("SELECT id, session_id, body FROM claimly.session_objects WHERE kind='document'").fetchall():
                body = json.loads(row["body"])
                if body["status"] == "needs_review":
                    print(json.dumps({"document_id": row["id"], "session_id": row["session_id"], "status": body["status"],
                                      "review_flags": body["review_flags"]}))
        return 0
    if not args.document_id or not args.session_id:
        p.error("Specify document_id and --session-id, or use --list.")
    if args.approve:
        if not args.source_sha or not args.pages_sha:
            p.error("Approval requires both hashes after comparing the original with the canonical pages.")
        job = approve(db, make_storage(settings), args.session_id, args.document_id, args.source_sha, args.pages_sha)
        print("Approved exact source/conversion; indexing job:", job["id"])
        return 0
    with db.tx() as c:
        doc, private = get(c, args.session_id, "document", args.document_id)
    print(json.dumps({"document": doc, "source_sha256": private["source_sha256"], "pages_sha256": private.get("pages_sha256"),
                      "pages": (private.get("extraction") or {}).get("pages")}, ensure_ascii=False, indent=2))
    print("Compare the canonical pages with the original before approving these hashes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
