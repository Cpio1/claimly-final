#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download the federal layer of the Claimly legal corpus, word for word, from official sources.

  Regulations : eCFR API (ecfr.gov), XML per part / subpart / section, no API key needed
  Statutes    : U.S. Code release point (uscode.house.gov), USLM XML per title

Input  : catalog/federal_sources.csv
Output : <out>/raw/...                 untouched files as downloaded
         <out>/cfr_sections.jsonl      one record per CFR section or appendix
         <out>/usc_sections.jsonl      one record per U.S. Code section
         <out>/chunks.jsonl            retrieval chunks (sections split when long)
         <out>/report.json             what was found for every catalog row, with warnings

Usage  : python download_federal.py --catalog ../catalog/federal_sources.csv --out ../corpus/federal
         python download_federal.py --selftest        (parser check on built-in miniature samples)

Standard library only. Nothing here rewrites the legal text: it is extracted from the XML as is.
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rag_common import clean_text, http_get, make_chunks, now_iso, sha256, write_jsonl

ECFR = "https://www.ecfr.gov"
USC_DOWNLOAD_PAGE = "https://uscode.house.gov/download.html"   # changed 2026-11-15: old /download/download.shtml returns 404 after the site redesign
USLM_NS = "{http://xml.house.gov/schemas/uslm/1.0}"


# ----------------------------------------------------------------------------- eCFR
def ecfr_title_dates():
    """Return {title number: date string} = the newest date each title is complete for."""
    data = json.loads(http_get(ECFR + "/api/versioner/v1/titles.json"))
    dates = {}
    for t in data.get("titles", []):
        d = t.get("up_to_date_as_of") or t.get("latest_issue_date")
        if d and not t.get("reserved"):
            dates[int(t["number"])] = d
    return dates


def ecfr_api_url(date, title, part, subpart="", section=""):
    q = {"part": part}
    if subpart:
        q["subpart"] = subpart
    if section:
        q["section"] = section
    return f"{ECFR}/api/versioner/v1/full/{date}/title-{title}.xml?" + urllib.parse.urlencode(q)


def _element_text(el):
    return "".join(el.itertext())


def parse_ecfr_xml(xml_bytes, title, part):
    """Yield (number, heading, text, kind) for every section (DIV8) and appendix (DIV9)."""
    root = ET.fromstring(xml_bytes)
    part_heading = ""
    for el in root.iter("DIV5"):
        head = el.find("HEAD")
        if head is not None:
            part_heading = clean_text(_element_text(head))
        break
    out = []
    for el in root.iter():
        if el.tag not in ("DIV8", "DIV9"):
            continue
        head = el.find("HEAD")
        heading = clean_text(_element_text(head)) if head is not None else ""
        paras = []
        for child in el:
            if child.tag == "HEAD":
                continue
            t = clean_text(_element_text(child))
            if t:
                paras.append(t)
        number = (el.get("N") or "").replace("§", "").strip()
        kind = "section" if el.tag == "DIV8" else "appendix"
        out.append((number, heading, "\n".join(paras), kind))
    return part_heading, out


def run_ecfr(rows, out_dir, report):
    raw_dir = os.path.join(out_dir, "raw", "ecfr")
    os.makedirs(raw_dir, exist_ok=True)
    dates = ecfr_title_dates()
    records = []
    for row in rows:
        title, part = int(row["title"]), row["part"]
        date = dates.get(title)
        entry = {"id": row["id"], "citation": row["citation"], "sections_found": 0, "warnings": []}
        report.append(entry)
        if not date:
            entry["warnings"].append(f"no date for title {title} in titles.json")
            continue
        wanted = [s for s in row["sections"].split(";") if s] or [""]
        for sec in wanted:
            url = ecfr_api_url(date, title, part, row["subpart"], sec)
            try:
                xml_bytes = http_get(url)
            except Exception as e:                       # keep going; the report shows the gap
                entry["warnings"].append(f"download failed: {url} ({e})")
                continue
            name = f"title-{title}_part-{part}" + (f"_subpart-{row['subpart']}" if row["subpart"] else "") + (f"_sec-{sec}" if sec else "") + f"_{date}.xml"
            with open(os.path.join(raw_dir, name), "wb") as f:
                f.write(xml_bytes)
            try:
                part_heading, sections = parse_ecfr_xml(xml_bytes, title, part)
            except ET.ParseError as e:
                entry["warnings"].append(f"XML parse error for {url}: {e}")
                continue
            for number, heading, text, kind in sections:
                if not text:
                    continue                             # reserved or empty section
                if kind == "appendix" and re.fullmatch(r"\[[^\]]*\]", text.strip()):
                    # changed 2026-11-15: image-only figure (e.g. Buyers Guide forms in 16 CFR 455);
                    # the XML holds only the Federal Register citation, so there is no text to quote
                    entry.setdefault("notes", []).append(f"skipped image-only item: {number}")
                    continue
                if kind == "section":
                    citation = f"{title} CFR {number}"
                    human = f"{ECFR}/current/title-{title}/section-{number}"
                else:
                    citation = f"{title} CFR Part {part}, {number}"
                    human = f"{ECFR}/current/title-{title}/part-{part}"
                rec_id = "us-cfr-" + re.sub(r"[^a-z0-9.]+", "-", f"{title}-{number}".lower()).strip("-")
                records.append({
                    "id": rec_id, "catalog_id": row["id"], "jurisdiction": "US", "level": "federal",
                    "kind": "regulation", "citation": citation, "heading": heading,
                    "part_heading": part_heading or row["name"], "topic": row["topic"],
                    "priority": int(row["priority"]), "status_note": row["status_note"],
                    "source": "eCFR", "source_url": human, "api_url": url, "version_date": date,
                    "retrieved_at": now_iso(), "text_sha256": sha256(text), "text": text,
                })
                entry["sections_found"] += 1
        if entry["sections_found"] == 0:
            entry["warnings"].append("no sections extracted - check part / subpart / section numbers")
    return records


