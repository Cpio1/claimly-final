# -*- coding: utf-8 -*-
"""Shared helpers for the Claimly legal corpus downloaders. Standard library only."""
import datetime
import gzip
import hashlib
import json
import re
import time
import urllib.error
import urllib.request

USER_AGENT = "ClaimlyCorpusBuilder/0.1 (legal text collection for a consumer-rights assistant)"
PAUSE_SECONDS = 0.6          # pause between requests: be polite to government servers
MAX_CHUNK_CHARS = 6000       # about 1,500 tokens; sections longer than this are split


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ssl_context():
    """Default trust store plus intermediate certificates shipped in scripts/extra_ca/.
    Added 2026-11-15: ftp.ilga.gov (Illinois public file repository) does not send its intermediate
    certificate, so verification failed. The intermediate is published by the CA (Sectigo) and
    chains to a root that is already trusted. Verification stays ON."""
    import glob, os, ssl
    ctx = ssl.create_default_context()
    for pem in glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "extra_ca", "*.pem")):
        ctx.load_verify_locations(pem)
    return ctx


_CTX = None


def http_get(url, retries=4, timeout=180):
    """GET a URL and return bytes. Retries on 429 and 5xx with growing pauses."""
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT, "Accept-Encoding": "gzip", "Accept": "*/*"})
        try:
            global _CTX
            if _CTX is None:
                _CTX = _ssl_context()
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                    data = gzip.decompress(data)
            time.sleep(PAUSE_SECONDS)
            return data
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} attempts: {url} ({last})")


def clean_text(text):
    """Normalize whitespace but keep paragraph breaks."""
    text = text.replace("\r", "\n").replace(" ", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    out, blank = [], False
    for ln in lines:
        if ln:
            out.append(ln)
            blank = False
        elif not blank and out:
            out.append("")
            blank = True
    return "\n".join(out).strip()


def split_chunks(text, max_chars=MAX_CHUNK_CHARS):
    """Split text on paragraph boundaries so that no chunk exceeds max_chars."""
    if len(text) <= max_chars:
        return [text]
    paras = [p for p in text.split("\n") if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        while len(p) > max_chars:            # a single huge paragraph: hard split on sentence end
            cut = p.rfind(". ", 0, max_chars)
            cut = cut + 1 if cut > max_chars // 2 else max_chars
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(p[:cut].strip())
            p = p[cut:].strip()
        if cur and len(cur) + 1 + len(p) > max_chars:
            chunks.append(cur)
            cur = p
        else:
            cur = (cur + "\n" + p) if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def make_chunks(record, max_chars=MAX_CHUNK_CHARS):
    """Turn one section record into retrieval chunks. Every chunk repeats the citation and
    heading so that it can be quoted with its source even when retrieved alone."""
    parts = split_chunks(record["text"], max_chars)
    header = record["citation"] + (" - " + record["heading"] if record.get("heading") else "")
    out = []
    for i, part in enumerate(parts):
        c = {k: v for k, v in record.items() if k != "text"}
        c["chunk_id"] = f'{record["id"]}#{i + 1}'
        c["chunk_index"] = i + 1
        c["chunk_count"] = len(parts)
        c["text"] = header + "\n" + part
        out.append(c)
    return out


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
