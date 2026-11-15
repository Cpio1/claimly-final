#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fill the `url` column of catalog/state_sources.csv for states whose official sites serve plain HTML.

Written 2026-11-15 during the first live run. Section lists are NOT typed in by hand: for a range of
sections the script reads the official table of contents (chapter / act / directory listing) and
keeps the links that fall inside the range. Fixed single addresses are listed in PLAN below.

Covered: FL, OH, NC, MI, TX, IL, PA.  Not covered here: CA (see download_ca_bulk.py), NY, GA.
Usage: python build_state_urls.py            (rewrites the catalog in place)
"""
import csv, os, re, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rag_common import http_get

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(HERE, "..", "catalog", "state_sources.csv")
_cache = {}


def page(url):
    if url not in _cache:
        _cache[url] = http_get(url).decode("utf-8", "replace")
    return _cache[url]


def key(sec):
    """'501.2041' -> (501, '2041'); '445.903e' -> (445, '903e'); plain compare inside one chapter."""
    a, _, b = sec.partition(".")
    return (int(re.sub(r"\D", "", a) or 0), b)


def in_range(sec, lo, hi):
    return key(lo) <= key(sec) <= key(hi)


# ---------------------------------------------------------------- per-state builders
def fl(chapter, lo=None, hi=None, only=None):
    c = int(chapter)
    block = f"{c // 100 * 100:04d}-{c // 100 * 100 + 99:04d}"
    base = "https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL="
    if only:
        return [f"{base}{block}/{c:04d}/Sections/{c:04d}.{s.split('.')[1]}.html" for s in only]
    # the chapter index lists sections directly, or lists parts whose own index lists the sections
    idx = page(f"{base}{block}/{c:04d}/{c:04d}ContentsIndex.html")
    htmls = [idx] + [page(f"{base}{block}/{c:04d}/{name}") for name in
                     dict.fromkeys(re.findall(rf"URL={block}/{c:04d}/({c:04d}PART[A-Za-z]+ContentsIndex\.html)", idx))]
    secs = []
    for html in htmls:
        for x in re.findall(rf"Sections/{c:04d}\.([0-9A-Za-z]+)\.html", html):
            if f"{c}.{x}" not in secs:
                secs.append(f"{c}.{x}")
    return [f"{base}{block}/{c:04d}/Sections/{c:04d}.{x.split('.')[1]}.html" for x in secs if lo is None or in_range(x, lo, hi)]


def oh(chapter, lo=None, hi=None, only=None):
    base = "https://codes.ohio.gov/ohio-revised-code/"
    if only:
        return [base + "section-" + s for s in only]
    html = page(base + "chapter-" + chapter)
    secs = []
    for s in re.findall(r'href="[^"]*section-([0-9.]+)"', html):
        if s not in secs:
            secs.append(s)
    return [base + "section-" + s for s in secs if lo is None or in_range(s, lo, hi)]


def mi_act(act, lo=None, hi=None):
    base = "https://www.legislature.mi.gov/Laws/MCL?objectName="
    html = page(base + act)
    out = []
    for obj in re.findall(r"objectName=(mcl-\d+-[0-9a-zA-Z]+)", html):
        m = re.match(r"mcl-(\d+)-([0-9a-zA-Z]+)$", obj)
        sec = f"{m.group(1)}.{m.group(2)}"
        if (lo is None or in_range(sec, lo, hi)) and base + obj not in out:
            out.append(base + obj)
    return out


def mi(*secs):
    return ["https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-" + s.replace(".", "-") for s in secs]


def nc_sec(chapter, *secs):
    return [f"https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/BySection/Chapter_{chapter}/GS_{s}.html" for s in secs]


def nc_art(chapter, article):
    return [f"https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/ByArticle/Chapter_{chapter}/Article_{article}.html"]


def tx(code, chapter):
    return [f"https://tcss.legis.texas.gov/resources/{code}/htm/{code}.{chapter}.htm"]


def il_dir(ch, act, pattern=None):
    d = f"https://ftp.ilga.gov/ILCS/Ch%20{ch:04d}/Act%20{act:04d}/"
    html = page(d)
    out = []
    for href in re.findall(r'(?i)href="([^"]+\.html)"', html):
        name = urllib.parse.unquote(href).rsplit("/", 1)[-1]
        if pattern is None or re.search(pattern, name):
            out.append(d + urllib.parse.quote(name))
    return out


def pa_act(year, num):
    return [f"https://www.palegis.us/statutes/unconsolidated/law-information/view-statute?txtType=HTM&SessYr={year}&ActNum={num:04d}&SessInd=0&SMthLwInd=0&iFrame=true"]


def pa_cs(ttl, chpt, *sctns):
    return [f"https://www.palegis.us/statutes/consolidated/view-statute?txtType=HTM&ttl={ttl}&div=0&chpt={chpt}&sctn={s}&subsctn=0&iFrame=true" for s in sctns]


UCC_EXTRA = ("714", "715", "719", "725")          # remedies, limitation of remedy, statute of limitations

PLAN = {
    # ---------------- Florida
    "FL-udap": lambda: fl(501, "501.201", "501.213"),
    "FL-lemon_law": lambda: fl(681),
    "FL-gift_cards": lambda: fl(501, only=["501.95"]),
    "FL-auto_renewal": lambda: fl(501, only=["501.165"]),
    "FL-service_contracts": lambda: fl(634, "634.011", "634.444"),
    "FL-unfair_claims": lambda: fl(626, only=["626.9541", "626.9743", "626.9744"]),
    "FL-refund_policy": lambda: fl(501, only=["501.142"]),
    "FL-home_solicitation": lambda: fl(501, "501.021", "501.055"),
    "FL-ucc_warranties": lambda: fl(672, only=["672.313", "672.314", "672.315", "672.316", "672.317", "672.318"] + ["672." + x for x in UCC_EXTRA]),
    # ---------------- Ohio
    "OH-udap": lambda: oh("1345", "1345.01", "1345.13"),
    "OH-lemon_law": lambda: oh("1345", "1345.71", "1345.78"),
    "OH-gift_cards": lambda: oh(None, only=["1349.61"]),
    "OH-service_contracts": lambda: oh(None, only=["3905.422"]),
    "OH-unfair_claims": lambda: ["https://codes.ohio.gov/ohio-administrative-code/rule-3901-1-07", "https://codes.ohio.gov/ohio-administrative-code/rule-3901-1-54"],
    "OH-home_solicitation": lambda: oh("1345", "1345.21", "1345.28"),
    "OH-ucc_warranties": lambda: oh(None, only=["1302.26", "1302.27", "1302.28", "1302.29", "1302.30", "1302.31", "1302.88", "1302.89", "1302.93", "1302.98"]),
    "OH-small_claims": lambda: oh(None, only=["1925.01", "1925.02"]),
    # ---------------- North Carolina
    "NC-udap": lambda: nc_art(75, 1),
    "NC-lemon_law": lambda: nc_art(20, "15A"),
    "NC-gift_cards": lambda: nc_sec(66, "66-67.5"),
    "NC-auto_renewal": lambda: nc_sec(75, "75-41"),
    "NC-service_contracts": lambda: nc_art(66, 43),
    "NC-unfair_claims": lambda: nc_sec(58, "58-63-15"),
    "NC-home_solicitation": lambda: nc_sec("25A", "25A-38", "25A-39", "25A-40", "25A-41", "25A-42"),
    "NC-ucc_warranties": lambda: nc_sec(25, *["25-2-" + x for x in ("313", "314", "315", "316", "317", "318") + UCC_EXTRA]),
    "NC-small_claims": lambda: nc_sec("7A", "7A-210"),
    # ---------------- Michigan
    "MI-udap": lambda: mi_act("mcl-Act-331-of-1976"),
    "MI-lemon_law": lambda: mi_act("mcl-Act-87-of-1986"),
    "MI-gift_cards": lambda: mi("445.903e", "445.903f", "445.903g"),
    "MI-unfair_claims": lambda: mi("500.2026"),
    "MI-home_solicitation": lambda: mi_act("mcl-Act-227-of-1971"),
    "MI-ucc_warranties": lambda: mi(*["440.2" + x for x in ("313", "314", "315", "316", "317", "318") + UCC_EXTRA]),
    "MI-small_claims": lambda: mi("600.8401"),
    # ---------------- Texas (whole chapter per file; the official file server behind statutes.capitol.texas.gov)
    "TX-udap": lambda: tx("BC", 17),
    "TX-lemon_law": lambda: tx("OC", 2301),
    "TX-gift_cards": lambda: tx("BC", 604),
    "TX-service_contracts": lambda: tx("OC", 1304),
    "TX-unfair_claims": lambda: tx("IN", 542),
    "TX-home_solicitation": lambda: tx("BC", 601),
    "TX-ucc_warranties": lambda: tx("BC", 2),
    "TX-small_claims": lambda: tx("GV", 27),
    # ---------------- Illinois (public file repository ftp.ilga.gov, one file per section)
    "IL-udap": lambda: il_dir(815, 505),
    "IL-lemon_law": lambda: il_dir(815, 380),
    "IL-gift_cards": lambda: il_dir(815, 505, r"K2SS\.html$"),
    "IL-auto_renewal": lambda: il_dir(815, 601),
    "IL-service_contracts": lambda: il_dir(215, 152),
    "IL-unfair_claims": lambda: il_dir(215, 5, r"K154\.6\.html$"),
    "IL-home_solicitation": lambda: il_dir(815, 505, r"K2B\.html$"),
    "IL-ucc_warranties": lambda: il_dir(810, 5, r"K2-(313|314|315|316|317|318|714|715|719|725)\.html$"),
    # ---------------- Pennsylvania
    "PA-udap": lambda: pa_act(1968, 387),
    "PA-lemon_law": lambda: pa_act(1984, 28),
    "PA-auto_renewal": lambda: pa_act(1989, 87),
    "PA-unfair_claims": lambda: pa_act(1974, 205),
    "PA-home_solicitation": lambda: pa_act(1968, 387),
    "PA-ucc_warranties": lambda: pa_cs(13, 23, 13, 14, 15, 16, 17, 18) + pa_cs(13, 27, 14, 15, 19, 25),
    "PA-small_claims": lambda: pa_cs(42, 15, 15),
}


def main():
    with open(CATALOG, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0].keys())
    for extra in ("download_note",):
        if extra not in fields:
            fields.append(extra)
    for r in rows:
        r.setdefault("download_note", "")
        if r["row_id"] in PLAN:
            try:
                urls = PLAN[r["row_id"]]()
            except Exception as e:
                print("FAILED", r["row_id"], e)
                continue
            r["url"] = " | ".join(urls)
            print(f'{r["row_id"]:24s} {len(urls):4d} url(s)')
            if not urls:
                print("   WARNING: nothing found")
    with open(CATALOG, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
