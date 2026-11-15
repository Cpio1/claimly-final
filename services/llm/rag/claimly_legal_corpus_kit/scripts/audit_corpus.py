#!/usr/bin/env python3
"""Offline integrity/coverage audit. Does not approve legal applicability or build an index."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

SECTION_FILES = ('corpus/federal/cfr_sections.jsonl', 'corpus/federal/usc_sections.jsonl',
                 'corpus/states/state_sections.jsonl')
CHUNK_FILES = ('corpus/federal/chunks.jsonl', 'corpus/states/chunks.jsonl')

def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def audit(root, tokenizer_path=None):
    sections = [r for name in SECTION_FILES for r in rows(root / name)]
    chunks = [r for name in CHUNK_FILES for r in rows(root / name)]
    parents = {r['id']: r for r in sections}
    groups = defaultdict(list)
    for r in sections:
        groups[r['text_sha256']].append(r['id'])
    with (root / 'catalog/state_sources.csv').open(encoding='utf-8-sig', newline='') as f:
        states = list(csv.DictReader(f))
    downloaded = {r['catalog_id'] for r in sections if r['level'] == 'state'}
    result = {
        'audit_version': 'claimly-legal-audit-v1',
        'scope': 'Local files only; integrity and coverage are not verification of current law or applicability.',
        'inputs': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                   for name in (*SECTION_FILES, *CHUNK_FILES, 'catalog/state_sources.csv', 'catalog/federal_sources.csv')},
        'counts': {
            'cfr_sections': len(rows(root / SECTION_FILES[0])),
            'usc_sections': len(rows(root / SECTION_FILES[1])),
            'state_sections': len(rows(root / SECTION_FILES[2])),
            'federal_chunks': len(rows(root / CHUNK_FILES[0])),
            'state_chunks': len(rows(root / CHUNK_FILES[1])),
            'state_catalog_rows': len(states), 'downloaded_state_catalog_rows': len(downloaded),
            'state_rows_with_citation_not_downloaded': sum(bool(r['citation']) and r['row_id'] not in downloaded for r in states),
            'state_rows_without_citation': sum(not r['citation'] for r in states),
            'sections_missing_version_date_or_release_point': sum(not (r.get('version_date') or r.get('release_point')) for r in sections),
            'sections_with_native_effective_date': sum(bool(r.get('effective_date')) for r in sections),
            'sections_without_normalized_effective_interval': sum(not (r.get('effective_from') and r.get('effective_to')) for r in sections),
        },
        'state_sections_by_jurisdiction': dict(sorted(Counter(r['jurisdiction'] for r in sections if r['level'] == 'state').items())),
        'catalog_verification_labels': dict(sorted(Counter(r['verification'] for r in states).items())),
        'integrity': {
            'duplicate_section_ids': len(sections) - len(parents),
            'duplicate_chunk_ids': len(chunks) - len({r['chunk_id'] for r in chunks}),
            'section_hash_failures': [r['id'] for r in sections if sha(r['text']) != r['text_sha256']],
            'orphan_chunks': [r['chunk_id'] for r in chunks if r['id'] not in parents],
            'parent_hash_mismatches': [r['chunk_id'] for r in chunks if r['id'] in parents and r['text_sha256'] != parents[r['id']]['text_sha256']],
            'missing_source_urls': [r['id'] for r in sections if not r.get('source_url')],
            'duplicate_section_text_groups': [ids for ids in groups.values() if len(ids) > 1],
            'chunk_text_hash_differs_from_inherited_parent_hash': sum(sha(r['text']) != r['text_sha256'] for r in chunks),
            'chunk_bodies_not_exact_parent_substrings': sum(r['text'].split('\n', 1)[-1] not in parents[r['id']]['text'] for r in chunks if r['id'] in parents),
        },
        'warnings': [
            'All legal records need an explicit version/applicability review before active retrieval; catalog official is not an admission decision.',
            'retrieved_at and snapshot version_date are not effective-from/effective-to dates. Native CA effective_date fields are not normalized applicability intervals.',
            'Existing text_sha256 on a chunk is inherited from its parent section, not computed over contextualized chunk text.',
            'Legacy chunks use 6000 characters; regenerate token-aware chunks from canonical sections and preserve quote mappings.',
            'Citation ranges on broad state pages can be wider than the actual pinpoint. Resolve subsection identifiers and cited URL before admitting.',
            'Exact duplicate text may belong to distinct provisions. Preserve citation aliases; do not merge distinct legal authorities on text hash alone.',
            'NY and GA have no downloaded section text. Missing coverage is not evidence that a consumer right does not exist.',
        ],
        'index_built': False, 'legal_applicability_verified': False,
    }
    if tokenizer_path is not None:
        from tokenizers import Tokenizer
        tokenizer = Tokenizer.from_file(str(tokenizer_path / 'tokenizer.json'))
        tokenizer.no_truncation()
        tokenizer.no_padding()
        lengths = sorted(len(tokenizer.encode(r['text'], add_special_tokens=True).ids) for r in chunks)
        result['token_audit'] = {
            'tokenizer_asset_sha256': hashlib.sha256((tokenizer_path / 'tokenizer.json').read_bytes()).hexdigest(),
            'includes_special_tokens': True, 'truncation_enabled': False,
            'planned_embedding_limit': 256, 'chunk_count': len(lengths),
            'over_256_tokens': sum(n > 256 for n in lengths),
            'max_tokens': max(lengths), 'median_tokens': lengths[len(lengths)//2],
            'p95_tokens': lengths[int(len(lengths)*.95)],
            'note': 'Token audit only. Embedding weights and semantic vectors are not produced.',
        }
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tokenizer', type=Path, help='Local MiniLM tokenizer folder; no downloads')
    parser.add_argument('--output', type=Path, help='Write JSON explicitly; default prints JSON only')
    args = parser.parse_args()
    report = audit(Path(__file__).resolve().parents[1], args.tokenizer)
    data = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(data)
        print(json.dumps({'counts': report['counts'], 'token_audit': report.get('token_audit'), 'index_built': False}))
    else:
        print(data, end='')
    integrity = report['integrity']
    return int(any(integrity[k] for k in ('duplicate_section_ids', 'duplicate_chunk_ids', 'section_hash_failures', 'orphan_chunks', 'parent_hash_mismatches', 'missing_source_urls')))

if __name__ == '__main__':
    raise SystemExit(main())
