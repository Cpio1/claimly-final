"""Map hash-verified, build-preloaded assets without any runtime network calls."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSET_ROOT = ROOT / '.runtime-models'


def prepare_assets() -> Path:
    """Resolve pinned cache snapshots and verified bundled OCR files locally."""
    from huggingface_hub import snapshot_download

    lock = json.loads((ROOT / 'asset-lock.json').read_text())
    ASSET_ROOT.mkdir(exist_ok=True)
    for folder, model in lock['repositories'].items():
        snapshot = Path(snapshot_download(model['repo'], revision=model['revision'], local_files_only=True))
        target = ASSET_ROOT / folder
        if not target.exists():
            target.symlink_to(snapshot, target_is_directory=True)
    target = ASSET_ROOT / 'RapidOcr'
    if not target.exists():
        target.symlink_to(ROOT / 'ocr_assets', target_is_directory=True)
    for name, expected in lock['files'].items():
        path = ASSET_ROOT / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Required parsing model asset is missing or does not match the release lock.')
    return ASSET_ROOT