# ----------------------------------------------------------------------------- U.S. Code
def norm_sec(s):
    return s.replace("–", "-").replace("—", "-").replace("‑", "-").strip().lower()


def parse_section_spec(spec):
    """'2301..2312;45;45b' -> [('2301','2312'), ('45','45'), ('45b','45b')]"""
    out = []
    for item in spec.split(";"):
        item = item.strip()
        if not item:
            continue
        a, _, b = item.partition("..")
        out.append((norm_sec(a), norm_sec(b or a)))
    return out


def usc_release_links():
    """Read the official download page and return {title: (zip url, release point)} for XML files."""
    html = http_get(USC_DOWNLOAD_PAGE).decode("utf-8", "replace")
    links = {}
    for m in re.finditer(r'href="([^"]*xml_usc(\d+)[aA]?@([^"/]+?)\.zip)"', html):
        href, num, rp = m.groups()
        if re.search(r"xml_usc\d+[aA]@", href):          # appendix files are not needed
            continue
        links[int(num)] = (urllib.parse.urljoin(USC_DOWNLOAD_PAGE, href), rp)
    return links


_BLOCK = {"subsection", "paragraph", "subparagraph", "clause", "subclause", "item", "subitem",
          "subsubitem", "chapeau", "continuation", "p", "content", "quotedContent", "table", "tr"}
_SKIP = {"notes", "note", "sourceCredit"}


def uslm_body_text(section):
    """Statutory text of a USLM <section>, without its number, heading, source credit and notes."""
    out = []

    def walk(e):
        tag = e.tag.split("}")[-1]
        if tag in _SKIP:
            return
        if tag in _BLOCK:
            out.append("\n")
        if e.text:
            out.append(e.text)
        if tag == "num":
            out.append(" ")
        for c in e:
            walk(c)
            if c.tail:
                out.append(c.tail)
        if tag in _BLOCK:
            out.append("\n")

    for child in section:
        tag = child.tag.split("}")[-1]
        if tag in ("num", "heading"):
            continue
        walk(child)
        if child.tail:
            out.append(child.tail)
    text = clean_text("".join(out))
    # changed 2026-11-15: in live USLM files <num> and <content> are sibling blocks, which left the
    # designator "(1)" alone on its own line. Join it with the line that follows. Words are untouched.
    text = re.sub(r"(?m)^((?:\([0-9A-Za-z]+\))+)\n+(?=\S)", r"\1 ", text)
    return text


def iter_usc_sections(xml_file, title):
    """Stream a title XML and yield (number, heading, text, status) for each codified section."""
    pat = re.compile(rf"^/us/usc/t{title}/s([^/]+)$")
    for _, el in ET.iterparse(xml_file, events=("end",)):
        if el.tag != USLM_NS + "section":
            continue
        m = pat.match(el.get("identifier", ""))
        if not m:
            continue
        num_el, head_el = el.find(USLM_NS + "num"), el.find(USLM_NS + "heading")
        number = (num_el.get("value") if num_el is not None and num_el.get("value") else m.group(1))
        heading = clean_text("".join(head_el.itertext())) if head_el is not None else ""
        credit_el = el.find(USLM_NS + "sourceCredit")
        credit = clean_text("".join(credit_el.itertext())) if credit_el is not None else ""
        yield number, heading, uslm_body_text(el), el.get("status", ""), credit
        el.clear()


