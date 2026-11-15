"""Periodic cleanup run by the worker: session expiry, orphaned uploads, tombstoned originals,
unadmitted-upload quarantine and in-app reminder delivery. Never logs document content or tokens."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime

from app import lifecycle
from app.db import Database, objects
from app.settings import Settings

LOG = logging.getLogger("claimly.maintenance")
INTENT_GRACE_SECONDS = 15 * 60
BATCH = 50


class Maintenance:
    def __init__(self, settings: Settings, db: Database, storage_factory, *, interval: float = 60.0):
        self.settings, self.db, self.storage_factory, self.interval = settings, db, storage_factory, interval
        self.quarantine_hours = float(os.environ.get("QUARANTINE_HOURS", "72"))
        self._last = 0.0

    def tick(self, *, force: bool = False) -> dict:
        if not force and time.monotonic() - self._last < self.interval:
            return {}
        self._last = time.monotonic()
        try:
            return self.run()
        except Exception as error:  # noqa: BLE001 - availability failures retry on the next tick
            LOG.warning("maintenance_failed type=%s", type(error).__name__)
            return {}

    def run(self) -> dict:
        stamp = time.time()
        report = {"expired_sessions": 0, "intents": 0, "quarantined": 0, "purged": 0, "dispatched": 0}
        with self.db.tx(write=True) as c:
            c.lock("claimly-maintenance")
            for row in c.execute("SELECT id FROM claimly.demo_sessions WHERE expires_at < ? LIMIT ?", (stamp, BATCH)).fetchall():
                owner = row["id"]
                for _, private in objects(c, owner, "document"):
                    lifecycle.tombstone(c, private["storage_path"])
                for intent in c.execute("SELECT storage_path FROM claimly.session_requests WHERE session_id=? "
                                        "AND storage_path IS NOT NULL", (owner,)).fetchall():
                    lifecycle.tombstone(c, intent["storage_path"])
                c.execute("DELETE FROM claimly.demo_sessions WHERE id=?", (owner,))  # cascades all session rows
                report["expired_sessions"] += 1
            for intent in c.execute("SELECT session_id, route, key_hash, storage_path FROM claimly.session_requests "
                                    "WHERE state IN ('reserved','cleanup_required') AND created_at < ? LIMIT ?",
                                    (stamp - INTENT_GRACE_SECONDS, BATCH)).fetchall():
                # A reserved/cleanup intent never produced a document; its object (if any) is an orphan.
                if intent["storage_path"]:
                    lifecycle.tombstone(c, intent["storage_path"])
                c.execute("DELETE FROM claimly.session_requests WHERE session_id=? AND route=? AND key_hash=?",
                          (intent["session_id"], intent["route"], intent["key_hash"]))
                report["intents"] += 1
            cutoff = stamp - self.quarantine_hours * 3600
            for row in c.execute("SELECT session_id, body, private FROM claimly.session_objects WHERE kind='document'").fetchall():
                doc, private = json.loads(row["body"]), json.loads(row["private"])
                created = datetime.fromisoformat(doc["created_at"].replace("Z", "+00:00")).timestamp()
                if private.get("populated") or created >= cutoff:
                    continue
                # Never-admitted uploads (unreviewed, blocked or failed) do not stay in private storage indefinitely.
                lifecycle.delete_document(c, row["session_id"], doc, private)
                report["quarantined"] += 1
            for row in c.execute("SELECT id, session_id, body, private FROM claimly.session_objects WHERE kind='entry'").fetchall():
                entry, private = json.loads(row["body"]), json.loads(row["private"])
                created = datetime.fromisoformat(entry["created_at"].replace("Z", "+00:00")).timestamp()
                if not private.get("admitted") and not entry["document_ids"] and created < cutoff:
                    # The unpopulated draft created before an upload is not a Vault row.
                    lifecycle.delete_entry(c, row["session_id"], entry, private)
            c.execute("DELETE FROM claimly.request_limits WHERE window_start < ?", (int(stamp) - 7200,))
            report["dispatched"] = lifecycle.dispatch_due(c, None, self.settings)["sent"]
        report["purged"] = self.purge()
        if any(report.values()):
            LOG.info("maintenance %s", report)
        return report

    def purge(self) -> int:
        with self.db.tx() as c:
            paths = [r["storage_path"] for r in c.execute("SELECT storage_path FROM claimly.storage_tombstones "
                                                          "ORDER BY created_at LIMIT ?", (BATCH,)).fetchall()]
        if not paths:
            return 0
        storage, done = self.storage_factory(), 0
        for path in paths:
            try:
                storage.delete(path)
            except Exception:  # noqa: BLE001 - retried next tick; tombstone keeps the object tracked
                continue
            with self.db.tx(write=True) as c:
                c.execute("DELETE FROM claimly.storage_tombstones WHERE storage_path=?", (path,))
            done += 1
        return done
