"""Explicit, one-time network preparation. Never called by notebook import."""
from pathlib import Path
from time import perf_counter
import json
from huggingface_hub import snapshot_download
from docling.utils.model_downloader import download_models
from ingestion_lab import write_json, digest, versions

ROOT = Path(__file__).resolve().parent
MODEL = 'sentence-transformers/all-MiniLM-L6-v2'

def main():
    start = perf_counter()
    target = ROOT / '.models'
    download_models(output_dir=target / 'docling', with_code_formula=False,
                    with_picture_classifier=False, rapidocr_models=['onnxruntime:en'])
    revision = '1110a243fdf4706b3f48f1d95db1a4f5529b4d41'
    snapshot_download(MODEL, revision=revision, local_dir=target / 'tokenizer',
                      allow_patterns=['config.json', 'tokenizer*', 'special_tokens_map.json', 'vocab.txt'])
    files = {p.relative_to(target).as_posix(): digest(p.read_bytes())
             for p in sorted(target.rglob('*')) if p.is_file() and '.cache' not in p.parts and p != target / 'assets.json'}
    expected = ROOT / 'model-assets.lock.json'
    if expected.exists() and json.loads(expected.read_text())['files'] != files:
        raise ValueError('Prefetched model assets differ from the recorded lock; inspect before using them.')
    write_json(target / 'assets.json', {'model': MODEL, 'tokenizer_revision': revision,
               'files': files, 'versions': versions(), 'prefetch_seconds': perf_counter()-start})
    print(f'Prefetched {len(files)} assets in {perf_counter()-start:.1f}s; tokenizer revision {revision}')

if __name__ == '__main__':
    main()
