"""Run the bounded, local export-only experiment. No paid calls or embeddings."""
from pathlib import Path
from time import perf_counter
import argparse
import json
import os
import resource
import sys

# Fail closed if something tries to fetch an HF model during an upload.
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
from ingestion_lab import (Config, make_converter, make_chunker, ingest, json_hash, write_json,
                           check_manifest, evaluation, validate_bytes, evidence_resolves, review_and_export)
from build_fixtures import DOCUMENTS

ROOT = Path(__file__).resolve().parent

def load_config(max_tokens=240, force_ocr=False):
    assets = json.loads((ROOT / '.models/assets.json').read_text())
    return Config(str(ROOT / '.models/docling'), str(ROOT / '.models/tokenizer'),
                  assets['tokenizer_revision'], max_tokens=max_tokens,
                  force_full_page_ocr=force_ocr, assets_hash=json_hash(assets['files']))

def fixture_quality_review(case, report, canonical):
    """Known fictional source text checks, not human labels and not relevance decisions.

    Never used for docs-sm. All known body passages and footer/header must survive
    conversion. A real upload requires a separate visual/content quality review.
    """
    if not canonical or not case['relative_path'].startswith('fixtures/'):
        return None
    key = case['source_group']
    if key not in DOCUMENTS or key in {'recipe','essay','identity','science','ad'}:
        return None
    title, lines = DOCUMENTS[key]
    expected = [title, *lines, 'CLAIMLY TEST FIXTURE - FICTIONAL - NOT A REAL CONTRACT', 'Fictional test source']
    text = ' '.join('\n'.join(p['text'] for p in canonical['pages']).split())
    if not all(' '.join(s.split()) in text for s in expected):
        return None
    if case['case_id'] == 'multipage_contract' and 'No transfer to another vehicle.' not in text:
        return None
    if case['case_id'] == 'table_bill' and not all(x in text for x in ['Meter fee','30.00','12.00','42.00']):
        return None
    return {'approved': True, 'source_sha256':case['sha256'], 'canonical_hash':json_hash(canonical),
            'reviewer':'synthetic-source-exact-content-check-v1',
            'reason':'All authored source passages, dates, amounts, header and footer found. Synthetic test only; not human review.'}

def run(cases, output, config):
    check_manifest(cases, ROOT)
    start=perf_counter()
    converter=make_converter(config)
    chunker=make_chunker(config)
    initialization=perf_counter()-start
    runs=[]
    for i,case in enumerate(cases):
        path=ROOT/case['relative_path']
        source=path.read_bytes()
        report,result,canonical,chunks=ingest(source,path.name,converter,chunker,config,output)
        first_seconds=report['elapsed_seconds']
        review=fixture_quality_review(case,report,canonical)
        if review and report.get('conversion_relevance_eligible'):
            reviewed_source = validate_bytes(source, path.name)
            report,chunks=review_and_export(reviewed_source,result,report,chunker,config,output,review)
            report['elapsed_seconds'] = first_seconds + report.get('export_seconds', 0)
        expected=case['expected_outcome']
        actual=report['relevance']['outcome']
        report.update(case_id=case['case_id'], folder=case['folder'], split=case['split'],
                      primary_test_group=case['primary_test_group'], expected_outcome=expected,
                      human_reviewed=case['human_reviewed'],
                      pass_fail=('pass' if expected==actual else 'fail') if case['human_reviewed'] else 'unscored',
                      preliminary_label_match=(expected==actual) if expected is not None else None,
                      chunk_count=len(chunks),
                      source_checks=[], peak_process_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if canonical:
            if case['relative_path'].startswith('fixtures/') and case['source_group'] in DOCUMENTS:
                title, passages = DOCUMENTS[case['source_group']]
                normalized = ' '.join('\n'.join(p['text'] for p in canonical['pages']).split())
                report['fixture_content_check'] = {
                    'passages_checked': len(passages)+1,
                    'missing_expected_passages': [p for p in [title,*passages] if ' '.join(p.split()) not in normalized],
                    'scope': 'authored source text, dates and amounts; independent of relevance label'}
            validated=validate_bytes(source,path.name)
            for ref in case['expected_evidence']:
                ev={'document_id':validated.document_id,'document_version':validated.document_version,**ref}
                report['source_checks'].append({**ref,'canonical_quote_resolves':evidence_resolves(ev,validated,canonical)})
            report['canonical_pages']=len(canonical['pages'])
            report['mapping_issues']=canonical['mapping_issues']
            report['table_count']=len(result.document.tables)
            report['text_item_count']=len(result.document.texts)
        if case['human_reviewed']:
            matches = expected == actual
            if expected == 'relevant':
                matches = matches and report['acceptance_gate'] and all(c['canonical_quote_resolves'] for c in report['source_checks'])
            else:
                matches = matches and not report['acceptance_gate']
            report['pass_fail'] = 'pass' if matches else 'fail'
        if not report['acceptance_gate']:
            assert not chunks and report['artifact_path'] is None
        runs.append(report)
        write_json(output/'run_report.json',{'configuration':config.identity(),'initialization_seconds':initialization,
                   'runs':runs,'metrics':evaluation(cases,runs),
                   'notice':'Exploratory results. Unreviewed labels are excluded from scored held-out metrics. RSS is process high-water mark, not per-case allocation.'})
        print(f'{i+1}/{len(cases)} {case["case_id"]}: {report.get("conversion_status", "not_run")} / {actual}; admitted={report["acceptance_gate"]}; chunks={len(chunks)}; {report["elapsed_seconds"]:.2f}s',flush=True)
    return runs

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',action='append',default=[])
    parser.add_argument('--output',default='runs/baseline')
    parser.add_argument('--max-tokens',type=int,default=240)
    parser.add_argument('--force-full-page-ocr',action='store_true',help='Explicit retry only; separate configuration identity.')
    args=parser.parse_args()
    cases=json.loads((ROOT/'evaluation_manifest.json').read_text())['cases']
    if args.case:
        chosen=set(args.case)
        cases=[c for c in cases if c['case_id'] in chosen]
        if len(cases)!=len(chosen):raise ValueError('Unknown or repeated --case.')
    output=(ROOT/args.output).resolve()
    if not output.is_relative_to(ROOT):raise ValueError('Keep experiment outputs under parsing/.')
    run(cases,output,load_config(args.max_tokens,args.force_full_page_ocr))

if __name__=='__main__':main()
