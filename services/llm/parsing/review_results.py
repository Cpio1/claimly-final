"""Validate and display human review exports without changing ingestion policy or scored labels."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
OUTCOMES = {'relevant','out_of_scope','uncertain','unreadable'}
READABILITY = {'readable','partial','difficult','unreadable','blank'}


def validate_reviews(export, gallery, root):
    if export.get('schema_version') != 'claimly-manual-reviews-v1':
        raise ValueError('Unsupported review export schema.')
    cases = {c['case_id']:c for c in gallery['cases']}
    seen = set()
    validated = []
    root = Path(root).resolve()
    for review in export.get('reviews',[]):
        case_id = review.get('case_id')
        if case_id not in cases or case_id in seen:
            raise ValueError('Unknown or duplicate reviewed case.')
        seen.add(case_id)
        case = cases[case_id]
        if review.get('relative_path') != case['relative_path'] or review.get('source_sha256') != case['source_sha256']:
            raise ValueError('Review does not match the selected source identity.')
        path = (root / review['relative_path']).resolve()
        if not path.is_relative_to(root) or sha256(path.read_bytes()).hexdigest() != review['source_sha256']:
            raise ValueError('Reviewed source was changed or is outside the experiment directory.')
        if review.get('human_reviewed') is not True:
            raise ValueError('Review is not marked human-reviewed.')
        if review.get('expected_outcome') not in OUTCOMES or review.get('readability') not in READABILITY:
            raise ValueError('Invalid review outcome/readability.')
        if not all(isinstance(review.get(k),str) and review[k].strip() for k in ['reviewer','expected_reason','reviewed_at']):
            raise ValueError('Reviewer, reason and timestamp are required.')
        timestamp = datetime.fromisoformat(review['reviewed_at'].replace('Z','+00:00'))
        if timestamp.tzinfo is None:
            raise ValueError('Review timestamp must include a timezone.')
        validated.append(dict(review))
    return validated


def clarification_notes(case, review):
    notes = []
    reason = review['expected_reason'].lower()
    if review['expected_outcome']=='relevant' and case['folder']=='invoice' and any(t in reason for t in ['correct','number','dates']):
        notes.append('The reason checks OCR accuracy. Confirm Claimly content relevance separately, including whether corporate billing/reprint material is supported.')
    if case['case_id']=='bill' and review['expected_outcome']!='relevant':
        notes.append('Your clarification concerns the next agent\'s supplied laws/rules/terms for deadline assessment. Keep that assessment separate from upload relevance: current policy allows relevant bills without printed due dates or explicit benefits. This submitted label is preserved pending reconciliation.')
    if review['expected_outcome']=='out_of_scope' and review['readability']=='unreadable' and 'unreadable' in reason:
        notes.append('Unreadability alone does not establish unrelated content. Confirm semantic irrelevance from the original, or keep the relevance unresolved/unreadable.')
    return notes


def compare_reviews(export, gallery, root=ROOT):
    reviews = validate_reviews(export,gallery,root)
    by_id = {r['case_id']:r for r in reviews}
    rows = []
    for case in gallery['cases']:
        review = by_id.get(case['case_id'])
        if not review:
            continue
        rows.append({'case_id':case['case_id'],'relative_path':case['relative_path'],
                     'source_sha256':case['source_sha256'],'human_review':review,
                     'prediction':case['relevance']['outcome'],
                     'prediction_reason':case['relevance']['reason'],
                     'agreement':review['expected_outcome']==case['relevance']['outcome'],
                     'token_count':case['token_count'],'quality_warnings':case['quality'].get('warnings',[]),
                     'clarification_notes':clarification_notes(case,review)})
    return {'schema_version':'claimly-review-comparison-v1','review_count':len(rows),
            'agreement_count':sum(r['agreement'] for r in rows),
            'disagreement_count':sum(not r['agreement'] for r in rows),
            'clarification_case_count':sum(bool(r['clarification_notes']) for r in rows),
            'human_outcomes':dict(Counter(r['human_review']['expected_outcome'] for r in rows)),
            'pipeline_outcomes':dict(Counter(r['prediction'] for r in rows)),
            'evaluation_status':'Descriptive comparison only. Reviews were entered with predictions visible; this is not blind held-out accuracy.',
            'manifest_updated':False,'ingestion_policy_updated':False,
            'rows':rows}


def review_summary_html(report):
    e=escape
    cards = f'''<div class="human-results"><style>
.human-results{{font-family:system-ui,sans-serif;color:#202b37;line-height:1.5}}.human-results .stats{{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}}.human-results .stat{{padding:12px 18px;background:#edf3f8;border-radius:8px}}.human-results .stat strong{{font-size:24px;display:block}}.human-results table{{border-collapse:collapse;width:100%;font-size:14px}}.human-results th,.human-results td{{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #dce3eb}}.human-results th{{background:#edf3f8}}.human-results .scroll{{overflow-x:auto}}.human-results .note{{color:#5b697b;font-size:14px}}.human-results .flag{{background:#fff3d8;padding:10px;border-radius:6px;margin-top:8px}}.human-results .yes{{color:#176640;font-weight:650}}.human-results .no{{color:#985b11;font-weight:650}}.human-results code{{overflow-wrap:anywhere}}.human-results details{{margin:8px 0}}.human-results summary{{cursor:pointer}}.human-results .verbatim{{white-space:pre-wrap}}.human-results a{{color:#235c9c}}
</style><h2>Your completed document reviews</h2><div class="stats"><div class="stat"><strong>{report['review_count']}</strong>human reviews preserved</div><div class="stat"><strong>{report['agreement_count']}</strong>matching predictions</div><div class="stat"><strong>{report['disagreement_count']}</strong>different predictions</div><div class="stat"><strong>{report['clarification_case_count']}</strong>labels to clarify</div></div><p class="note">{e(report['evaluation_status'])} Your original labels and reasons remain unchanged. No evaluation-manifest labels, ingestion rules, Vault rows or index records were changed.</p><p><b>Human labels:</b> {e(', '.join(f"{v} {k}" for k,v in report['human_outcomes'].items()))}.</p><div class="scroll"><table><thead><tr><th>Source</th><th>Your label / readability</th><th>Pipeline prediction</th><th>Comparison</th><th>Your note and follow-up</th></tr></thead><tbody>'''
    clarification = report.get('deadline_context_clarification')
    if clarification:
        cards = cards.replace('<div class="scroll">', '<div class="flag"><b>Downstream deadline context</b><p>' + e(clarification['interpretation']) + '</p><p>' + e(clarification['stage_boundary']) + '</p><p>Your submitted review labels remain unchanged; the external rule corpus is not loaded in this experiment.</p></div><div class="scroll">', 1)
    for row in report['rows']:
        review=row['human_review']
        notes=''.join(f'<div class="flag">{e(n)}</div>' for n in row['clarification_notes'])
        warning='; '.join(row['quality_warnings'])
        cards += f'''<tr><td><a href="manual_review.html?case={quote(row['case_id'])}"><code>{e(row['relative_path'])}</code></a><br><span class="note">{row['token_count']} MiniLM text tokens</span></td><td><b>{e(review['expected_outcome'])}</b><br>{e(review['readability'])}<br><span class="note">Reviewer: {e(review['reviewer'])}</span></td><td>{e(row['prediction'])}<details><summary>Prediction reason / quality</summary>{e(row['prediction_reason'])}<br>{e(warning or 'No conversion warnings recorded.')}</details></td><td class="{'yes' if row['agreement'] else 'no'}">{'Match' if row['agreement'] else 'Different'}</td><td><div class="verbatim">{e(review['expected_reason'])}</div>{notes}<details><summary>Review timestamp</summary>{e(review['reviewed_at'])}</details></td></tr>'''
    cards += '''</tbody></table></div><h3>Next steps</h3><ol><li>Resolve the flagged relevance-versus-OCR and policy questions while keeping the submitted reviews as the audit record.</li><li>Use agreed labels for targeted OCR/relevance improvements; preserve canonical source text and record any corrected transcription separately.</li><li>Evaluate the improved pipeline on additional human-labeled sources that were not used for tuning.</li></ol><p class="note">A review is evaluation evidence, not automatic upload acceptance. The original source files and extraction text remain unchanged.</p></div>'''
    return cards


def save_report(export_path, root=ROOT):
    from ingestion_lab import write_json
    from review_gallery import render_gallery, notebook_cards
    root=Path(root)
    gallery=json.loads((root/'runs/manual-review/gallery-data.json').read_text())
    raw=Path(export_path).read_bytes()
    export=json.loads(raw)
    report=compare_reviews(export,gallery,root)
    # Keep the browser's exact export bytes as the durable human review record.
    destination=root/'manual_reviews.json'
    if destination.exists() and destination.read_bytes()!=raw:
        stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        (root/f'manual_reviews.previous-{stamp}.json').write_bytes(destination.read_bytes())
    destination.write_bytes(raw)
    clarification_path = root / 'manual_review_notes.json'
    if clarification_path.exists():
        report['deadline_context_clarification'] = json.loads(clarification_path.read_text())
    write_json(root/'runs/manual-review/review-comparison.json',report)
    by_id={r['case_id']:r['human_review'] for r in report['rows']}
    decorated={**gallery,'saved_reviews':list(by_id.values()),
               'cases':[{**c,'human_review':by_id.get(c['case_id'])} for c in gallery['cases']]}
    render_gallery(decorated,root/'manual_review.html')
    body=review_summary_html(report)+'<h2>Reviewed sources and conversion text</h2>'+notebook_cards(decorated)
    document='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Claimly · Completed reviews</title></head><body style="max-width:1500px;margin:32px auto;padding:0 22px">'+body+'</body></html>'
    if '/Users/' in document:
        raise ValueError('Absolute home path found in visible review report.')
    (root/'review_results.html').write_text(document,encoding='utf-8')
    print(f'Saved {report["review_count"]} verified reviews: {report["agreement_count"]} matches, {report["disagreement_count"]} differences; {report["clarification_case_count"]} labels need clarification.')
    print('Human record: manual_reviews.json | HTML: review_results.html')
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--reviews',type=Path,default=ROOT/'manual_reviews.json')
    args=parser.parse_args()
    save_report(args.reviews)

if __name__=='__main__':main()
