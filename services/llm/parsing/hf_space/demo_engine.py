"""Isolated inspection-only adapter around the unchanged Claimly Stage 1 parser."""
from functools import lru_cache
from io import BytesIO
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
from uuid import uuid4
import zipfile

from assets import ROOT, ASSET_ROOT
from claimly_parser import Config, InvalidSource, canonical_pages, convert, make_converter, quality_gate, validate_bytes

LOG = logging.getLogger(__name__)
LOCK = threading.Lock()
OUTPUT_ROOT = Path(tempfile.gettempdir()) / 'claimly-parsing-results'
OUTPUT_ROOT.mkdir(mode=0o700, exist_ok=True)
TTL_SECONDS = 3600


def clean_expired() -> None:
    """Remove expired request artifacts without logging document content."""
    while True:
        for directory in OUTPUT_ROOT.iterdir():
            if directory.is_dir() and time.time() - directory.stat().st_mtime > TTL_SECONDS:
                shutil.rmtree(directory, ignore_errors=True)
        time.sleep(300)


@lru_cache(maxsize=1)
def converter():
    """Build one CPU converter using only the prevalidated local assets."""
    config = Config(str(ASSET_ROOT), '', '', threads=2, document_timeout=120.0)
    return make_converter(config)


def read_upload(file_path: str) -> tuple[bytes, str]:
    """Read a Gradio-uploaded file or an explicitly bundled fictional example."""
    if not file_path:
        raise InvalidSource('Choose a PDF, JPEG or PNG first.')
    path = Path(file_path).resolve()
    cache = Path(os.environ.get('GRADIO_TEMP_DIR', str(Path(tempfile.gettempdir()) / 'gradio'))).resolve()
    examples = (ROOT / 'examples').resolve()
    if not (path.is_relative_to(cache) or path.is_relative_to(examples)):
        raise InvalidSource('Please use the document upload control.')
    if not path.is_file():
        raise InvalidSource('The temporary upload is unavailable. Please upload it again.')
    with path.open('rb') as stream:
        data = stream.read(10 * 1024 * 1024 + 1)
    return data, path.name


def preview_pages(data: bytes, mime_type: str, directory: Path) -> list[tuple[str, str]]:
    """Render originals, with EXIF applied to image previews only."""
    from PIL import Image, ImageOps
    previews = []
    if mime_type == 'application/pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(data) as pdf:
            for index in range(len(pdf)):
                page = pdf[index]
                scale = min(1.4, 1400 / max(page.get_size()))
                bitmap = page.render(scale=scale)
                image = bitmap.to_pil().convert('RGB')
                target = directory / f'page-{index + 1}.png'
                image.save(target)
                previews.append((str(target), f'Original · page {index + 1}'))
                bitmap.close()
                page.close()
    else:
        with Image.open(BytesIO(data)) as original:
            image = ImageOps.exif_transpose(original).convert('RGB')
            image.thumbnail((1400, 1800))
            target = directory / 'page-1.png'
            image.save(target)
        previews.append((str(target), 'Original · page 1 · oriented for reading'))
    return previews


def parse_source(file_path: str) -> tuple:
    """Parse one document for inspection; never admit or index its content."""
    started = time.perf_counter()
    data, filename = read_upload(file_path)
    source = validate_bytes(data, filename)
    directory = Path(tempfile.mkdtemp(prefix='request-', dir=OUTPUT_ROOT))
    try:
        with LOCK:
            result, conversion_seconds, warnings = convert(source, converter())
            if result.document is None:
                raise InvalidSource('Conversion produced no readable document. Try a clearer source.')
            canonical = canonical_pages(result.document, source.page_count)
            quality = quality_gate(result, source, canonical, warnings)
        previews = preview_pages(data, source.mime_type, directory)
        text = '\n\n'.join(f"PAGE {p['page']}\n{p['text']}" for p in canonical['pages'])
        manifest = {
            'format': 'claimly-parsing-inspection-v1', 'request_id': str(uuid4()),
            'source': source.identity(), 'source_sha256': hashlib.sha256(data).hexdigest(),
            'page_count': source.page_count, 'serializer_version': canonical['serializer_version'],
            'quality': quality, 'conversion_seconds': round(conversion_seconds, 3),
            'total_seconds': round(time.perf_counter() - started, 3),
            'relevance': 'not_evaluated', 'admission': 'not_performed',
            'source_review': 'required', 'embedding_calls': 0, 'hosted_model_calls': 0,
            'release': json.loads((ROOT / 'release-manifest.json').read_text())['parser'],
        }
        contents = {'document.json': result.document.export_to_dict(), 'canonical.json': canonical, 'manifest.json': manifest}
        archive = directory / 'parsing-inspection.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, value in contents.items():
                bundle.writestr(name, json.dumps(value, ensure_ascii=False, indent=2))
        status = ('Parsing complete · compare the text with the original.' if quality['passed']
                  else 'Review required · conversion quality checks found issues.')
        LOG.info('parse_complete pages=%d quality_passed=%s elapsed_seconds=%.3f', source.page_count, quality['passed'], manifest['total_seconds'])
        return status, previews, text, manifest, canonical['item_map'], str(archive)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
