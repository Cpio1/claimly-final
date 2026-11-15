"""Bounded, offline diagnostic gallery. Never admits or indexes inspected documents."""
from __future__ import annotations
from base64 import b64encode
from pathlib import Path
import argparse
import json
import os

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
from ingestion_lab import ingest, make_converter, make_chunker, write_json, digest
from run_lab import load_config

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'runs/manual-review'


def selected_sources():
    invoices = sorted((ROOT / 'docs-sm/invoice').glob('*.jpg'))
    paths = [invoices[0], invoices[len(invoices)//2], invoices[-1]]
    paths += [ROOT / p for p in [
        'fixtures/bill.pdf',
        'docs-sm/resume/0000153376.jpg',
        'docs-sm/budget/0000009994.jpg',
        'docs-sm/memo/0000018957.jpg',
        'docs-sm/scientific_report/0000949066.jpg',
        'docs-sm/news_article/0000092722.jpg',
        'docs-sm/email/2064207146a.jpg',
        'docs-sm/letter/0000022394.jpg',
        'docs-sm/handwritten/500002030.jpg',
    ]]
    return paths


def safe_display(value):
    if isinstance(value, dict):
        return {k:safe_display(v) for k,v in value.items()}
    if isinstance(value, list):
        return [safe_display(v) for v in value]
    if isinstance(value, str):
        return value.replace(str(ROOT.parent.parent.parent)+'/', '').replace(str(Path.home())+'/', '~/')
    return value


def build_data():
    from PIL import Image
    from io import BytesIO
    import pypdfium2 as pdfium
    config = load_config()
    converter = make_converter(config)
    chunker = make_chunker(config)
    tokenizer = chunker.tokenizer.get_tokenizer()
    manifest = json.loads((ROOT/'evaluation_manifest.json').read_text())['cases']
    expected = {c['relative_path']:c for c in manifest}
    result_rows = []
    for i,path in enumerate(selected_sources()):
        relative = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        report,result,canonical,chunks = ingest(raw,path.name,converter,chunker,config,OUT)
        assert not chunks and report['acceptance_gate'] is False
        if path.suffix == '.pdf':
            with pdfium.PdfDocument(raw) as pdf:
                image = pdf[0].render(scale=1.5).to_pil()
                buf = BytesIO(); image.save(buf,format='PNG'); visual = buf.getvalue()
            mime = 'image/png'
            original_note = 'First page rendered from original PDF; original PDF unchanged.'
        else:
            visual = raw
            mime = 'image/jpeg'
            original_note = 'Original JPEG bytes, embedded without resizing or replacement.'
        pages = canonical['pages'] if canonical else []
        counted_pages = []
        for page in pages:
            tokens = tokenizer.tokenize(page['text'])
            counted_pages.append({**page,'tokens':tokens,'token_ids':tokenizer.convert_tokens_to_ids(tokens),
                                  'token_count':len(tokens),'characters':len(page['text'])})
        proposed = expected.get(relative)
        row = {'case_id':proposed['case_id'] if proposed else f'invoice-extra-{i+1}',
               'relative_path':relative,'source_sha256':digest(raw),
               'folder':path.parent.name if 'docs-sm' in path.parts else 'fictional control',
               'original_image':'data:'+mime+';base64,'+b64encode(visual).decode(),
               'original_note':original_note,'source_bytes':len(raw),
               'conversion_status':report.get('conversion_status','not_run'),
               'conversion_seconds':report.get('conversion_seconds'),
               'quality':safe_display(report.get('quality',{})),
               'relevance':report['relevance'],
               'processing_error':safe_display(report.get('processing_error')),
               'pages':counted_pages,'token_count':sum(p['token_count'] for p in counted_pages),
               'tables':len(result.document.tables) if result and canonical else 0,
               'proposed_outcome':proposed.get('expected_outcome') if proposed else None,
               'proposed_reason':proposed.get('expected_reason') if proposed else None,
               'label_status':'Unreviewed by a human; machine/agent proposal only.',
               'artifact_scope':'manual inspection diagnostic only; no Vault row or ordinary retrieval chunks'}
        result_rows.append(row)
        print(f'{i+1}/12 {relative}: {row["token_count"]} MiniLM text tokens; {row["relevance"]["outcome"]}',flush=True)
    inventory = [p for p in (ROOT/'docs-sm').rglob('*') if p.is_file()]
    payload = {'version':'claimly-manual-review-v1','tokenizer_model':config.embedding_model,
               'tokenizer_revision':config.tokenizer_revision,
               'token_count_definition':'MiniLM WordPiece tokens in canonical page text, excluding special tokens; not API billing or image tokens.',
               'image_files':sum(p.suffix.lower() in {'.jpg','.jpeg'} for p in inventory),
               'all_files':len(inventory),'invoice_files':len(list((ROOT/'docs-sm/invoice').glob('*.jpg'))),
               'cases':result_rows}
    write_json(OUT/'gallery-data.json',payload)
    return payload


HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claimly · Source review</title>
<style>
:root{font-family:system-ui,-apple-system,sans-serif;color:#202b37;background:#f2f5f8}*{box-sizing:border-box}body{margin:0}header{padding:25px 32px 18px;background:#fff;border-bottom:1px solid #d9e0e7}h1{font-size:26px;letter-spacing:-.6px;margin:0 0 9px}.muted{color:#5a6879;font-size:14px;line-height:1.5}.stats{display:flex;gap:12px;flex-wrap:wrap;margin:17px 0}.stat{background:#edf2f7;border-radius:8px;padding:11px 16px;font-size:14px}.stat b{font-size:21px;margin-right:6px}.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}button,select,input,textarea{font:inherit;border:1px solid #bdc9d5;border-radius:6px;padding:9px 11px;background:white;color:#202b37}button{cursor:pointer}button:hover{background:#eaf0f5}button:disabled{opacity:.35;cursor:default}select{max-width:100%}#case-picker{flex:1;min-width:230px}main{padding:20px 28px}#path{font-family:ui-monospace,monospace;font-size:14px;overflow-wrap:anywhere;margin:0 0 12px}.decision{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}.card{border:1px solid #d9e0e7;background:white;border-radius:9px;padding:15px}.label{text-transform:uppercase;letter-spacing:.08em;font-size:11px;color:#607084;font-weight:700;margin-bottom:8px}.badge{display:inline-block;border-radius:5px;padding:4px 8px;font-size:13px;font-weight:650;background:#e8edf2}.relevant{background:#e1f3e9;color:#17663f}.out_of_scope{background:#f9e5e5;color:#992f34}.uncertain,.unreadable{background:#fff0d3;color:#80570d}.comparison{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px;align-items:start}.image-frame{max-height:80vh;overflow:auto;border:1px solid #dce3eb;background:#e6ebf1;border-radius:6px}.image-frame img{display:block;width:100%;height:auto}#original.actual{width:auto;max-width:none}pre{white-space:pre-wrap;overflow-wrap:anywhere;tab-size:4;font:14px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace;background:#f8fafc;padding:15px;border-radius:5px;max-height:65vh;overflow:auto;margin:10px 0}.page-title{font-size:14px;font-weight:700;margin:16px 0 6px}.tokens{max-height:290px;overflow:auto;line-height:2.1;margin-top:10px}.token{display:inline-block;font:12px ui-monospace,monospace;border:1px solid #d7e4ee;background:#eef5fa;padding:3px 5px;margin:2px;border-radius:4px}.token:nth-child(3n+1){background:#f0eefa}.token:nth-child(3n+2){background:#e8f5ed}details{margin-top:13px}summary{cursor:pointer;font-size:14px}.review{margin-top:20px}.review-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}.field{display:flex;flex-direction:column;gap:6px;font-size:13px}.field.wide{grid-column:1/-1}textarea{width:100%;min-height:78px}.actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:12px}#review-status{font-size:14px;color:#17663f}.notes{font-size:13px;line-height:1.6}a{color:#235c9c}.page-count{margin-left:auto}#counts{font-weight:650}.intro{max-width:1050px}.bottom-note{padding:16px 0;font-size:13px;color:#5a6879}@media(max-width:850px){header{padding:18px}main{padding:16px}.comparison,.decision,.review-grid{grid-template-columns:1fr}.image-frame{max-height:65vh}.stat{padding:8px 11px}}
</style></head><body>
<header><h1>Raw source → extracted text → tokens</h1>
<div class="muted intro">Inspect a small sample before deciding what belongs in Claimly. Filenames and folders are sampling metadata, not relevance labels. All files in this gallery remain inspection diagnostics.</div>
<div class="stats"><div class="stat"><b id="total"></b><span id="image-label">JPEGs</span></div><div class="stat"><b id="invoices"></b>invoices</div><div class="stat"><b id="sample"></b>selected cases</div><div class="stat"><b id="reviewed">0</b>manually reviewed here</div></div>
<div class="toolbar"><button id="prev">← Previous</button><select id="case-picker" aria-label="Selected source"></select><button id="next">Next →</button><a href="review_results.html">Completed reviews</a><span id="counter" class="muted"></span></div></header>
<main><p id="path"></p><div class="decision"><div class="card"><div class="label">Experimental content prediction</div><span id="outcome" class="badge"></span><p id="reason" class="notes"></p><div class="muted">This prediction is not human ground truth or production upload acceptance.</div></div><div class="card"><div class="label">Conversion and token counts</div><div id="counts"></div><p id="conversion" class="notes"></p><div class="muted">MiniLM WordPiece tokens in canonical text, excluding special tokens. No paid model calls. These are not image tokens, API billing counts, or embeddings. Long text still needs chunking.</div></div></div>
<div class="comparison"><section class="card"><div class="toolbar"><div class="label">Original source</div><button id="zoom">Actual size</button></div><div class="image-frame"><img id="original" alt="Original selected document"></div><p id="original-note" class="muted"></p></section><section class="card"><div class="label">Full canonical text · no truncation</div><div id="pages"></div><details><summary>Quality warnings and source audit</summary><pre id="audit"></pre></details><details><summary>Earlier proposed label · pending human review</summary><p id="proposal" class="notes"></p></details></section></div>
<section class="card review"><div class="label">Your manual review</div><p class="muted">Record the content decision separately from readability. Changes stay in this page until you download the review JSON. This does not accept an upload or change the evaluation manifest.</p>
<div class="review-grid"><label class="field">Relevance<select id="manual-outcome"><option value="">Unreviewed</option><option value="relevant">Relevant</option><option value="out_of_scope">Out of scope</option><option value="uncertain">Uncertain</option><option value="unreadable">Unreadable</option></select></label><label class="field">Readability<select id="readability"><option value="">Select readability</option><option>readable</option><option>partial</option><option>difficult</option><option>unreadable</option><option>blank</option></select></label><label class="field">Reviewer<input id="reviewer" placeholder="Your name or initials"></label><label class="field wide">Reason and supporting source quote<textarea id="manual-reason" placeholder="Explain the decision using the actual source content."></textarea></label></div>
<div class="actions"><button id="save-review">Save this case review</button><button id="download">Download saved reviews</button><span id="review-status" role="status"></span></div></section>
<div class="bottom-note">Paths are relative to <span id="path-scope">the parsing folder</span>. Originals are unchanged. Tokenizer: <span id="tokenizer"></span>. <span id="saved-note"></span></div></main>
<script id="gallery-data" type="application/json">__DATA__</script><script>
'use strict';
const data=JSON.parse(document.getElementById('gallery-data').textContent);
const cases=data.cases, reviews=new Map((data.saved_reviews||[]).map(r=>[r.case_id,r]));let index=Math.max(0,cases.findIndex(c=>c.case_id===new URLSearchParams(location.search).get('case')));
const el=id=>document.getElementById(id);
el('total').textContent=data.image_files.toLocaleString();el('image-label').textContent=data.image_label||'JPEGs';el('invoices').textContent=data.invoice_files;el('sample').textContent=cases.length;el('reviewed').textContent=reviews.size;el('tokenizer').textContent=data.tokenizer_model;el('path-scope').textContent=data.path_scope||'the parsing folder';
cases.forEach((c,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${i+1}. ${c.relative_path}`;el('case-picker').append(o)});
function render(){const c=cases[index];el('case-picker').value=index;el('counter').textContent=`${index+1} / ${cases.length}`;el('prev').disabled=index===0;el('next').disabled=index===cases.length-1;
el('path').textContent=c.relative_path;el('original').src=c.original_image;el('original').classList.remove('actual');el('zoom').textContent='Actual size';el('original-note').textContent=c.original_note;
el('outcome').textContent=c.relevance.outcome.replaceAll('_',' ');el('outcome').className='badge '+c.relevance.outcome;el('reason').textContent=c.relevance.reason;
el('counts').textContent=`${c.token_count.toLocaleString()} text tokens · ${c.pages.reduce((n,p)=>n+p.characters,0).toLocaleString()} characters · ${c.tables} tables`;
el('conversion').textContent=`Conversion: ${c.conversion_status} · ${Number(c.conversion_seconds||0).toFixed(2)} s · quality checks: ${c.quality.passed?'structural pass':'review required'} · export: ${c.acceptance_gate?'approved local checkpoint ('+(c.admitted_chunk_count||0)+' chunks)':'withheld in inspection gallery'}`;
el('pages').replaceChildren();for(const p of c.pages){const title=document.createElement('div');title.className='page-title';title.textContent=`Page ${p.page} · ${p.token_count} tokens · ${p.characters} characters`;el('pages').append(title);const pre=document.createElement('pre');pre.textContent=p.text;el('pages').append(pre);const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent=`Show all ${p.token_count} token pieces and IDs`;details.append(summary);const tokens=document.createElement('div');tokens.className='tokens';p.tokens.forEach((t,i)=>{const span=document.createElement('span');span.className='token';span.textContent=t;span.title=`position ${i}; token ID ${p.token_ids[i]}`;tokens.append(span)});details.append(tokens);el('pages').append(details)}
if(!c.pages.length){const p=document.createElement('p');p.textContent='No canonical text is available; inspect conversion failure.';el('pages').append(p)}
el('audit').textContent=JSON.stringify({relative_path:c.relative_path,source_sha256:c.source_sha256,warnings:c.quality.warnings||[],processing_error:c.processing_error,artifact_scope:c.artifact_scope,tokenizer_revision:data.tokenizer_revision},null,2);
el('proposal').textContent=c.proposed_outcome?`${c.proposed_outcome}: ${c.proposed_reason} ${c.label_status}`:'No earlier expected label exists. Inspect and label the source content.';
const r=reviews.get(c.case_id);if(r)el('reviewer').value=r.reviewer;el('manual-outcome').value=r?.expected_outcome||'';el('readability').value=r?.readability||'';el('manual-reason').value=r?.expected_reason||'';el('review-status').textContent=r?'Saved for this case.':'';}
el('case-picker').onchange=e=>{index=Number(e.target.value);render()};el('prev').onclick=()=>{if(index>0){index--;render()}};el('next').onclick=()=>{if(index<cases.length-1){index++;render()}};
el('zoom').onclick=()=>{const actual=el('original').classList.toggle('actual');el('zoom').textContent=actual?'Fit width':'Actual size'};
el('save-review').onclick=()=>{const outcome=el('manual-outcome').value,readability=el('readability').value,reason=el('manual-reason').value.trim(),reviewer=el('reviewer').value.trim();if(!outcome||!readability||!reason||!reviewer){el('review-status').textContent='Choose outcome/readability and enter a reason and reviewer.';return}const c=cases[index];reviews.set(c.case_id,{case_id:c.case_id,relative_path:c.relative_path,source_sha256:c.source_sha256,expected_outcome:outcome,expected_reason:reason,readability,reviewer,human_reviewed:true,reviewed_at:new Date().toISOString()});el('reviewed').textContent=reviews.size;el('review-status').textContent='Saved in this page. Download reviews to keep them.'};
el('download').onclick=()=>{if(!reviews.size){el('review-status').textContent='Save at least one case review first.';return}const body={schema_version:'claimly-manual-reviews-v1',note:'User-entered reviews; source hash validation is required before merging into an evaluation manifest.',reviews:Array.from(reviews.values())};const url=URL.createObjectURL(new Blob([JSON.stringify(body,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='claimly-manual-reviews.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),500)};
render();
</script></body></html>'''


def render_gallery(payload, destination):
    encoded = json.dumps(payload,ensure_ascii=False).replace('<','\\u003c').replace('&','\\u0026')
    html = HTML.replace('__DATA__',encoded)
    if '/Users/' in html:
        raise ValueError('An absolute home path would be displayed or embedded in the gallery.')
    Path(destination).parent.mkdir(parents=True,exist_ok=True)
    Path(destination).write_text(html,encoding='utf-8')
    return Path(destination)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--reuse-data',action='store_true',help='Re-render the saved diagnostic data without OCR.')
    args=parser.parse_args()
    payload=json.loads((OUT/'gallery-data.json').read_text()) if args.reuse_data else build_data()
    saved = ROOT / 'manual_reviews.json'
    if saved.exists():
        from review_results import validate_reviews
        payload = {**payload, 'saved_reviews':validate_reviews(json.loads(saved.read_text()),payload,ROOT)}
    render_gallery(payload,ROOT/'manual_review.html')
    print('Saved manual_review.html; data: runs/manual-review/gallery-data.json')

if __name__=='__main__':main()


def notebook_cards(payload):
    """Static, escaped side-by-side cards work in saved notebook output without JS."""
    from html import escape
    cards = ['<div class="claimly-review"><style>.claimly-review details.case{border:1px solid #d4dce5;border-radius:8px;padding:12px;margin:12px 0}.claimly-review summary{cursor:pointer;font-weight:600}.claimly-review .comparison{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px;margin-top:14px}.claimly-review img{width:100%;height:auto}.claimly-review pre{white-space:pre-wrap;overflow-wrap:anywhere;tab-size:4;font-size:13px;line-height:1.6;max-height:620px;overflow:auto;background:#f6f8fa;padding:12px}.claimly-review .pieces{max-height:240px;overflow:auto}.claimly-review .piece{display:inline-block;background:#edf3fa;border:1px solid #d5e1ed;padding:3px 5px;margin:2px;font:12px monospace}.claimly-review .note{font-size:13px;color:#526173}@media(max-width:800px){.claimly-review .comparison{grid-template-columns:1fr}}</style><p><b>Raw source / canonical text / MiniLM tokens.</b> Expand a selected case. These are inspection diagnostics, not accepted Vault/index artifacts. Counts exclude special tokens and are not API billing counts.</p>']
    for i,c in enumerate(payload['cases']):
        title = escape(f'{c["relative_path"]} · {c["token_count"]} tokens · {c["relevance"]["outcome"]}')
        card = [f'<details class="case" {"open" if i==0 else ""}><summary>{title}</summary>',
                '<div class="comparison"><div><b>Original source</b>',
                f'<img src="{c["original_image"]}" alt="{escape(c["relative_path"],quote=True)}">',
                f'<p class="note">{escape(c["original_note"])}</p></div><div><b>Full canonical text</b>',
                f'<p class="note">Prediction: {escape(c["relevance"]["reason"])}</p>']
        review = c.get('human_review')
        if review:
            card += [f'<p><b>Your human review: {escape(review["expected_outcome"])} · {escape(review["readability"])}</b></p>',
                     f'<p class="note">Reviewer: {escape(review["reviewer"])} | {escape(review["reviewed_at"])}</p>',
                     f'<p>{escape(review["expected_reason"])}</p>']
        for p in c['pages']:
            card += [f'<p><b>Page {p["page"]} · {p["token_count"]} tokens · {p["characters"]} characters</b></p>',
                     f'<pre>{escape(p["text"])}</pre>',
                     f'<details><summary>All {p["token_count"]} token pieces (hover for token IDs)</summary><div class="pieces">']
            card += [f'<span class="piece" title="token ID {token_id}">{escape(token)}</span>' for token,token_id in zip(p['tokens'],p['token_ids'])]
            card += ['</div></details>']
        card += [f'<p class="note">Quality warnings: {escape("; ".join(c["quality"].get("warnings",[])) or "none")}</p>',
                 '</div></div></details>']
        cards.append(''.join(card))
    cards.append('</div>')
    return ''.join(cards)
