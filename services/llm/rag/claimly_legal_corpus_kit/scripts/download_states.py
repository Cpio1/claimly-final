#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download state statutes listed in catalog/state_sources.csv.

IMPORTANT - read before running
  The catalog has partial official URLs and an existing preserved corpus. See ../README.txt.
  Fill and verify missing official addresses before downloading. Filtered runs must use a NEW
  --out directory: this script replaces the sections/chunks/report in its output directory.
  This script does the mechanical part once the addresses are there:

    1. reads every row whose `url` is filled (several addresses may be separated by " | ")
    2. downloads the page and extracts the readable text (no rewriting, no summarizing)
    3. checks the text against the row's `expect_terms` pattern - a page that does not even
       mention the subject is flagged instead of being trusted
    4. writes sections, retrieval chunks and a status report

Output : <out>/raw/<row_id>_<n>.html      pages as downloaded
         <out>/state_sections.jsonl       one record per downloaded page
         <out>/chunks.jsonl               retrieval chunks
         <out>/report.csv                 status of every catalog row
                                          (ok / no_url / no_citation / http_error / terms_not_found / too_short)

Usage  : python download_states.py --catalog ../catalog/state_sources.csv --out ../corpus/states
         python download_states.py --states CA,NY,TX --topics gift_cards,lemon_law
         python download_states.py --selftest