def select_sections(sections, specs):
    """Keep sections named in specs. A range 'a..b' means everything from a to b in document order."""
    active = [False] * len(specs)
    hits = [0] * len(specs)
    for sec in sections:
        n = norm_sec(sec[0])
        keep = False
        for i, (a, b) in enumerate(specs):
            if n == a:
                active[i] = True
            if active[i]:
                keep = True
                hits[i] += 1
            if n == b:
                active[i] = False
        if keep:
            yield sec
    select_sections.last_hits = hits


def run_usc(rows, out_dir, report):
    raw_dir = os.path.join(out_dir, "raw", "uscode")
    os.makedirs(raw_dir, exist_ok=True)
    links = usc_release_links()
    by_title = {}
    for row in rows:
        by_title.setdefault(int(row["title"]), []).append(row)
    records = []
    for title, trows in sorted(by_title.items()):
        entries = {r["id"]: {"id": r["id"], "citation": r["citation"], "sections_found": 0, "warnings": []} for r in trows}
        report.extend(entries.values())
        if title not in links:
            for e in entries.values():
                e["warnings"].append(f"no XML link for title {title} on {USC_DOWNLOAD_PAGE}")
            continue
        url, release = links[title]
        try:
            blob = http_get(url, timeout=600)
        except Exception as e:
            for en in entries.values():
                en["warnings"].append(f"download failed: {url} ({e})")
            continue
        with open(os.path.join(raw_dir, os.path.basename(urllib.parse.urlparse(url).path)), "wb") as f:
            f.write(blob)
        zf = zipfile.ZipFile(io.BytesIO(blob))
        xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if not xml_names:
            for en in entries.values():
                en["warnings"].append(f"no XML inside {url}")
            continue
        for row in trows:                                 # one streaming pass per catalog row
            specs = parse_section_spec(row["sections"])
            with zf.open(xml_names[0]) as xf:
                for number, heading, text, status, credit in select_sections(iter_usc_sections(xf, title), specs):
                    n = norm_sec(number)
                    citation = f"{title} U.S.C. § {number}"
                    rec_id = "us-usc-" + re.sub(r"[^a-z0-9]+", "-", f"{title}-{n}").strip("-")
                    records.append({
                        "id": rec_id, "catalog_id": row["id"], "jurisdiction": "US", "level": "federal",
                        "kind": "statute", "citation": citation, "heading": heading,
                        "act_name": row["name"], "topic": row["topic"], "priority": int(row["priority"]),
                        "status": status, "status_note": row["status_note"], "source_credit": credit,
                        "source": "U.S. Code (Office of the Law Revision Counsel)",
                        "source_url": f"https://uscode.house.gov/us/usc/t{title}/s{n}/",   # changed 2026-11-15: view.xhtml?req=granuleid links return 404
                        "download_url": url, "release_point": release, "retrieved_at": now_iso(),
                        "text_sha256": sha256(text), "text": text,
                    })
                    entries[row["id"]]["sections_found"] += 1
            for (a, b), h in zip(specs, getattr(select_sections, "last_hits", [])):
                if h == 0:
                    entries[row["id"]]["warnings"].append(f"nothing matched '{a}'..'{b}' in title {title}")
    return records


# ----------------------------------------------------------------------------- self-test
_ECFR_SAMPLE = b"""<?xml version="1.0"?>
<DIV5 N="999" TYPE="PART"><HEAD>PART 999-SAMPLE PART</HEAD><AUTH><HED>Authority:</HED><PSPACE>x</PSPACE></AUTH>
<DIV8 N="\xc2\xa7 999.1" TYPE="SECTION"><HEAD>\xc2\xa7 999.1 Scope.</HEAD><P>(a) First paragraph.</P><P>(b) Second <I>italic</I> paragraph.</P><CITA>[1 FR 1, Jan. 1, 2000]</CITA></DIV8>
<DIV8 N="\xc2\xa7 999.2" TYPE="SECTION"><HEAD>\xc2\xa7 999.2 [Reserved]</HEAD></DIV8>
<DIV9 N="Appendix A to Part 999" TYPE="APPENDIX"><HEAD>Appendix A to Part 999-Forms</HEAD><P>Form text.</P></DIV9></DIV5>"""

