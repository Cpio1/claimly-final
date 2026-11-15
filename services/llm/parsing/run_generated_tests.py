"""Inspect the three user-supplied generated-test sources with the existing local pipeline."""
from pathlib import Path
from dataclasses import replace
import argparse
import json
import os
import re
from base64 import b64encode
from hashlib import sha256

os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
from ingestion_lab import ingest,make_converter,make_chunker,validate_bytes,review_and_export,json_hash,write_json
from run_lab import load_config
from review_gallery import safe_display,render_gallery,notebook_cards

LAB=Path(__file__).resolve().parent
PROJECT=LAB.parents[2]


def validate_case(case,root=PROJECT):
    root=Path(root).resolve()
    path=(root/case['relative_path']).resolve()
    if not path.is_relative_to(root):raise ValueError('Sample path escapes repository root.')
    if sha256(path.read_bytes()).hexdigest()!=case['sha256']:raise ValueError('Sample source hash changed.')
    return path


def checked_passages(canonical,case):
    text=' '.join('\n'.join(p['text'] for p in canonical['pages']).split()) if canonical else ''
    return [{'quote':q,'resolves_after_whitespace_normalization':' '.join(q.split()) in text}
            for q in case['expected_evidence']]


def run(output='runs/generated-final', force_ocr=False):
    manifest=json.loads((LAB/'generated_test_manifest.json').read_text())
    config=replace(load_config(force_ocr=force_ocr),as_of=manifest['as_of']);converter=make_converter(config);chunker=make_chunker(config)
    root=LAB/output;rows=[];gallery=[]
    for case in manifest['cases']:
        path=validate_case(case)
        raw=path.read_bytes()
        report,result,canonical,chunks=ingest(raw,path.name,converter,chunker,config,root)
        checks=checked_passages(canonical,case)
        # Original source visually inspected; supported title/period is now explicit
        # policy evidence. No visual review can bypass conversion/source checks.
        if (case['case_id'] in {'generated-current-purchase-receipt','generated-warranty-certificate'} and canonical and checks
                and all(c['resolves_after_whitespace_normalization'] for c in checks)
                and report.get('quality',{}).get('passed')):
            source=validate_bytes(raw,path.name)
            review={'approved':True,'source_sha256':source.sha256,'canonical_hash':json_hash(canonical),
                    'reviewer':'Codex visual/source-passage review; human approval pending',
                    'reason':'Original source visually inspected and all recorded source passages preserved. User-confirmed title-plus-period relevance policy applies. Template/synthetic provenance and interpretation notes remain recorded; no legal coverage or unused benefit is inferred.'}
            report,chunks=review_and_export(source,result,report,chunker,config,root,review)
        report.update(case_id=case['case_id'],relative_path=case['relative_path'],
                      expected_relevance=case['expected_relevance'],human_reviewed=False,split='tuning',
                      expected_category=case['expected_category'],source_passage_checks=checks,
                      temporal_state=case['temporal_state'],source_review_notes=case['review_reasons'],
                      provenance=case['provenance'],chunk_count=len(chunks),
                      scoring_status='exploratory; not human-reviewed held-out accuracy')
        rows.append(report)
        inspection=root/'inspection'/case['case_id'];inspection.mkdir(parents=True,exist_ok=True)
        if canonical:
            write_json(inspection/'pages.json',canonical)
            result.document.save_as_json(inspection/'document.json')
        write_json(inspection/'diagnostic.json',safe_display(report))
        pages=[];tokenizer=chunker.tokenizer.get_tokenizer()
        for p in canonical['pages'] if canonical else []:
            tokens=tokenizer.tokenize(p['text']);pages.append({**p,'tokens':tokens,'token_ids':tokenizer.convert_tokens_to_ids(tokens),'token_count':len(tokens),'characters':len(p['text'])})
        mime='image/png' if path.suffix.lower()=='.png' else 'image/jpeg'
        gallery.append({'case_id':case['case_id'],'relative_path':case['relative_path'],
                        'source_sha256':case['sha256'],'original_image':f'data:{mime};base64,'+b64encode(raw).decode(),
                        'original_note':'Original user-supplied bytes; unchanged. '+case['provenance'],
                        'folder':'generated-test','source_bytes':len(raw),'pages':pages,
                        'token_count':sum(p['token_count'] for p in pages),'tables':len(result.document.tables) if canonical else 0,
                        'quality':safe_display(report.get('quality',{})),'relevance':report['relevance'],
                        'acceptance_gate':report['acceptance_gate'],'review_state':report.get('review_state'),
                        'admitted_chunk_count':len(chunks),
                        'conversion_status':report.get('conversion_status'),'conversion_seconds':report.get('conversion_seconds'),
                        'processing_error':safe_display(report.get('processing_error')),
                        'proposed_outcome':case['expected_relevance'],'proposed_reason':case['temporal_state']+'; '+' '.join(case['review_reasons']),
                        'artifact_scope':'diagnostic gallery; only acceptance-gate-approved records can enter RAG seed inputs'})
        print(case['case_id'],report['relevance']['outcome'],'admitted=',report['acceptance_gate'],'chunks=',len(chunks),flush=True)
    summary={'as_of':manifest['as_of'],'pipeline':config.identity(),'cases':rows,
             'admitted':sum(r['acceptance_gate'] for r in rows),'chunks':sum(r['chunk_count'] for r in rows),
             'note':'Current-looking date, supported content, conversion quality and legal applicability are distinct. No legal inference performed.'}
    write_json(root/'run_report.json',safe_display(summary))
    write_json(LAB/'generated_test_results.json',safe_display(summary))
    payload={'cases':gallery,'image_files':3,'image_label':'images','path_scope':'the repository root','all_files':3,'invoice_files':0,
             'tokenizer_model':config.embedding_model,'tokenizer_revision':config.tokenizer_revision}
    write_json(root/'gallery-data.json',payload)
    render_gallery(payload,LAB/'generated_test_review.html')
    print('Saved generated_test_results.json and generated_test_review.html')
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='runs/generated-final');parser.add_argument('--force-full-page-ocr',action='store_true');args=parser.parse_args();run(args.output,args.force_full_page_ocr)
