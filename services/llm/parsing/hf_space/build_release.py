"""Assemble only reviewed parsing-demo files; never upload the Claimly workspace."""
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[3]
PARSING = HERE.parent
DESTINATION = WORKSPACE / '.local/parsing-space-release'
APP_FILES = ['app.py', 'demo_engine.py', 'assets.py', 'README.md', 'AGENTS.md', 'requirements.txt', 'packages.txt']
EXAMPLES = ['warranty.pdf', 'scan_pdf.pdf', 'table_bill.pdf', 'multipage_contract.pdf', 'png_scan.png']
MODEL_FILES = [
    'docling-project--docling-layout-heron/config.json',
    'docling-project--docling-layout-heron/preprocessor_config.json',
    'docling-project--docling-layout-heron/model.safetensors',
    'docling-project--docling-models/model_artifacts/tableformer/accurate/tableformer_accurate.safetensors',
    'docling-project--docling-models/model_artifacts/tableformer/accurate/tm_config.json',
    'docling-project--docling-models/model_artifacts/tableformer/fast/tableformer_fast.safetensors',
    'docling-project--docling-models/model_artifacts/tableformer/fast/tm_config.json',
    'RapidOcr/PP-OCRv6_det_small.onnx', 'RapidOcr/PP-OCRv6_rec_small.onnx',
    'RapidOcr/ch_ppocr_mobile_v2.0_cls_mobile.onnx',
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    expected = set(APP_FILES + ['claimly_parser.py', 'asset-lock.json', 'release-manifest.json', 'THIRD_PARTY.md'])
    expected.update('examples/' + name for name in EXAMPLES)
    expected.update('ocr_assets/' + Path(name).name for name in MODEL_FILES if name.startswith('RapidOcr/'))
    unexpected = [p.relative_to(DESTINATION).as_posix() for p in DESTINATION.rglob('*') if p.is_file()
                  and p.relative_to(DESTINATION).as_posix() not in expected and '__pycache__' not in p.parts]
    if unexpected:
        raise RuntimeError('Unexpected release files; inspect before upload: ' + ', '.join(unexpected))
    for name in APP_FILES:
        shutil.copyfile(HERE / name, DESTINATION / name)
    shutil.copyfile(PARSING / 'ingestion_lab.py', DESTINATION / 'claimly_parser.py')
    (DESTINATION / 'examples').mkdir(exist_ok=True)
    for name in EXAMPLES:
        shutil.copyfile(PARSING / 'fixtures' / name, DESTINATION / 'examples' / name)
    original_lock = json.loads((PARSING / 'model-assets.lock.json').read_text())['files']
    pinned = {}
    (DESTINATION / 'ocr_assets').mkdir(exist_ok=True)
    for name in MODEL_FILES:
        source = PARSING / '.models/docling' / name
        digest = sha(source)
        if digest != original_lock['docling/' + name]:
            raise RuntimeError('Stage 1 model hash mismatch; source assets were not changed.')
        pinned[name] = digest
        if name.startswith('RapidOcr/'):
            shutil.copyfile(source, DESTINATION / 'ocr_assets' / Path(name).name)
    asset_lock = {'repositories': {
        'docling-project--docling-layout-heron': {'repo': 'docling-project/docling-layout-heron', 'revision': '8f39ad3c0b4c58e9c2d2c84a38465abf757272d8'},
        'docling-project--docling-models': {'repo': 'docling-project/docling-models', 'revision': 'fc0f2d45e2218ea24bce5045f58a389aed16dc23'},
    }, 'files': pinned}
    (DESTINATION / 'asset-lock.json').write_text(json.dumps(asset_lock, indent=2) + '\n')
    (DESTINATION / 'THIRD_PARTY.md').write_text(
        '# Public model attribution\n\n'
        'Docling: https://github.com/docling-project/docling (MIT).\n'
        'Docling layout Heron: https://huggingface.co/docling-project/docling-layout-heron (Apache-2.0).\n'
        'Docling TableFormer: https://huggingface.co/docling-project/docling-models (MIT).\n'
        'RapidOCR: https://github.com/RapidAI/RapidOCR (Apache-2.0).\n'
        'The three unmodified ONNX models are from the RapidAI/RapidOCR v3.10.0 model distribution:\n'
        'https://modelscope.cn/models/RapidAI/RapidOCR/tree/v3.10.0/onnx\n'
        'PaddleOCR model project: https://github.com/PaddlePaddle/PaddleOCR (Apache-2.0).\n\n'
        'Exact required file hashes are recorded in asset-lock.json. All bundled example documents are fictional Claimly test fixtures.\n'
    )
    files = {p.relative_to(DESTINATION).as_posix(): sha(p) for p in sorted(DESTINATION.rglob('*'))
             if p.is_file() and p.relative_to(DESTINATION).as_posix() in expected
             and p.name != 'release-manifest.json'}
    manifest = {'format': 'claimly-parsing-space-release-v1', 'parser': {
        'source': 'services/llm/parsing/ingestion_lab.py', 'sha256': sha(PARSING / 'ingestion_lab.py'),
        'copy': 'claimly_parser.py', 'unchanged': sha(PARSING / 'ingestion_lab.py') == sha(DESTINATION / 'claimly_parser.py')},
        'files': files}
    (DESTINATION / 'release-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'release': DESTINATION.relative_to(WORKSPACE).as_posix(), 'files': len(files) + 1,
                      'bytes': sum((DESTINATION / name).stat().st_size for name in files),
                      'parser_unchanged': manifest['parser']['unchanged']}, indent=2))


if __name__ == '__main__':
    main()
