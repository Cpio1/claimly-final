#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""California: take statute sections from the Legislative Counsel's official bulk file.

Why: leginfo.legislature.ca.gov answers scripts with a JavaScript challenge (HTTP 403), but the same
office publishes the full database for download at https://downloads.leginfo.legislature.ca.gov/
(pubinfo_2025.zip, table LAW_SECTION_TBL, one .lob file per section). This script reads only the
members it needs through HTTP Range requests. Text is extracted from the official XML as is.

Output: <out>/raw_ca/<member>.lob, <out>/extra_sections/CA.jsonl, <out>/extra_sections/CA_report.csv
Written 2026-11-15.
"""
import csv, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rag_common import now_iso, sha256
from download_states import html_to_text
import remote_zip

BULK = "https://downloads.leginfo.legislature.ca.gov/pubinfo_2025.zip"
CODE_NAMES = {"CIV": "Cal. Civ. Code", "BPC": "Cal. Bus. & Prof. Code", "INS": "Cal. Ins. Code",
              "COM": "Cal. Com. Code", "CCP": "Cal. Code Civ. Proc."}


def ipart(lo, hi):
    return lambda n: n.split(".")[0].isdigit() and lo <= int(n.split(".")[0]) <= hi


def rx(p):
    return lambda n: re.fullmatch(p, n) is not None


# row_id -> [(law code, section filter)]
PLAN = {
    "CA-udap": [("BPC", ipart(17200, 17594)), ("CIV", ipart(1750, 1784))],
    "CA-lemon_law": [("CIV", ipart(1790, 1795))],
    "CA-gift_cards": [("CIV", rx(r"1749\.(45|5|51|6)"))],
    "CA-auto_renewal": [("BPC", ipart(17600, 17606))],
    "CA-service_contracts": [("BPC", ipart(9855, 9855)), ("INS", ipart(12800, 12865)), ("INS", ipart(12140, 12311))],
    "CA-unfair_claims": [("INS", rx(r"790\.03"))],
    "CA-refund_policy": [("CIV", rx(r"1723"))],
    "CA-home_solicitation": [("CIV", rx(r"1689\.(5|6|7|8|9|1[0-4])"))],
    "CA-ucc_warranties": [("COM", rx(r"231[3-7]|2714|2715|2719|2725"))],
    "CA-small_claims": [("CCP", rx(r"116\.22[01]"))],
}


def sort_key(num):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", num)]


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "..", "corpus", "states")
    catalog = os.path.join(here, "..", "catalog", "state_sources.csv")
    with open(catalog, encoding="utf-8-sig", newline="") as f:
        cat = {r["row_id"]: r for r in csv.DictReader(f)}
    raw_dir = os.path.join(out, "raw_ca")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(os.path.join(out, "extra_sections"), exist_ok=True)
    z, f = remote_zip.open_remote_zip(BULK)
    table = z.read("LAW_SECTION_TBL.dat").decode("utf-8", "replace").split("\n")
    f.set_block(32 * 1024)
    wanted = []
    for line in table:
        c = [x.strip("`") for x in line.split("\t")]
        if len(c) < 17 or c[15] != "Y":                      # active sections only
            continue
        code, num = c[1], c[2].rstrip(".")
        for row_id, specs in PLAN.items():
            if any(code == sc and test(num) for sc, test in specs):
                wanted.append((row_id, code, num, c[6], c[13], c[14]))
    wanted.sort(key=lambda w: (w[0], w[1], sort_key(w[2])))
    records, report, counts = [], [], {}
    for row_id, code, num, eff, history, lob in wanted:
        raw_path = os.path.join(raw_dir, lob)
        if os.path.exists(raw_path):
            raw = open(raw_path, "rb").read()
        else:
            raw = z.read(lob)
            with open(raw_path, "wb") as fh:
                fh.write(raw)
        text = html_to_text(raw.decode("utf-8", "replace"))
        if not text:
            report.append([row_id, "empty", f"{code} {num}", lob])
            continue
        counts[row_id] = counts.get(row_id, 0) + 1
        row = cat[row_id]
        records.append({
            "id": f"ca-{code.lower()}-{num}-{counts[row_id]}-{row['topic']}", "catalog_id": row_id, "jurisdiction": "CA",
            "jurisdiction_name": "California", "level": "state", "kind": "statute",
            "citation": f"{CODE_NAMES[code]} § {num}", "heading": "", "statute_name": row["statute_name"],
            "catalog_citation": row["citation"], "topic": row["topic"], "catalog_note": row["note"],
            "citation_verification": "official", "history": history, "effective_date": eff if eff != "NULL" else "",
            "source_url": f"https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode={code}&sectionNum={num}.",
            "download_url": BULK, "bulk_member": lob, "retrieved_at": now_iso(), "text_sha256": sha256(text), "text": text,
        })
        report.append([row_id, "ok", f"{code} {num}", lob])
    with open(os.path.join(out, "extra_sections", "CA.jsonl"), "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(out, "extra_sections", "CA_report.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh); w.writerow(["row_id", "status", "section", "bulk_member"]); w.writerows(report)
    print("CA sections:", len(records), "| per row:", counts, "| MB fetched:", round(f.bytes_fetched / 1e6, 1))


if __name__ == "__main__":
    main()
