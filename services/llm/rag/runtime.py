"""Qwen-token-aware, exact page-span chunks and small-corpus hybrid retrieval."""
import hashlib
import json
import math
import re
from services.llm.app.contracts import Failure

def page_hash(pages):
    return hashlib.sha256(json.dumps(pages,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def chunks_for_pages(document_id,version,pages,hf):
    chunks=[]; limit=hf.settings.chunk_tokens
    for page in pages:
        text=page['text']; start=0
        prefix=f"Document page {page['page']}\n"
        while start<len(text):
            low,high=start+1,len(text); end=start
            while low<=high:
                mid=(low+high)//2
                if hf.budget.embedding_count(prefix+text[start:mid])<=limit:
                    end=mid; low=mid+1
                else: high=mid-1
            if end==start: raise Failure('VALIDATION_ERROR','A source item cannot fit the embedding budget.')
            if end<len(text):
                line=text.rfind('\n',start,end)
                if line>start: end=line+1
                else:
                    if '\t' in text[start:text.find('\n',start) if '\n' in text[start:] else len(text)]:
                        raise Failure('VALIDATION_ERROR','A table row exceeds the chunk budget and needs structural review.')
                    boundary=text.rfind(' ',start,end)
                    if boundary>start: end=boundary+1
            source=text[start:end]; contextual=prefix+source
            if hf.budget.embedding_count(contextual)>limit:
                raise Failure('VALIDATION_ERROR','Embedding input exceeded its budget; no truncation occurred.')
            identity=f'{document_id}:{version}:{page["page"]}:{start}:{end}:{hf.embedding_identity}'
            chunks.append({'chunk_id':hashlib.sha256(identity.encode()).hexdigest(),'document_id':document_id,
                'document_version':version,'page':page['page'],'start':start,'end':end,
                'source_text':source,'contextualized_text':contextual,
                'text_sha256':hashlib.sha256(source.encode()).hexdigest(),'profile':hf.embedding_identity})
            assert text[start:end]==source
            start=end
    for i,c in enumerate(chunks):
        c['order']=i; c['previous_chunk_id']=chunks[i-1]['chunk_id'] if i else None
        c['next_chunk_id']=chunks[i+1]['chunk_id'] if i+1<len(chunks) else None
    return chunks

def hybrid(question,candidates,query_vector,k=3):
    # candidates MUST already be filtered by owner, scope, current version and embedding profile.
    if not candidates: return []
    terms=set(re.findall(r'\w{2,}',question.lower()))
    lexical=sorted(candidates,key=lambda c:(-len(terms & set(re.findall(r'\w{2,}',c['chunk']['source_text'].lower()))),c['chunk']['chunk_id']))
    dense=sorted(candidates,key=lambda c:(-sum(a*b for a,b in zip(query_vector,c['vector'],strict=True)),c['chunk']['chunk_id']))
    scores={}
    for ranked in [lexical,dense]:
        for rank,c in enumerate(ranked,1):
            key=c['chunk']['chunk_id']; scores[key]=scores.get(key,0)+1/(60+rank)
    ordered=sorted(candidates,key=lambda c:(-scores[c['chunk']['chunk_id']],c['chunk']['chunk_id']))
    chosen={c['chunk']['chunk_id'] for c in ordered[:k]}
    for c in ordered[:k]:
        chosen.update(x for x in [c['chunk'].get('previous_chunk_id'),c['chunk'].get('next_chunk_id')] if x)
    return [c['chunk'] for c in candidates if c['chunk']['chunk_id'] in chosen]
