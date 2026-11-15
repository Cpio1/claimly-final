"""Build a portable Stage 1 record and a verified, review-aware RAG handoff. No models run."""
from __future__ import annotations
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import shutil

LAB=Path(__file__).resolve().parent
PROJECT=LAB.parents[2]


def portable(value):
    if isinstance(value,dict):return {k:portable(v) for k,v in value.items()}
    if isinstance(value,list):return [portable(v) for v in value]
    if isinstance(value,str):return value.replace(str(PROJECT)+'/', '').replace(str(Path.home())+'/', '~/')
    return value


def write(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')


def verify_checkpoint(path):
    path=Path(path)
    manifest=json.loads((path/'manifest.json').read_text())
    if manifest.get('acceptance_gate') is not True or manifest.get('relevance',{}).get('outcome')!='relevant':
        raise ValueError('Checkpoint is not acceptance-gate approved.')
    if not manifest.get('quality',{}).get('passed') or manifest.get('review_state')!='reviewed':
        raise ValueError('Checkpoint quality is unresolved.')
    for name,expected in manifest['artifact_hashes'].items():
        asset=(path/name).resolve()
        if not asset.is_relative_to(path.resolve()) or sha256(asset.read_bytes()).hexdigest()!=expected:
            raise ValueError('Checkpoint integrity failure.')
    pages=json.loads((path/'pages.json').read_text())
    by_page={p['page']:p['text'] for p in pages['pages']}
    mappings={}
    for m in pages['item_map']:
        if by_page[m['page']][m['start']:m['end']]!=m['text']:raise ValueError('Canonical span mismatch.')
        mappings.setdefault(m['item_ref'],[]).append(m)
    chunks=[json.loads(line) for line in (path/'chunks.jsonl').read_text().splitlines() if line.strip()]
    for chunk in chunks:
        if (chunk['document_id'],chunk['document_version'])!=(manifest['document_id'],manifest['document_version']):
            raise ValueError('Chunk identity mismatch.')
        if not chunk['item_refs'] or any(r not in mappings for r in chunk['item_refs']):raise ValueError('Chunk source reference missing.')
        if not chunk['source_locations'] or any(p['page'] not in by_page for p in chunk['source_locations']):raise ValueError('Chunk page missing.')
    return manifest,pages,chunks


def build_handoff():
    baseline=json.loads((LAB/'runs/final/run_report.json').read_text())
    generated=json.loads((LAB/'generated_test_results.json').read_text())
    cases={c['case_id']:c for c in json.loads((LAB/'evaluation_manifest.json').read_text())['cases']}
    handoff=LAB/'rag-handoff';handoff.mkdir(exist_ok=True)
    entries=[]
    # Prefer a multi-page contract, but do not activate multiple source variants.
    primary={'contract':'multipage_contract'}
    for row in baseline['runs']:
        if not row['acceptance_gate']:continue
        case=cases[row['case_id']]
        source=Path(row['artifact_path'])
        if not source.is_absolute():source=PROJECT/source
        verify_checkpoint(source)
        dest=handoff/'checkpoints'/row['case_id']
        if dest.exists():shutil.rmtree(dest)
        shutil.copytree(source,dest)
        manifest=json.loads((dest/'manifest.json').read_text())
        manifest=portable(manifest);manifest['artifact_path']='.'
        manifest['handoff_scope']='Notebook-approved synthetic fixture checkpoint; not production acceptance.'
        write(dest/'manifest.json',manifest)
        verify_checkpoint(dest)
        original=LAB/case['relative_path']
        source_copy=handoff/'sources'/(row['case_id']+original.suffix)
        source_copy.parent.mkdir(exist_ok=True);shutil.copyfile(original,source_copy)
        group=case['source_group']
        active=row['case_id']==primary.get(group,group)
        reason=None
        if group=='bill':
            active=False;reason='Manual review of the bill is uncertain; deadline-context clarification needs reconciliation. Source remains supported by existing policy, but this seed is withheld pending review.'
        elif not active:reason='Variant retained for robustness tests; a single primary source is active per source group.'
        entries.append({'case_id':row['case_id'],'document_id':row['document_id'],'document_version':row['document_version'],
                        'source_group':group,'source_sha256':case['sha256'],'source_path':source_copy.relative_to(handoff).as_posix(),
                        'checkpoint_path':dest.relative_to(handoff).as_posix(),'chunk_count':row['chunk_count'],
                        'default_active':active,'inactive_reason':reason,'label_provenance':'fixture author expectations; independent human held-out relevance labels pending',
                        'split':case['split'],'demo_session':'session-A' if group in {'receipt','warranty','certificate','membership','foreign'} else 'session-B'})
    generated_cases={c['case_id']:c for c in json.loads((LAB/'generated_test_manifest.json').read_text())['cases']}
    for row in generated['cases']:
        if not row['acceptance_gate']:continue
        case=generated_cases[row['case_id']]
        source=Path(row['artifact_path'])
        if not source.is_absolute():source=PROJECT/source
        verify_checkpoint(source)
        dest=handoff/'checkpoints'/row['case_id']
        if dest.exists():shutil.rmtree(dest)
        shutil.copytree(source,dest)
        checkpoint=portable(json.loads((dest/'manifest.json').read_text()))
        checkpoint.update(artifact_path='.',handoff_scope='User-supplied test source accepted under the user-confirmed title-plus-period rule; not proof of real-world coverage.')
        write(dest/'manifest.json',checkpoint);verify_checkpoint(dest)
        original=PROJECT/case['relative_path']
        source_copy=handoff/'sources'/(row['case_id']+original.suffix)
        shutil.copyfile(original,source_copy)
        entries.append({'case_id':row['case_id'],'document_id':row['document_id'],'document_version':row['document_version'],
                        'source_group':case['source_group'],'source_sha256':case['sha256'],'source_path':source_copy.relative_to(handoff).as_posix(),
                        'checkpoint_path':dest.relative_to(handoff).as_posix(),'chunk_count':row['chunk_count'],
                        'default_active':True,'inactive_reason':None,
                        'label_provenance':'User-confirmed supported-title-plus-period policy; exact-format/body interpretation flags retained.',
                        'split':'tuning','demo_session':'session-C'})
    exclusions=[{'case_id':r['case_id'],'relative_path':r['relative_path'],'relevance':r['relevance']['outcome'],
                 'reason':'Not acceptance-gate approved; no ordinary retrieval chunks.',
                 'source_checks':r['source_passage_checks'],'review_notes':r['source_review_notes']} for r in generated['cases'] if not r['acceptance_gate']]
    manifest={'schema_version':'claimly-rag-handoff-v1','scope':'local experiment fixtures only','as_of':'2026-11-15',
              'embedding_status':'Not implemented. Tokenizer only; no vectors or semantic recall measured.',
              'demo_session_note':'Synthetic test assignments only; Backend determines real ownership/authorization.',
              'checkpoint_count':len(entries),'all_checkpoint_chunks':sum(e['chunk_count'] for e in entries),
              'default_active_documents':sum(e['default_active'] for e in entries),
              'default_active_chunks':sum(e['chunk_count'] for e in entries if e['default_active']),
              'documents':entries,'generated_sources_excluded':exclusions}
    write(handoff/'index_input_manifest.json',manifest)
    questions=[
      ('warranty','How long is the laptop warranty and which damage is excluded?', ['Coverage lasts 24 months from purchase.','Excludes accidental damage and liquid damage.']),
      ('certificate','What is the printed certificate expiry and how many services are stated?', ['Printed expiry: 2027-12-31. Appointment required.','Valid for four dental cleaning services.']),
      ('insurance','What deductible and exclusions are printed in the insurance policy?', ['Deductible: USD 500.00.','Excludes flood water and gradual wear.']),
      ('agreement','What maintenance is included and what is excluded?', ['Includes one preventive maintenance visit. Booking required.','Excludes replacement parts.']),
      ('contract','Does the vehicle service contract include repairs or allow transfer?', ['Excludes repairs and government inspections.','No transfer to another vehicle.']),
      ('membership','What membership period is printed?', ['Membership term: 2026-01-01 through 2026-12-31.']),
      ('refund','What refund amount and timing are stated?', ['Refund USD 29.00 processed for order R-17.','Credit timing is not specified.']),
      ('foreign','What amount and currency were paid at the Euro shop?', ['Amount paid: EUR 19.50.']),
      ('receipt','How much was paid for the coffee maker?', ['Coffee maker model M1. Amount paid: USD 89.50.']),
      ('subscription','What does the subscription say about renewal?', ['Renews monthly unless canceled.']),
      ('correspondence','What service is mentioned for order SC-17?', ['Your order SC-17 includes a maintenance visit.']),
    ]
    if any(e['source_group']=='generated-warranty-certificate' and e['default_active'] for e in entries):
        questions.append(('generated-warranty-certificate','What period and purchase-document condition are printed on the uploaded warranty certificate?',
                          ['from 12.02.2024 to 12.02.2027','original purchase document']))
    qrows=[]
    for group,question,quotes in questions:
        entry=next(e for e in entries if e['source_group']==group and e['default_active'])
        _,pages,_=verify_checkpoint(handoff/entry['checkpoint_path'])
        refs=[]
        for text in quotes:
            page=next((p for p in pages['pages'] if ' '.join(text.split()) in ' '.join(p['text'].split())),None)
            if page is None:raise ValueError('Expected retrieval quote is absent from canonical source.')
            refs.append({'document_id':entry['document_id'],'document_version':entry['document_version'],'page':page['page'],'quote':text})
        qrows.append({'query_id':'seed-'+group,'question':question,'source_group':group,'split':'tuning',
                      'demo_session':entry['demo_session'],'allowed_document_ids':[entry['document_id']],
                      'expected_evidence_refs':refs,'evaluation_target':'retrieval evidence and citation resolution; no generated answer',
                      'label_provenance':'authored fixture ground truth; not blind held-out evaluation'})
    write(handoff/'retrieval_questions.json',{'schema_version':'claimly-rag-queries-v1','queries':qrows,
          'next_required':'Add genuinely new held-out source groups and negative/no-evidence, cross-session, version, deletion and authoritative-rule cases before tuning claims.'})
    reports=LAB/'reports';reports.mkdir(exist_ok=True)
    write(reports/'baseline-55.json',portable(baseline))
    write(reports/'generated-samples.json',generated)
    for name in ['review-comparison.json']:
        write(reports/name,json.loads((LAB/'runs/manual-review'/name).read_text()))
    prior_summary=json.loads((reports/'stage-summary.json').read_text()) if (reports/'stage-summary.json').exists() else {}
    write(reports/'stage-summary.json',{**prior_summary,'status':'Notebook/export experiment finalized; production not implemented or approved.',
          'baseline_cases':len(baseline['runs']),'baseline_outcomes':dict(Counter(r['relevance']['outcome'] for r in baseline['runs'])),
          'baseline_admitted':sum(r['acceptance_gate'] for r in baseline['runs']),'baseline_chunks':sum(r['chunk_count'] for r in baseline['runs']),
          'new_generated_cases':len(generated['cases']),'generated_admitted':generated['admitted'],
          'human_review_count':12,'human_prediction_matches':5,'human_prediction_differences':7,
          'rag_checkpoint_count':len(entries),'rag_default_active_documents':manifest['default_active_documents'],
          'rag_default_active_chunks':manifest['default_active_chunks'],'rag_seed_queries':len(qrows),
          'shared_contracts_changed':False,'paid_calls':0,'embedding_calls':0})
    print(json.dumps({'checkpoints':len(entries),'active_documents':manifest['default_active_documents'],'active_chunks':manifest['default_active_chunks'],'seed_queries':len(qrows)}))
    return manifest

if __name__=='__main__':build_handoff()
