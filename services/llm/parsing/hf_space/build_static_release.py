"""Package the free, browser-only Space without any user documents or secrets."""
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BROWSER = HERE / 'browser'
TARGET = ROOT / '.local/parsing-static-release'
EXAMPLES = ['warranty.pdf', 'scan_pdf.pdf', 'table_bill.pdf', 'multipage_contract.pdf', 'png_scan.png']
APP_FILES = ['index.html', 'style.css', 'app.js', 'AGENTS.md', 'README.md']
VENDORS = ['pdf.mjs', 'pdf.worker.mjs', 'tesseract.min.js', 'worker.min.js']


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / 'examples').mkdir(exist_ok=True)
    (TARGET / 'vendor').mkdir(exist_ok=True)
    for name in APP_FILES:
        shutil.copyfile(BROWSER / name, TARGET / name)
    for name in EXAMPLES:
        shutil.copyfile(HERE.parent / 'fixtures' / name, TARGET / 'examples' / name)
    for name in VENDORS:
        path = TARGET / 'vendor' / name
        if not path.is_file():
            raise RuntimeError('Download the pinned public vendor asset before release: ' + name)
    (TARGET / 'THIRD_PARTY.md').write_text(
        '# Public browser libraries\n\n'
        '- PDF.js / pdfjs-dist 6.5.438 (Apache-2.0): https://github.com/mozilla/pdf.js\n'
        '  https://cdn.jsdelivr.net/npm/pdfjs-dist@6.5.438/build/pdf.mjs\n'
        '  https://cdn.jsdelivr.net/npm/pdfjs-dist@6.5.438/build/pdf.worker.mjs\n'
        '- Tesseract.js 7.0.0 (Apache-2.0): https://github.com/naptha/tesseract.js\n'
        '  https://cdn.jsdelivr.net/npm/tesseract.js@7.0.0/dist/tesseract.min.js\n'
        '  https://cdn.jsdelivr.net/npm/tesseract.js@7.0.0/dist/worker.min.js\n'
        '- OCR core 7.0.0 and WASM: https://cdn.jsdelivr.net/npm/tesseract.js-core@7.0.0\n'
        '- English trained data: https://tessdata.projectnaptha.com/4.0.0/eng.traineddata.gz\n'
        '- DM Sans / Manrope fonts (SIL OFL): https://fonts.google.com\n\n'
        'Only public engine/font assets are fetched. Document bytes remain in the browser.\n'
        'Bundled documents are fictional fixtures from Claimly; none are user uploads.\n'
    )
    allowed = set(APP_FILES + ['THIRD_PARTY.md', 'release-manifest.json'])
    allowed.update('examples/' + name for name in EXAMPLES)
    allowed.update('vendor/' + name for name in VENDORS)
    found = {p.relative_to(TARGET).as_posix() for p in TARGET.rglob('*') if p.is_file()}
    if found - allowed:
        raise RuntimeError('Unexpected files in deployment directory; inspect before upload.')
    files = {name: hashlib.sha256((TARGET / name).read_bytes()).hexdigest()
             for name in sorted(found) if name != 'release-manifest.json'}
    (TARGET / 'release-manifest.json').write_text(json.dumps({
        'format': 'claimly-static-space-release-v1', 'sdk': 'static', 'docling': False,
        'reason': 'Free ZeroGPU creation rejected: account under 30 days old.', 'files': files,
    }, indent=2) + '\n')
    print(json.dumps({'release': TARGET.relative_to(ROOT).as_posix(), 'files': len(files) + 1,
                      'bytes': sum((TARGET / name).stat().st_size for name in files)}, indent=2))


if __name__ == '__main__':
    main()
