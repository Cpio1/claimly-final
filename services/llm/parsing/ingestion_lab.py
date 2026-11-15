"""Notebook-only Docling experiment; no production endpoints, storage or model calls."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from time import perf_counter
from uuid import UUID, uuid5, NAMESPACE_URL
import importlib.metadata as metadata
import json
import logging
import re
import tempfile
import warnings

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 25
SERIALIZER = 'claimly-pages-v2'
PROCESSOR = 'claimly-docling-lab-v5'
POLICY = 'claimly-content-rules-v3-title-period'
CATEGORIES = {'receipt', 'warranty', 'insurance', 'service_agreement', 'service_contract',
              'gift_certificate', 'subscription', 'membership', 'refund_confirmation',
              'correspondence', 'other'}

def digest(data: bytes) -> str:
    return sha256(data).hexdigest()

def json_hash(value) -> str:
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def versions():
    names = ['docling', 'docling-core', 'docling-ibm-models', 'docling-parse', 'rapidocr',
             'onnxruntime', 'torch', 'transformers', 'pillow', 'pypdf']
    return {name: metadata.version(name) for name in names}

class InvalidSource(ValueError):
    pass

@dataclass
class Source:
    document_id: str
    document_version: int
    filename: str
    mime_type: str
    sha256: str
    page_count: int
    original: bytes
    prepared: bytes
    preparation: str

    def identity(self):
        return {k: v for k, v in asdict(self).items() if k not in {'original', 'prepared'}}

def validate_bytes(data: bytes, filename: str, *, document_id=None, document_version=1,
                   declared_mime=None) -> Source:
    """Validate actual bytes; the original is never mutated, truncated or renamed."""
    from PIL import Image, ImageOps
    from pypdf import PdfReader
    if not data:
        raise InvalidSource('Empty file.')
    if len(data) > MAX_BYTES:
        raise InvalidSource('File exceeds 10 MB (10,485,760 bytes).')
    if not isinstance(document_version, int) or isinstance(document_version, bool) or document_version < 1:
        raise InvalidSource('document_version must be a positive integer.')
    source_hash = digest(data)
    identity = str(UUID(document_id)) if document_id else str(uuid5(NAMESPACE_URL, 'claimly-lab:' + source_hash))
    prepared, preparation = data, 'original bytes'
    if data.startswith(b'%PDF-'):
        mime = 'application/pdf'
        try:
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise InvalidSource('Encrypted PDF: provide an unlocked original.')
            pages = len(reader.pages)
            if not 1 <= pages <= MAX_PAGES:
                raise InvalidSource('PDF must contain 1-25 pages; no pages were truncated.')
            for page in reader.pages:
                page.get_contents()
        except InvalidSource:
            raise
        except Exception as exc:
            raise InvalidSource(f'Damaged PDF ({type(exc).__name__}).') from exc
    elif data.startswith(b'\xff\xd8\xff') or data.startswith(b'\x89PNG\r\n\x1a\n'):
        mime = 'image/jpeg' if data.startswith(b'\xff\xd8\xff') else 'image/png'
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    if image.format != ('JPEG' if mime == 'image/jpeg' else 'PNG'):
                        raise InvalidSource('Image signature and decoder format disagree.')
                    image.verify()
                with Image.open(BytesIO(data)) as image:
                    image.load()
                    if getattr(image, 'n_frames', 1) != 1:
                        raise InvalidSource('Animated/multi-frame images require review; use a static image.')
                    orientation = image.getexif().get(274, 1)
                    normalized = ImageOps.exif_transpose(image).convert('RGB')
                    stream = BytesIO()
                    normalized.save(stream, format='PNG')
                    prepared = stream.getvalue()
                    preparation = f'EXIF orientation {orientation} normalized; RGB PNG; no resize; {normalized.size}'
        except InvalidSource:
            raise
        except Exception as exc:
            raise InvalidSource(f'Damaged or unsafe image ({type(exc).__name__}).') from exc
        pages = 1
    else:
        if b'ftyp' in data[:32] or Path(filename).suffix.lower() in {'.heic', '.heif'}:
            raise InvalidSource('HEIC/HEIF is not supported yet. Export as PDF, JPEG or PNG.')
        raise InvalidSource('Unsupported signature. Supported formats: PDF, JPEG and PNG.')
    if declared_mime and declared_mime != mime:
        raise InvalidSource(f'Declared MIME does not match decoded {mime}.')
    return Source(identity, document_version, Path(filename).name, mime, source_hash, pages,
                  data, prepared, preparation)

@dataclass(frozen=True)
class Config:
    artifacts_path: str
    tokenizer_path: str
    tokenizer_revision: str
    embedding_model: str = 'sentence-transformers/all-MiniLM-L6-v2'
    max_tokens: int = 240  # model supports 256; context counts toward this budget
    force_full_page_ocr: bool = False
    ocr_language: str = 'en'
    threads: int = 4
    assets_hash: str = ''
    document_timeout: float = 120.0
    as_of: str | None = None  # Explicit experiment/Backend-local date; never inferred from the clock.

    def identity(self):
        # Paths are machine-local; they do not change processing identity.
        return {k: v for k, v in asdict(self).items() if not k.endswith('_path')}

def make_converter(config: Config):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions, OcrMode
    from docling.document_converter import DocumentConverter, PdfFormatOption, ImageFormatOption
    options = PdfPipelineOptions(
        artifacts_path=Path(config.artifacts_path), do_ocr=True, do_table_structure=True,
        generate_page_images=True, images_scale=1.5, document_timeout=config.document_timeout,
        accelerator_options=AcceleratorOptions(num_threads=config.threads, device=AcceleratorDevice.CPU),
        ocr_options=RapidOcrOptions(backend='onnxruntime', lang=[config.ocr_language],
                                    mode=OcrMode.FULL_PAGE if config.force_full_page_ocr else OcrMode.DEFAULT,
                                    detect_orientation=True),
    )
    return DocumentConverter(allowed_formats=[InputFormat.PDF, InputFormat.IMAGE], format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=options),
        InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
    })

def make_chunker(config: Config):
    from transformers import AutoTokenizer
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
    from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
    if not 1 <= config.max_tokens <= 256:
        raise ValueError('MiniLM experiment token budget must be <=256.')
    tokenizer = HuggingFaceTokenizer(tokenizer=AutoTokenizer.from_pretrained(
        config.tokenizer_path, local_files_only=True), max_tokens=config.max_tokens)
    return HybridChunker(tokenizer=tokenizer, merge_peers=True)

def convert(source: Source, converter):
    from docling.datamodel.base_models import DocumentStream
    suffix = '.pdf' if source.mime_type == 'application/pdf' else '.png'
    start = perf_counter()
    messages = []
    class Capture(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())
    handler = Capture(level=logging.WARNING)
    logger = logging.getLogger('docling')
    logger.addHandler(handler)
    try:
        result = converter.convert(DocumentStream(name='source' + suffix, stream=BytesIO(source.prepared)),
                                   raises_on_error=False, max_num_pages=MAX_PAGES,
                                   max_file_size=max(MAX_BYTES, len(source.prepared)))
    finally:
        logger.removeHandler(handler)
    return result, perf_counter() - start, messages

def _box(prov):
    return {'page': prov.page_no, 'bbox': prov.bbox.model_dump(mode='json')}

def canonical_pages(doc, count):
    """Exact offsets refer ONLY to this serializer's page text, never PDF byte offsets.

    Text uses Docling's per-provenance character spans. Single-page tables use
    row-major cell text with tabs/newlines; spanning tables require review rather
    than duplicating the complete table onto every page.
    """
    from docling_core.types.doc import TableItem, TextItem, ContentLayer
    pages = {p: {'page': p, 'text': '', 'needs_review': False} for p in range(1, count + 1)}
    mappings, issues = [], []
    # Keep body reading order, then furniture in its own order. The mapping
    # explicitly identifies the layer; no page text is silently discarded.
    ordered = list(doc.iterate_items(included_content_layers=set(ContentLayer), traverse_pictures=True))
    ordered += list(doc.iterate_items(root=doc.furniture, included_content_layers=set(ContentLayer), traverse_pictures=True))
    seen = set()
    for item, _ in ordered:
        if item.self_ref in seen:
            continue
        seen.add(item.self_ref)
        if not isinstance(item, (TextItem, TableItem)):
            continue
        provs = list(item.prov)
        if not provs:
            issues.append(f'{item.self_ref}: text/table without page provenance')
            continue
        if isinstance(item, TableItem):
            if len({p.page_no for p in provs}) != 1:
                issues.append(f'{item.self_ref}: multi-page table requires cell/page mapping review')
                continue
            rows = []
            for row in item.data.grid:
                rows.append('\t'.join(cell.text for cell in row))
            parts = [(provs[0], '\n'.join(rows), 'table-row-major-tabs-v1')]
        else:
            parts = []
            covered = set()
            for prov in provs:
                a, b = prov.charspan
                if 0 <= a <= b <= len(item.text):
                    covered.update(range(a,b))
            if any(not ch.isspace() and i not in covered for i,ch in enumerate(item.text)):
                issues.append(f'{item.self_ref}: provenance charspans omit source text')
            for prov in provs:
                a, b = prov.charspan
                if not 0 <= a <= b <= len(item.text):
                    issues.append(f'{item.self_ref}: invalid source charspan')
                    continue
                parts.append((prov, item.text[a:b], 'docling-text-charspan'))
        for prov, text, method in parts:
            if prov.page_no not in pages:
                issues.append(f'{item.self_ref}: provenance references nonexistent page {prov.page_no}')
                continue
            page = pages[prov.page_no]
            if not text:
                continue
            prefix = '\n' if page['text'] else ''
            start = len(page['text']) + len(prefix)
            page['text'] += prefix + text
            mappings.append({'item_ref': item.self_ref, 'page': prov.page_no, 'start': start,
                             'end': start + len(text), 'text': text, 'method': method,
                             'source_charspan': list(prov.charspan), 'content_layer': item.content_layer.value,
                             'source_locations': [_box(p) for p in provs if p.page_no == prov.page_no]})
    for item in doc.texts:
        if item.text.strip() and item.self_ref not in seen:
            issues.append(f'{item.self_ref}: readable text absent from document traversal')
    for m in mappings:
        assert pages[m['page']]['text'][m['start']:m['end']] == m['text']
    return {'serializer_version': SERIALIZER, 'pages': list(pages.values()),
            'item_map': mappings, 'mapping_issues': issues}

def quality_gate(result, source: Source, canonical, conversion_warnings=()):
    status = getattr(result.status, 'value', str(result.status))
    errors = [e.model_dump(mode='json') if hasattr(e, 'model_dump') else str(e) for e in result.errors]
    reasons = list(canonical['mapping_issues']) + list(conversion_warnings)
    if status != 'success':
        reasons.append(f'Conversion status: {status}')
    if errors:
        reasons.append('Docling reported conversion errors')
    expected = set(range(1, source.page_count + 1))
    actual = set(result.document.pages)
    converted = {p.page_no for p in result.pages}
    if actual != expected or converted != expected:
        reasons.append(f'Incomplete page coverage: document={sorted(actual)}, converted={sorted(converted)}')
    for mapping in canonical['item_map']:
        for loc in mapping['source_locations']:
            page = result.document.pages.get(loc['page'])
            box = loc['bbox']
            if page is not None and (min(box['l'],box['r']) < -2 or max(box['l'],box['r']) > page.size.width+2
                    or min(box['t'],box['b']) < -2 or max(box['t'],box['b']) > page.size.height+2):
                reasons.append(f'{mapping["item_ref"]}: bounding box outside source page')
    page_checks = []
    for page in canonical['pages']:
        text = page['text']
        dp = result.document.pages.get(page['page'])
        image = dp.image.pil_image if dp is not None and dp.image is not None else None
        blank = False
        if image is not None:
            gray = image.convert('L')
            low, high = gray.getextrema()
            blank = low >= 245 and high - low <= 3
        state = 'text' if text.strip() else ('blank' if blank else 'unreadable')
        if state == 'unreadable':
            reasons.append(f'Page {page["page"]}: nonblank/unknown page without readable text')
        if text and (text.count('\ufffd') / len(text) > .01 or len(re.findall(r'\w', text)) < 8):
            reasons.append(f'Page {page["page"]}: sparse/garbled text requires review')
        page_checks.append({'page': page['page'], 'state': state, 'characters': len(text),
                            'has_page_image': image is not None})
    if not any(p['text'].strip() for p in canonical['pages']):
        reasons.append('No readable content; do not guess relevance')
    if reasons:
        for page in canonical['pages']:
            page['needs_review'] = True
    return {'passed': not reasons, 'conversion_status': status, 'errors': errors,
            'warnings': reasons, 'page_checks': page_checks,
            'visual_review': 'required separately; structural checks do not prove OCR completeness or fact correctness'}

def title_period_assessment(pages, as_of):
    """Supported source heading + explicit printed window, independent of exact D/M choice.

    A window is usable only when every valid date interpretation agrees that the
    supplied local as_of date is inside it. Raw ambiguous dates are retained.
    """
    from datetime import date, datetime
    if as_of is None:
        return None
    reference = date.fromisoformat(as_of) if isinstance(as_of,str) else as_of
    titles = [
        ('receipt', r'^(?:purchase |paid )?(?:receipt|bill|invoice)(?:\s+(?:confirmation|certificate))?\s*[:.]?\s*$'),
        ('warranty', r'^(?:limited )?warranty(?:\s+(?:certificate|policy|agreement|terms))?\s*[:.]?\s*$'),
        ('insurance', r'^insurance(?:\s+(?:policy|certificate|agreement|terms))?\s*[:.]?\s*$'),
        ('service_agreement', r'^service agreement(?:\s+terms)?\s*[:.]?\s*$'),
        ('service_contract', r'^service contract(?:\s+terms)?\s*[:.]?\s*$'),
        ('gift_certificate', r'^gift (?:certificate|voucher)(?:\s+terms)?\s*[:.]?\s*$'),
        ('subscription', r'^subscription(?:\s+(?:agreement|confirmation|terms))?\s*[:.]?\s*$'),
        ('membership', r'^membership(?:\s+(?:agreement|confirmation|terms))?\s*[:.]?\s*$'),
        ('refund_confirmation', r'^refund confirmation\s*[:.]?\s*$'),
        ('correspondence', r'^(?:(?:purchase|service|refund) )?correspondence\s*[:.]?\s*$'),
    ]
    headings=[]
    for page in pages:
        for category,pattern in titles:
            match=re.search(pattern,page['text'],re.I|re.M)
            if match:headings.append((page['page'],match.start(),category,match.group(0).strip()))
    if not headings:return None
    headings.sort(key=lambda h:(h[0],h[1]));heading=headings[0]
    atom=r'(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{4})'
    pattern=rf'(?:\bfrom\s+|\b(?:period|term|validity|coverage)\s*:?\s*(?:from\s+)?)({atom})\s*(?:to|through|until|–|—)\s*({atom})'
    def candidates(raw):
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw):
            try:return {'iso':date.fromisoformat(raw)}
            except ValueError:return {}
        result={}
        for style,fmt in [('day_first','%d.%m.%Y'),('month_first','%m.%d.%Y')]:
            try:result[style]=datetime.strptime(raw.replace('/','.').replace('-','.'),fmt).date()
            except ValueError:pass
        return result
    for page in pages:
        match=re.search(pattern,page['text'],re.I)
        if not match:continue
        starts,ends=candidates(match.group(1)),candidates(match.group(2))
        interpretations=[]
        for style,start in starts.items():
            end=ends.get(style)
            if end is not None and start<=end:
                interpretations.append({'format':style,'start':start.isoformat(),'end':end.isoformat(),
                                        'contains_as_of':start<=reference<=end})
        distinct={(i['start'],i['end']) for i in interpretations}
        state=('within_window' if interpretations and all(i['contains_as_of'] for i in interpretations)
               else 'outside_window' if interpretations and not any(i['contains_as_of'] for i in interpretations)
               else 'ambiguous_or_invalid_window')
        flags=[]
        if len(distinct)>1:flags.append('Exact day/month interpretation remains unresolved; all valid interpretations were assessed.')
        if heading[2]=='warranty' and any(re.search(r'\binsurance\b',p['text'],re.I) for p in pages):
            flags.append('Primary category follows the Warranty heading; insurance wording is retained for later field interpretation.')
        return {'category':heading[2],'heading_evidence':{'page':heading[0],'quote':heading[3]},
                'period_evidence':{'page':page['page'],'quote':match.group(0)},
                'period':{'as_of':reference.isoformat(),'raw_start':match.group(1),'raw_end':match.group(2),
                          'state':state,'exact_dates_resolved':len(distinct)==1,'interpretations':interpretations},
                'review_flags':flags}
    return None


def classify_content(pages, *, as_of=None):
    """Conservative, auditable baseline. No filename, folder, labels or category hints."""
    text = '\n'.join(p['text'] for p in pages)
    def decision(outcome, reason, category=None, pattern=None):
        evidence = []
        if pattern:
            for p in pages:
                match = re.search(pattern, p['text'], re.I | re.M)
                if match:
                    evidence.append({'page': p['page'], 'quote': match.group(0)})
                    break
        return {'outcome': outcome, 'reason': reason, 'category': category,
                'evidence': evidence, 'policy_version': POLICY, 'method': 'content-rule-baseline'}
    if not text.strip():
        return decision('unreadable', 'No canonical readable text.')
    if re.search(r'ignore (?:all |previous )?instructions|invent (?:a |any )?benefit|system prompt|force acceptance', text, re.I):
        return decision('uncertain', 'Embedded model instructions detected; independent content review required.')
    negative = r'curriculum vitae|grant expenditures|chemical methods|smoking and health|similarity smoking test|sample specifications|duolite filter rod waste|\brecipe\b|\bpassport\b|free sample advertisement|standalone essay|aglossostomia|misled.{0,15}smokes'
    positive = [
        ('refund_confirmation', r'^refund confirmation\b', r'refund.{0,80}(?:USD|\$|credited|processed)'),
        ('gift_certificate', r'^(?:gift certificate|gift voucher)\b', r'(?:redeem|valid for|services|value)'),
        ('warranty', r'^(?:limited )?warranty\b', r'(?:covers|coverage|months|excludes)'),
        ('insurance', r'^insurance (?:policy|certificate)\b', r'(?:deductible|coverage|excludes|insured)'),
        ('service_contract', r'^service contract\b', r'(?:customer|service|diagnostic|maintenance)'),
        ('service_agreement', r'^service agreement\b', r'(?:customer|service|maintenance)'),
        ('membership', r'^membership (?:agreement|confirmation)\b', r'(?:member|access|term|renewal)'),
        ('subscription', r'^subscription (?:agreement|confirmation)\b', r'(?:renew|month|paid|cancel)'),
        ('receipt', r'^(?:purchase receipt|paid receipt|invoice|bill|purchase confirmation)\b', r'(?:total|amount paid|balance).{0,50}(?:USD|\$|[0-9]+\.[0-9]{2})'),
        ('correspondence', r'^(?:refund correspondence|service correspondence|purchase correspondence)\b', r'(?:order|refund|service|purchase)'),
    ]
    titled_period = title_period_assessment(pages, as_of)
    neg = re.search(negative, text, re.I)
    matches = [(c, title) for c, title, support in positive
               if re.search(title, text, re.I | re.M) and re.search(support, text, re.I | re.S)]
    if neg and (matches or titled_period):
        return decision('uncertain', 'Conflicting supported and unrelated content; review required.')
    if neg:
        return decision('out_of_scope', 'Readable standalone content is unrelated to supported consumer documents.', pattern=negative)
    if titled_period:
        within=titled_period['period']['state']=='within_window'
        result=decision('relevant' if within else 'uncertain',
                        'Supported source title and printed period include the supplied as_of under every valid date interpretation.' if within
                        else 'Supported title found, but the printed period does not establish a current window; review remains required.',
                        titled_period['category'])
        result.update(evidence=[titled_period['heading_evidence'],titled_period['period_evidence']],
                      period_assessment=titled_period['period'],review_flags=titled_period['review_flags'])
        return result
    if not matches:
        # Merchant slips often omit a literal Receipt heading. Require several
        # independent purchase markers; brand names and filenames are not inputs.
        total = re.search(r'\bTOTAL\s*:?\s*(?:USD\s*)?\$?\s*([0-9]+\.[0-9]{2})', text, re.I)
        payment = re.search(r'(?:VISA|MASTERCARD|AMEX|DISCOVER|CASH|DEBIT|CREDIT).{0,20}?(?:CHARGE|PAID|PAYMENT|TENDER).{0,20}?\$?\s*([0-9]+\.[0-9]{2})', text, re.I)
        dated = re.search(r'\bDATE\s*:?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', text, re.I)
        if (total and payment and dated and re.search(r'\bSUBTOTAL', text, re.I)
                and total.group(1) == payment.group(1)):
            return decision('relevant', 'Dated purchase with subtotal, total and matching payment amount found in readable source content.', 'receipt', r'\bTOTAL\s*:?\s*(?:USD\s*)?\$?\s*[0-9]+\.[0-9]{2}')
    if len(matches) == 1:
        category, title = matches[0]
        # B2B invoice is not automatically a supported consumer receipt.
        if category == 'receipt' and re.search(r'public rel|tobacco corp|agency comm', text, re.I):
            return decision('uncertain', 'Business-to-business invoice; consumer relevance is unconfirmed.')
        return decision('relevant', 'Supported document title and substantive terms found in readable content.', category, title)
    return decision('uncertain', 'Content baseline cannot establish Claimly relevance; review required.')

def evidence_resolves(ref, source: Source, canonical):
    if (ref['document_id'], ref['document_version']) != (source.document_id, source.document_version):
        return False
    pages = {p['page']: p['text'] for p in canonical['pages']}
    quote = ' '.join(ref['quote'].split())
    return bool(quote) and quote in ' '.join(pages.get(ref['page'], '').split())

def build_chunks(doc, source, canonical, chunker, processing_id, config):
    by_ref = {}
    for m in canonical['item_map']:
        by_ref.setdefault(m['item_ref'], []).append(m)
    records = []
    for order, chunk in enumerate(chunker.chunk(dl_doc=doc)):
        refs = list(dict.fromkeys(i.self_ref for i in chunk.meta.doc_items))
        if not refs or any(ref not in by_ref for ref in refs):
            raise ValueError('Chunk contains items without canonical source mappings.')
        locations = []
        spans = []
        for ref in refs:
            for m in by_ref[ref]:
                locations.extend(m['source_locations'])
                spans.append({k: m[k] for k in ['item_ref', 'page', 'start', 'end']})
        context = chunker.contextualize(chunk)
        if chunker.tokenizer.count_tokens(context) > config.max_tokens:
            raise ValueError('Contextualized chunk exceeds selected model token budget.')
        text_hash = digest(chunk.text.encode())
        chunk_id = json_hash([source.document_id, source.document_version, processing_id, order, refs, text_hash])
        records.append({'chunk_id': chunk_id, 'processing_id': processing_id,
                        'serializer_version': SERIALIZER, 'document_id': source.document_id,
                        'document_version': source.document_version, 'source_sha256': source.sha256,
                        'source_text': chunk.text, 'contextualized_text': context,
                        'item_refs': refs, 'source_locations': list({json.dumps(p, sort_keys=True): p for p in locations}.values()),
                        'canonical_spans': spans, 'source_mapping_scope': 'whole source items; not exact chunk offsets', 'headings': chunk.meta.headings or [],
                        'order': order, 'text_hash': text_hash,
                        'review_flags': ['Resolve quotations against canonical pages; chunk text may be transformed.']})
    if not records:
        raise ValueError('Relevant document produced no chunks.')
    for i, r in enumerate(records):
        r['previous_chunk_id'] = records[i-1]['chunk_id'] if i else None
        r['next_chunk_id'] = records[i+1]['chunk_id'] if i+1 < len(records) else None
    return records

def ingest(data, filename, converter, chunker, config, output_root, *, document_id=None,
           document_version=1, declared_mime=None, quality_review=None):
    """Only eligible documents get accepted artifacts. Diagnostics contain no document text."""
    start = perf_counter()
    run_key = json_hash([digest(data), document_id, document_version, config.identity(), versions(), SERIALIZER, POLICY, PROCESSOR, quality_review])
    root = Path(output_root)
    diagnostic = root / 'diagnostics' / f'{run_key}.json'
    try:
        source = validate_bytes(data, filename, document_id=document_id,
                                document_version=document_version, declared_mime=declared_mime)
    except (InvalidSource, ValueError) as exc:
        report = {'run_key': run_key, 'validation': 'invalid_file', 'reason': str(exc),
                  'source_sha256': digest(data), 'acceptance_gate': False,
                  'relevance': {'outcome': 'invalid_file', 'reason': str(exc)},
                  'elapsed_seconds': perf_counter()-start, 'artifact_path': None}
        write_json(diagnostic, report)
        return report, None, None, []
    report = {'run_key': run_key, **source.identity(), 'validation': 'valid',
              'versions': versions(), 'pipeline': config.identity(), 'serializer_version': SERIALIZER, 'processor_version': PROCESSOR,
              'acceptance_gate': False, 'artifact_path': None,
              'resolved_pipeline_options': {f.value:o.pipeline_options.model_dump(mode='json') for f,o in converter.format_to_options.items()}}
    result = canonical = None
    chunks = []
    try:
        result, conversion_time, conversion_warnings = convert(source, converter)
        report['conversion_warnings'] = conversion_warnings
        # Inspect status/errors before accessing result.document.
        status = getattr(result.status, 'value', str(result.status))
        report.update(conversion_status=status, conversion_seconds=conversion_time)
        if status != 'success':
            report.update(quality={'passed': False, 'warnings': ['Conversion incomplete; inspect status/errors.'],
                                   'errors': [str(e) for e in result.errors]},
                          relevance={'outcome': 'unreadable', 'reason': 'Incomplete conversion requires review.'})
        else:
            canonical = canonical_pages(result.document, source.page_count)
            quality = quality_gate(result, source, canonical, conversion_warnings)
            relevance = classify_content(canonical['pages'], as_of=config.as_of) if quality['passed'] else {
                'outcome': 'unreadable', 'reason': '; '.join(quality['warnings'])}
            report.update(quality=quality, relevance=relevance, canonical_hash=json_hash(canonical))
            report.update(conversion_relevance_eligible=quality['passed'] and relevance['outcome'] == 'relevant',
                          review_state='quality_review_required')
            if quality_review:
                report, chunks = review_and_export(source, result, report, chunker, config, root, quality_review)

    except Exception as exc:
        # Failed export/chunk validation never admits a document or partial checkpoint.
        report.update(acceptance_gate=False, artifact_path=None,
                      processing_error=f'{type(exc).__name__}: {exc}',
                      relevance=report.get('relevance', {'outcome': 'unreadable', 'reason': 'Conversion unavailable/failed.'}))
        chunks = []
    report['elapsed_seconds'] = perf_counter()-start
    write_json(diagnostic, report)
    return report, result, canonical, chunks

def review_and_export(source, result, initial_report, chunker, config, output_root, quality_review):
    """Review/export the SAME in-memory document. No conversion, OCR or remote call.

    This notebook operation is not Backend upload acceptance. A review can only
    approve source quality; it cannot override relevance or conversion errors.
    """
    report = dict(initial_report)
    report.update(acceptance_gate=False, artifact_path=None, quality_review=quality_review)
    start = perf_counter()
    root = Path(output_root)
    chunks = []
    status = result.status.value
    if status != 'success':
        report['review_state'] = 'incomplete_conversion'
        return report, chunks
    canonical = canonical_pages(result.document, source.page_count)
    quality = quality_gate(result, source, canonical, report.get('conversion_warnings', []))
    relevance = classify_content(canonical['pages'], as_of=config.as_of)
    reviewed = bool(quality_review and quality_review.get('approved') is True
                    and quality_review.get('reviewer') and quality_review.get('reason')
                    and quality_review.get('source_sha256') == source.sha256
                    and quality_review.get('canonical_hash') == json_hash(canonical))
    key = json_hash([source.document_id, source.document_version, source.sha256, config.identity(),
                     versions(), SERIALIZER, POLICY, PROCESSOR, quality_review])
    report.update(run_key=key, quality=quality, relevance=relevance, canonical_hash=json_hash(canonical),
                  review_state='reviewed' if reviewed else 'quality_review_required')
    if quality['passed'] and relevance['outcome'] == 'relevant' and reviewed:
        try:
            chunks = build_chunks(result.document, source, canonical, chunker, key, config)
            dest = root / 'accepted' / source.document_id / str(source.document_version) / key
            if dest.exists():
                manifest = json.loads((dest / 'manifest.json').read_text())
                for name, sha in manifest['artifact_hashes'].items():
                    if digest((dest / name).read_bytes()) != sha:
                        raise ValueError('Existing checkpoint failed integrity validation.')
                if manifest['canonical_hash'] != json_hash(canonical):
                    raise ValueError('Existing checkpoint has different canonical text.')
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(dir=dest.parent) as temp:
                    stage = Path(temp) / 'checkpoint'
                    stage.mkdir()
                    result.document.save_as_json(stage / 'document.json')
                    write_json(stage / 'pages.json', canonical)
                    (stage / 'chunks.jsonl').write_text(''.join(json.dumps(c, ensure_ascii=False)+'\n' for c in chunks))
                    from docling_core.types.doc import DoclingDocument
                    reloaded = DoclingDocument.load_from_json(stage / 'document.json')
                    if canonical_pages(reloaded, source.page_count) != canonical:
                        raise ValueError('JSON reload changed canonical source mappings.')
                    for number, page in result.document.pages.items():
                        if page.image is not None:
                            page.image.pil_image.save(stage / f'page-{number}.png')
                    report.update(acceptance_gate=True, artifact_path=str(dest.resolve()),
                                  document_serialization_version=result.document.version)
                    report['artifact_hashes'] = {p.name:digest(p.read_bytes()) for p in stage.iterdir() if p.is_file()}
                    write_json(stage / 'manifest.json', report)
                    stage.rename(dest)
            report.update(acceptance_gate=True, artifact_path=str(dest.resolve()))
        except Exception as exc:
            report.update(acceptance_gate=False, artifact_path=None,
                          processing_error=f'{type(exc).__name__}: {exc}')
            chunks = []
    report['export_seconds'] = perf_counter()-start
    write_json(root / 'diagnostics' / f'{key}.json', report)
    return report, chunks

def smoke_manifest(root):
    root = Path(root)
    cases = []
    for folder in sorted(p for p in (root / 'docs-sm').iterdir() if p.is_dir()):
        files = sorted(p for p in folder.iterdir() if p.suffix.lower() in {'.jpg', '.jpeg', '.png'})
        if not files:
            continue
        path = files[0]
        sha = digest(path.read_bytes())
        cases.append({'case_id': 'docs-sm-' + folder.name, 'relative_path': path.relative_to(root).as_posix(),
                      'sha256': sha, 'source': 'local docs-sm; upstream provenance/license unverified',
                      'folder': folder.name, 'source_group': sha,
                      'split': 'held_out' if int(sha[:8], 16) % 3 == 0 else 'tuning',
                      'primary_test_group': 'parser_robustness', 'expected_outcome': None,
                      'expected_reason': None, 'expected_category': None, 'expected_evidence': [],
                      'readability': 'unreviewed', 'human_reviewed': False})
    return cases

def check_manifest(cases, root):
    groups = {}
    hashes = {}
    for c in cases:
        path = (Path(root) / c['relative_path']).resolve()
        if not path.is_relative_to(Path(root).resolve()):
            raise ValueError('Fixture path escapes experiment directory.')
        if digest(path.read_bytes()) != c['sha256']:
            raise ValueError(f'Fixture changed: {c["case_id"]}')
        for registry, key in [(groups, c['source_group']), (hashes, c['sha256'])]:
            if key in registry and registry[key] != c['split']:
                raise ValueError('Related/identical sources cross tuning/held-out split.')
            registry[key] = c['split']

def evaluation(cases, runs):
    """No human-reviewed held-out labels => no scored accuracy, never a zero error claim."""
    actual = {r['case_id']: r for r in runs}
    scored = [c for c in cases if c.get('human_reviewed') and c['split'] == 'held_out'
              and c.get('expected_outcome') not in {None, 'invalid_file'} and c['case_id'] in actual]
    def summarize(subset):
        relevant = [c for c in subset if c['expected_outcome'] == 'relevant']
        unrelated = [c for c in subset if c['expected_outcome'] == 'out_of_scope']
        def outcome(c):
            return actual[c['case_id']]['relevance']['outcome']
        def ratio(n, denominator):
            return {'count': n, 'denominator': denominator, 'rate': n/denominator if denominator else None}
        return {'cases': len(subset),
                'false_acceptance': ratio(sum(actual[c['case_id']]['acceptance_gate'] for c in unrelated), len(unrelated)),
                'false_rejection': ratio(sum(outcome(c) == 'out_of_scope' for c in relevant), len(relevant)),
                'unresolved_relevant': ratio(sum(not actual[c['case_id']]['acceptance_gate'] and outcome(c) != 'out_of_scope' for c in relevant), len(relevant)),
                'review': ratio(sum(outcome(c) == 'uncertain' for c in subset), len(subset)),
                'unreadable': ratio(sum(outcome(c) == 'unreadable' for c in subset), len(subset))}
    return {'held_out_scored': summarize(scored),
            'excluded_unreviewed': sum(not c.get('human_reviewed') for c in cases),
            'invalid_validation': {'cases': sum(c.get('expected_outcome') == 'invalid_file' and c['case_id'] in actual for c in cases),
                                  'stopped_before_conversion': sum(c.get('expected_outcome') == 'invalid_file' and c['case_id'] in actual and actual[c['case_id']]['validation'] == 'invalid_file' and 'conversion_status' not in actual[c['case_id']] for c in cases)},
            'by_folder': {f: summarize([c for c in scored if c.get('folder') == f]) for f in sorted({c.get('folder','supplemental') for c in cases})},
            'by_group': {g: summarize([c for c in scored if c['primary_test_group'] == g]) for g in sorted({c['primary_test_group'] for c in cases})}}