Standard library only. Some state sites are built with JavaScript or block scripts; those rows end
up as http_error or too_short and need a headless browser or a manual save.
"""
import argparse
import csv
import os
import re
import sys
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rag_common import clean_text, http_get, make_chunks, now_iso, sha256, write_jsonl

MIN_CHARS = 200

# Added 2026-11-15 (first live run). Where a site wraps the statute in menus, keep only the part of
# the page that holds the statute. (host substring, start regex, end regex). Nothing is rewritten:
# the text between the two markers is taken as is.
CONTENT_MARKERS = [
    ("leg.state.fl.us", r'<div id="statutes">', r'Copyright\s*(?:&copy;|\u00a9)\s*1995'),
    ("le.utah.gov", r'<div id="secdiv"', r'<div id="footer|<footer'),
    ("mgaleg.maryland.gov", r'<div id="StatuteText"', r"<footer"),
    ("scstatehouse.gov", r'<div id="contentsection"', r'<div id="footer|<footer'),
    ("codes.ohio.gov", r'<section class="laws-header', r"<footer"),
    ("legislature.mi.gov", r'<div class="sectionWrapper">', r"</main>"),
]


def cut_content(url, html):
    for host, start, end in CONTENT_MARKERS:
        if host in url:
            m = re.search(start, html)
            if not m:
                return html
            rest = html[m.start():]
            e = re.search(end, rest)
            return rest[:e.start()] if e else rest
    return html


class _TextExtractor(HTMLParser):
    SKIP = {"head", "title", "script", "style", "noscript", "nav", "header", "footer", "form", "svg", "button", "select"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
             "table", "ul", "ol", "blockquote", "pre", "td", "th", "dd", "dt"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.depth = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.depth:
            self.parts.append(data)


def html_to_text(html):
    p = _TextExtractor()
    p.feed(html)
    return clean_text("".join(p.parts))


def decode(raw):
    m = re.search(rb'charset=["\']?([A-Za-z0-9_\-]+)', raw[:4000])
    for enc in ([m.group(1).decode("ascii", "ignore")] if m else []) + ["utf-8", "cp1252"]:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def selftest():
    html = ("<html><head><title>t</title><style>x{}</style><script>var a=1;</script></head><body><nav>Menu</nav>"
            "<h1>501.95 Gift certificates and credit memos.</h1><p>(1) As used in this section, a "
            "&ldquo;gift certificate&rdquo; means a certificate.</p><div>(2) A gift certificate may not have "
            "an expiration date.</div><footer>Copyright</footer></body></html>")
    text = html_to_text(html)
    assert "Menu" not in text and "Copyright" not in text and "var a" not in text, text
    assert text.split("\n")[0] == "501.95 Gift certificates and credit memos.", text
    assert re.search(r"gift certificate|gift card", text, re.I)
    assert decode("caf\xe9".encode("cp1252")) == "caf\xe9"
    print("selftest OK: HTML text extraction, expect_terms check, charset fallback")
    print("NOTE: built-in sample only. No state website was contacted.")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default=os.path.join(here, "..", "catalog", "state_sources.csv"))
    ap.add_argument("--out", default=os.path.join(here, "..", "corpus", "states"))
    ap.add_argument("--states", default="", help="comma-separated postal codes, e.g. CA,NY (default: all)")
    ap.add_argument("--topics", default="", help="comma-separated topic ids (default: all)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="download again even if the raw page is already saved")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    states = {s.strip().upper() for s in args.states.split(",") if s.strip()}
    topics = {t.strip() for t in args.topics.split(",") if t.strip()}
    with open(args.catalog, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f)
                if (not states or r["state"] in states) and (not topics or r["topic"] in topics)]
    raw_dir = os.path.join(args.out, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    records, report = [], []
    for row in rows:
        urls = [u.strip() for u in row["url"].split("|") if u.strip()]
        if not row["citation"]:
            report.append([row["row_id"], "no_citation", 0, row["verification"], ""])
            continue
        if not urls:
            report.append([row["row_id"], "no_url", 0, row["verification"], row.get("download_note", "")])
            continue
        # Changed 2026-11-15: a row may list many pages (one per section of an act). The subject check
        # (expect_terms) is applied to the row as a whole: single sections such as "Short title" do not
        # repeat the subject words. Every page still records whether it matched on its own.
        pages = []
        for i, url in enumerate(urls, 1):
            raw_path = os.path.join(raw_dir, f"{row['row_id']}_{i}.html")
            url_path = raw_path + ".url"
            try:
                if (not args.refresh and os.path.exists(raw_path) and os.path.exists(url_path)
                        and open(url_path, encoding="utf-8").read() == url):
                    raw = open(raw_path, "rb").read()          # already downloaded from this address
                else:
                    raw = http_get(url)
                    with open(raw_path, "wb") as f:
                        f.write(raw)
                    with open(url_path, "w", encoding="utf-8") as f:
                        f.write(url)
            except Exception as e:
                report.append([row["row_id"], "http_error", 0, row["verification"], f"{url} ({e})"])
                continue
            text = html_to_text(cut_content(url, decode(raw)))
            if len(text) < (MIN_CHARS if len(urls) == 1 else 40):
                report.append([row["row_id"], "too_short", len(text), row["verification"], url])
                continue
            pages.append((i, url, text, bool(re.search(row["expect_terms"], text, re.I))))
        if not pages:
            continue
        if not any(p[3] for p in pages):
            for i, url, text, hit in pages:
                report.append([row["row_id"], "terms_not_found", len(text), row["verification"], url])
            continue                                  # do not put unconfirmed pages in the corpus
        for i, url, text, hit in pages:
            report.append([row["row_id"], "ok", len(text), row["verification"], url])
            first_line = text.split("\n")[0][:200]
            records.append({
                "id": f"{row['row_id'].lower()}-{i}", "catalog_id": row["row_id"], "jurisdiction": row["state"],
                "jurisdiction_name": row["state_name"], "level": "state", "kind": "statute_or_rule",
                "citation": row["citation"], "heading": first_line if len(urls) > 1 else (row["statute_name"] or first_line),
                "statute_name": row["statute_name"], "topic": row["topic"],
                "catalog_note": row["note"], "citation_verification": row["verification"],
                "page_matched_expect_terms": hit, "pages_in_row": len(urls),
                "source_url": url, "retrieved_at": now_iso(), "text_sha256": sha256(text), "text": text,
            })
    # Added 2026-11-15: sections prepared by a separate loader (California bulk file, see
    # download_ca_bulk.py) are merged here so that the corpus and the report stay in one place.
    extra_dir = os.path.join(args.out, "extra_sections")
    if os.path.isdir(extra_dir):
        import json
        done = {r[0] for r in report if r[1] == "ok"}
        for name in sorted(os.listdir(extra_dir)):
            if not name.endswith(".jsonl"):
                continue
            extra = [json.loads(l) for l in open(os.path.join(extra_dir, name), encoding="utf-8") if l.strip()]
            extra = [e for e in extra if (not states or e["jurisdiction"] in states) and (not topics or e["topic"] in topics)]
            per_row = {}
            for e in extra:
                per_row.setdefault(e["catalog_id"], []).append(e)
            for rid, items in per_row.items():
                report[:] = [r for r in report if not (r[0] == rid and r[1] == "no_url")]
                report.append([rid, "ok_bulk", sum(len(e["text"]) for e in items), "official",
                               f"{len(items)} section(s) from {items[0].get('download_url', name)}"])
            records.extend(extra)
    write_jsonl(os.path.join(args.out, "state_sections.jsonl"), records)
    write_jsonl(os.path.join(args.out, "chunks.jsonl"), [c for r in records for c in make_chunks(r)])
    with open(os.path.join(args.out, "report.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["row_id", "status", "chars", "citation_verification", "detail"])
        w.writerows(report)
    counts = {}
    for r in report:
        counts[r[1]] = counts.get(r[1], 0) + 1
    print("rows:", len(rows), "| pages in corpus:", len(records), "| status counts:", counts)


if __name__ == "__main__":
    main()