_USLM_SAMPLE = ("""<?xml version="1.0" encoding="UTF-8"?>
<uscDoc xmlns="http://xml.house.gov/schemas/uslm/1.0"><main><title identifier="/us/usc/t15"><chapter identifier="/us/usc/t15/ch50">
<section identifier="/us/usc/t15/s2300"><num value="2300">§ 2300.</num><heading>Before range</heading><content><p>skip me</p></content></section>
<section identifier="/us/usc/t15/s2301"><num value="2301">§ 2301.</num><heading>Definitions</heading><chapeau>For the purposes of this chapter:</chapeau>
<paragraph identifier="/us/usc/t15/s2301/1"><num value="1">(1)</num><content>The term "consumer product" means tangible personal property.</content></paragraph>
<sourceCredit>(Pub. L. 93-637, title I, § 101, Jan. 4, 1975, 88 Stat. 2183.)</sourceCredit>
<notes><note><heading>Short Title</heading><p>NOTE TEXT MUST NOT APPEAR</p></note></notes></section>
<section identifier="/us/usc/t15/s2302"><num value="2302">§ 2302.</num><heading>Rules governing contents of warranties</heading><subsection identifier="/us/usc/t15/s2302/a"><num value="a">(a)</num><heading>Full and conspicuous disclosure</heading><content>Warrantor shall disclose terms.</content></subsection></section>
<section identifier="/us/usc/t15/s2303"><num value="2303">§ 2303.</num><heading>After range</heading><content><p>skip me too</p></content></section>
<section identifier="/us/usc/t15/s1693l–1"><num value="1693l–1">§ 1693l–1.</num><heading>General-use prepaid cards, gift certificates, and store gift cards</heading><content>Dash test.</content></section>
</chapter></title></main></uscDoc>""").encode("utf-8")


def selftest():
    part_heading, secs = parse_ecfr_xml(_ECFR_SAMPLE, 16, "999")
    assert part_heading.startswith("PART 999"), part_heading
    assert [s[0] for s in secs] == ["999.1", "999.2", "Appendix A to Part 999"], secs
    assert secs[0][2] == "(a) First paragraph.\n(b) Second italic paragraph.\n[1 FR 1, Jan. 1, 2000]", secs[0][2]
    assert secs[1][2] == "" and secs[2][3] == "appendix"
    got = list(select_sections(iter_usc_sections(io.BytesIO(_USLM_SAMPLE), 15), parse_section_spec("2301..2302;1693l-1")))
    assert [g[0] for g in got] == ["2301", "2302", "1693l–1"], [g[0] for g in got]
    assert "consumer product" in got[0][2] and "NOTE TEXT" not in got[0][2] and "Pub. L." not in got[0][2], got[0][2]
    assert got[0][4].startswith("(Pub. L. 93-637"), got[0][4]
    assert got[1][2].startswith("(a) Full and conspicuous disclosure"), got[1][2]
    assert select_sections.last_hits == [2, 1]
    assert ecfr_api_url("2026-11-01", 12, "1026", "", "1026.13").endswith("title-12.xml?part=1026&section=1026.13")
    rec = {"id": "x", "citation": "16 CFR 999.1", "heading": "Scope.", "text": "para one.\n" + ("word " * 2000)}
    chunks = make_chunks(rec, 3000)
    assert len(chunks) > 1 and all(c["text"].startswith("16 CFR 999.1 - Scope.") for c in chunks)
    assert all(len(c["text"]) <= 3000 + 40 for c in chunks)
    print("selftest OK: eCFR parser, U.S. Code parser, section ranges, chunking")
    print("NOTE: this checks parsing logic on built-in miniature samples only. It does not contact ecfr.gov or uscode.house.gov.")


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "catalog", "federal_sources.csv"))
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "corpus", "federal"))
    ap.add_argument("--only", choices=["ecfr", "uscode"], help="download just one of the two sources")
    ap.add_argument("--max-priority", type=int, default=3, help="1 = core only, 2 = core + important, 3 = everything")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    with open(args.catalog, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if int(r["priority"]) <= args.max_priority]
    os.makedirs(args.out, exist_ok=True)
    report, cfr, usc = [], [], []
    if args.only in (None, "ecfr"):
        cfr = run_ecfr([r for r in rows if r["source_system"] == "ecfr"], args.out, report)
        write_jsonl(os.path.join(args.out, "cfr_sections.jsonl"), cfr)
    if args.only in (None, "uscode"):
        usc = run_usc([r for r in rows if r["source_system"] == "uscode"], args.out, report)
        write_jsonl(os.path.join(args.out, "usc_sections.jsonl"), usc)
    chunks = [c for rec in cfr + usc for c in make_chunks(rec)]
    write_jsonl(os.path.join(args.out, "chunks.jsonl"), chunks)
    problems = [e for e in report if e["warnings"]]
    with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8") as f:
        json.dump({"generated_at": now_iso(), "cfr_sections": len(cfr), "usc_sections": len(usc),
                   "chunks": len(chunks), "rows_with_warnings": len(problems), "rows": report}, f, indent=2, ensure_ascii=False)
    print(f"CFR sections: {len(cfr)} | U.S. Code sections: {len(usc)} | chunks: {len(chunks)} | catalog rows with warnings: {len(problems)}")
    for e in problems:
        print("  WARNING", e["id"], e["citation"], "->", "; ".join(e["warnings"]))


if __name__ == "__main__":
    main()
