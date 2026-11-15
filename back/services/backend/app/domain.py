"""Deterministic Backend-owned rules: usage, deadlines, reminders/deliveries, dashboard.

Model output never sets usage, final deadlines, case states or refunds; these functions do.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time as dtime, timedelta, timezone
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

OFFSETS = (30, 14, 7, 1, 0)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def valid_timezone(name) -> bool:
    if not isinstance(name, str) or not name or len(name) > 64:
        return False
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def valid_date(value) -> bool:
    try:
        return isinstance(value, str) and len(value) == 10 and date.fromisoformat(value) is not None
    except ValueError:
        return False


def default_profile(email_configured: bool) -> dict:
    return {"timezone": "America/New_York", "email_notification_opt_in": False, "email_configured": email_configured,
            "reminder_offsets": [7, 1, 0], "local_notification_time": "09:00", "notification_email": None}


# ── usage ────────────────────────────────────────────────────────────────────────────
def apply_usage(benefit: dict, used: int) -> None:
    """Absolute used count (not an increment); repeated identical calls are idempotent."""
    benefit["used_units"] = used
    total = benefit["units_total"]
    if total is not None:
        benefit["remaining_units"] = max(0, total - used)
        benefit["usage_state"] = "unused" if used == 0 else "used" if used >= total else "partial"
    else:
        benefit["remaining_units"] = None
        benefit["usage_state"] = "unused" if used == 0 else "partial"
    benefit["data_version"] += 1


# ── deadlines ────────────────────────────────────────────────────────────────────────
def add_months(start: date, months: int) -> date:
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def rule_date(rule: dict | None, facts: dict) -> str | None:
    """Explicit dates and unambiguous calendar intervals only; business days need a calendar."""
    if not rule:
        return None
    if rule["kind"] == "absolute":
        return rule["date"] if valid_date(rule["date"]) else None
    if rule["kind"] != "relative" or not rule["anchor_field"] or not rule["duration_value"]:
        return None
    anchor = facts.get(rule["anchor_field"]) or {}
    if anchor.get("needs_review") or not valid_date(anchor.get("value")):
        return None
    start = date.fromisoformat(anchor["value"])
    if rule["duration_unit"] == "calendar_days":
        return (start + timedelta(days=rule["duration_value"])).isoformat()
    if rule["duration_unit"] == "calendar_months":
        return add_months(start, rule["duration_value"]).isoformat()
    return None


def initial_deadline(candidate: dict, facts: dict) -> tuple[str | None, str, str | None, bool]:
    """Returns (deadline_date, deadline_status, reminder_date, reminder_confirmed)."""
    rule = candidate["deadline_rule"]
    if not rule:
        return None, "not_known", None, False
    computed = rule_date(rule, facts)
    confirmed = (rule["kind"] == "absolute" and computed is not None and rule["last_day_inclusion"] != "unknown"
                 and not candidate["needs_review"])
    if confirmed:
        return computed, "document_confirmed", computed, True
    return None, "needs_review", computed, False


def deadline_status_after_patch(benefit: dict, origin: str | None) -> str:
    if benefit["deadline_date"] is None:
        return "needs_review" if benefit["deadline_rule"] else "not_known"
    return "document_confirmed" if origin == "document" else "user_set"


# ── reminders and deliveries ─────────────────────────────────────────────────────────
def scheduled_utc(day: str, local_time: str, tz: str) -> str:
    hour, minute = (int(x) for x in local_time.split(":"))
    local = datetime.combine(date.fromisoformat(day), dtime(hour, minute), tzinfo=ZoneInfo(tz))
    return local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def delivery_id(reminder_id: str, revision: int, offset: int, channel: str) -> str:
    """Unique delivery key: reminder + revision + interval + channel."""
    return str(uuid5(UUID(reminder_id), f"{revision}:{offset}:{channel}"))


def planned_notifications(reminder: dict, revision: int) -> list[dict]:
    if reminder["status"] != "active":
        return []
    out = []
    for offset in sorted(set(reminder["offset_days"]), reverse=True):
        day = (date.fromisoformat(reminder["date"]) - timedelta(days=offset)).isoformat()
        for channel in sorted(set(reminder["channels"])):
            body = (f"Today: {reminder['title']}" if offset == 0
                    else f"{reminder['title']} — in {offset} day{'s' if offset != 1 else ''} ({reminder['date']}).")
            out.append({"id": delivery_id(reminder["id"], revision, offset, channel), "reminder_id": reminder["id"],
                        "title": reminder["title"], "body": body, "channel": channel, "status": "pending",
                        "scheduled_at": scheduled_utc(day, reminder["local_time"], reminder["timezone"]),
                        "sent_at": None, "read_at": None})
    return out


# ── dashboard ────────────────────────────────────────────────────────────────────────
def _key(value):
    return (value is None, value or "")


def dashboard(benefits: list[dict], cases: list[dict], outcomes: list[dict], reminders: list[dict], today: str) -> dict:
    available = [b for b in benefits if b["usage_state"] == "unused"
                 or (b["usage_state"] == "partial" and (b["remaining_units"] is None or b["remaining_units"] > 0))]
    by_case = {o["case_id"]: o for o in outcomes}
    return {
        "available_benefits_count": len(available),
        "usage_unknown_count": sum(1 for b in benefits if b["usage_state"] == "unknown"),
        "document_valued_benefits_cents": sum(b["stated_value_cents"] for b in benefits
                                              if b["usage_state"] != "used" and b["stated_value_cents"] is not None),
        "approved_not_received_cents": sum(c["approved_amount_cents"] or 0 for c in cases if c["status"] == "approved"
                                           and (by_case.get(c["id"]) or {}).get("kind") != "cash_refund"),
        "cash_recovered_cents": sum(o["cash_amount_cents"] or 0 for o in outcomes if o["kind"] == "cash_refund"),
        # Confirmed usage counted once from benefits; linked outcomes are not summed again.
        "services_used_units": sum(b["used_units"] or 0 for b in benefits),
        "currency": "USD",
        "next_benefits": sorted([b for b in benefits if b["usage_state"] != "used"],
                                key=lambda b: (_key(b["deadline_date"]), b["id"]))[:4],
        "upcoming_reminders": sorted([r for r in reminders if r["status"] not in ("cancelled", "done") and r["date"] >= today],
                                     key=lambda r: (r["date"], r["id"]))[:5],
        "active_cases": sorted([c for c in cases if c["status"] != "resolved"],
                               key=lambda c: (c["updated_at"], c["id"]), reverse=True)[:5],
    }
