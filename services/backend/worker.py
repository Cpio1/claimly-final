"""Durable upload/chat worker. Backend owns admission, sources and vectors."""
from datetime import datetime, timezone
import hashlib
import json
import time
from uuid import UUID, uuid5
from services.llm.app.config import Settings
from services.llm.app.contracts import Failure, VERSION, validate, extraction_check, answer_check
from services.llm.app.hf import HFClient
from services.llm.rag.runtime import chunks_for_pages, page_hash, hybrid
from .config import BackendSettings
from .db import Database,get,put,objects,finish,now,uid,encoded
from .storage import Storage
from .llm_client import HttpLlmClient

class Worker:
    def __init__(self,settings=None,*,db=None,storage=None,llm=None,hf=None):
        self.settings=settings or BackendSettings.env()
        self.db=db or Database(self.settings); self.storage=storage or Storage(self.settings)
        self.llm=llm or HttpLlmClient(self.settings); self.hf=hf or HFClient(Settings.env())
    def once(self):
        claimed=self.db.claim(self.settings.lease_seconds)
        if claimed is None: return False
        try:
            with self.db.tx() as c:
                session=c.execute('SELECT expires FROM claimly_sessions WHERE id=?',(claimed['session_id'],)).fetchone()
                if session is None or session['expires']<time.time(): raise Failure('STALE_INPUT','The source session expired.',409)
            if claimed['kind']=='extract': self.extract(claimed)
            elif claimed['kind']=='answer': self.answer(claimed)
            else: raise Failure('VALIDATION_ERROR','Unsupported integration job kind.')
        except Failure as exc:
            try:
                with self.db.tx(write=True) as c:
                    finished=finish(c,claimed,failure=exc,status='stale' if exc.code in {'STALE_INPUT','NOT_FOUND'} else None)
                    if claimed['kind']=='extract' and exc.code=='VALIDATION_ERROR' and exc.message.startswith('Out of scope:'):
                        self.reject(c,claimed)
                    elif claimed['kind']=='extract' and finished['status']=='failed':
                        try:
                            doc,private=get(c,claimed['session_id'],'document',claimed['payload']['document_id'])
                            doc['status']='failed';doc['review_flags']=list(dict.fromkeys(doc['review_flags']+[exc.code+': '+exc.message]))
                            put(c,claimed['session_id'],'document',doc,private,doc['entry_id'])
                        except Failure:pass
            except Failure: pass  # A deletion/cancellation/lease replacement has already made it inactive.
        except Exception:
            with self.db.tx(write=True) as c:
                try: finish(c,claimed,failure=Failure('INTERNAL_ERROR','The worker could not complete this job.',500))
                except Failure: pass
        return True
    def reject(self,c,claimed):
        owner=claimed['session_id']; doc,private=get(c,owner,'document',claimed['payload']['document_id'])
        self.storage.delete(private['storage_key'])
        c.execute('DELETE FROM claimly_objects WHERE id=? AND session_id=?',(doc['id'],owner))
        entry,ep=get(c,owner,'entry',doc['entry_id'])
        entry['document_ids']=[x for x in entry['document_ids'] if x!=doc['id']]
        if not ep.get('admitted') and not entry['document_ids']:
            c.execute('DELETE FROM claimly_objects WHERE id=? AND session_id=?',(entry['id'],owner))
        else: put(c,owner,'entry',entry,ep)
    def extract(self,claimed):
        owner=claimed['session_id']; doc_id=claimed['payload']['document_id']
        with self.db.tx(write=True) as c:
            doc,private=get(c,owner,'document',doc_id)
            if private.get('deleted') or doc['version']!=claimed['payload']['version']: raise Failure('STALE_INPUT','The document version changed.',409)
            doc['status']='processing'; put(c,owner,'document',doc,private,doc['entry_id'])
        data=self.storage.read(private['storage_key'])
        if hashlib.sha256(data).hexdigest()!=private['source_sha256']:
            raise Failure('STALE_INPUT','The stored source hash changed.',409)
        output=private.get('extraction')
        if output is None:
            metadata={'request_id':claimed['id'],'contract_version':VERSION,'document_id':doc_id,
                      'document_version':doc['version'],'filename':doc['name'],'mime_type':doc['mime_type']}
            output=self.llm.extract(data,metadata,datetime.now(timezone.utc).date().isoformat())
            extraction_check(output,{'document_id':doc_id,'document_version':doc['version'],'pages':output['pages']})
            private.update(extraction=output,pages_sha256=page_hash(output['pages']))
        blocked='quality:blocked' in output['review_flags'] or any(p['needs_review'] for p in output['pages'])
        review=private.get('quality_review',{})
        approved=(review.get('source_sha256')==private['source_sha256'] and review.get('pages_sha256')==private['pages_sha256'])
        if blocked or not approved:
            with self.db.tx(write=True) as c:
                latest,lp=get(c,owner,'document',doc_id)
                if latest['version']!=doc['version'] or lp['source_sha256']!=private['source_sha256']:
                    raise Failure('STALE_INPUT','The document changed during conversion.',409)
                doc['status']='needs_review'; doc['review_flags']=output['review_flags']
                doc['page_count']=len(output['pages']); put(c,owner,'document',doc,private,doc['entry_id'])
                finish(c,claimed,result={'type':'extract','document_id':doc_id,'benefit_ids':[],'review_required':True})
            return
        chunks=chunks_for_pages(doc_id,doc['version'],output['pages'],self.hf)
        vectors=[]
        for offset in range(0,len(chunks),16):
            vectors.extend(self.hf.embed([x['contextualized_text'] for x in chunks[offset:offset+16]]))
        if not chunks or len(vectors)!=len(chunks): raise Failure('INVALID_LLM_OUTPUT','Index batch is incomplete.',502)
        with self.db.tx(write=True) as c:
            latest,lp=get(c,owner,'document',doc_id)
            if latest['version']!=doc['version'] or lp.get('quality_review')!=review:
                raise Failure('STALE_INPUT','Source version or review changed during indexing.',409)
            # Lease checked before publishing any derived state; transaction rolls back on failure.
            finish(c,claimed,result={'type':'extract','document_id':doc_id,'benefit_ids':[], 'review_required':False})
            c.execute('DELETE FROM claimly_vectors WHERE session_id=? AND document_id=?',(owner,doc_id))
            for chunk,vector in zip(chunks,vectors,strict=True):
                c.execute('INSERT INTO claimly_vectors VALUES(?,?,?,?,?,?,?)',
                          (chunk['chunk_id'],owner,doc_id,doc['version'],self.hf.embedding_identity,encoded(chunk),encoded(vector)))
            entry,ep=get(c,owner,'entry',doc['entry_id'])
            benefit_ids=[]
            for candidate in output['benefits']:
                b={k:v for k,v in candidate.items() if k!='candidate_key'}
                b.update(id=str(uuid5(UUID(doc_id),candidate['candidate_key'])),entry_id=entry['id'],usage_state='unknown',
                         used_units=None,remaining_units=None,deadline_date=None,
                         deadline_status='needs_review' if candidate['deadline_rule'] else 'not_known',data_version=1)
                validate('Benefit',b); put(c,owner,'benefit',b,{'document_id':doc_id},entry['id']); benefit_ids.append(b['id'])
            doc.update(status='ready',facts=output['facts'],page_count=len(output['pages']),
                       review_flags=[f for f in output['review_flags'] if f!='quality:source_review_required'])
            private['embedding_profile']=self.hf.embedding_identity
            put(c,owner,'document',doc,private,entry['id'])
            entry.update(title=output['title'],category=output['category'],provider=output['provider'],subject=output['subject'],
                         facts={**entry['facts'],**output['facts']},benefit_ids=list(dict.fromkeys(entry['benefit_ids']+benefit_ids)),
                         data_version=entry['data_version']+1,updated_at=now())
            ep['admitted']=True; put(c,owner,'entry',entry,ep)
            jb=json.loads(c.execute('SELECT body FROM claimly_jobs WHERE id=?',(claimed['id'],)).fetchone()['body'])
            jb['result']['benefit_ids']=benefit_ids
            c.execute('UPDATE claimly_jobs SET body=? WHERE id=?',(encoded(jb),claimed['id']))
    def answer(self,claimed):
        owner=claimed['session_id']; thread_id=claimed['payload']['thread_id']
        with self.db.tx() as c:
            thread,_=get(c,owner,'thread',thread_id)
            message,_=get(c,owner,'message',claimed['payload']['message_id'])
            docs=[(d,p) for d,p in objects(c,owner,'document') if d['status']=='ready'
                  and (thread['scope']!='entry' or d['entry_id']==thread['entry_id'])
                  and (not thread['document_ids'] or d['id'] in thread['document_ids'])]
            allowed={d['id']:d for d,_ in docs}
            rows=[]
            if docs:
                # Ownership, scope, active status, version and profile BEFORE vector/lexical ranking.
                profile=self.hf.embedding_identity
                for row in c.execute('SELECT * FROM claimly_vectors WHERE session_id=? AND profile=?',(owner,profile)).fetchall():
                    doc=allowed.get(row['document_id'])
                    if doc and row['version']==doc['version']:
                        rows.append({'chunk':json.loads(row['chunk']),'vector':json.loads(row['vector'])})
            entries=[e for e,p in objects(c,owner,'entry') if p.get('admitted') and any(d['entry_id']==e['id'] for d,_ in docs)]
            benefits=[b for b,p in objects(c,owner,'benefit') if b['entry_id'] in {e['id'] for e in entries}]
            history=[{'role':m['role'],'content':m['content']} for m,p in objects(c,owner,'message',thread_id)
                     if m['created_at']<message['created_at']]
        selected=hybrid(message['content'],rows,self.hf.embed([message['content']],query=True)[0]) if rows else []
        selected_pages={(x['document_id'],x['document_version'],x['page']) for x in selected}
        context_docs=[{'document_id':d['id'],'document_version':d['version'],'name':d['name'],
                       'pages':[page for page in p['extraction']['pages'] if (d['id'],d['version'],page['page']) in selected_pages]}
                      for d,p in docs if any(x[0]==d['id'] for x in selected_pages)]
        context={'as_of':now(),'timezone':'UTC','entries':entries,'benefits':benefits,'documents':context_docs,'history':history,'case':None}
        request={'request_id':claimed['id'],'contract_version':VERSION,'question':message['content'],'context':context}
        validate('AnswerRequest',request)
        output=self.llm.answer(request); answer_check(output,context)
        with self.db.tx(write=True) as c:
            get(c,owner,'thread',thread_id)
            for d in context_docs:
                current,cp=get(c,owner,'document',d['document_id'])
                if current['version']!=d['document_version'] or current['status']!='ready' or cp.get('embedding_profile')!=self.hf.embedding_identity:
                    raise Failure('STALE_INPUT','A supporting document changed while the answer was generated.',409)
            for entry in entries:
                current,_=get(c,owner,'entry',entry['id'])
                if current['data_version']!=entry['data_version']:
                    raise Failure('STALE_INPUT','Entry facts changed while the answer was generated.',409)
            assistant={'id':uid(),'thread_id':thread_id,'role':'assistant','content':output['answer'],
                       'evidence_refs':output['evidence_refs'],'matched_benefit_ids':output['matched_benefit_ids'],
                       'questions':output['questions'],'next_actions':output['next_actions'],'created_at':now()}
            validate('ChatMessage',assistant)
            finish(c,claimed,result={'type':'answer','assistant_message':assistant})
            put(c,owner,'message',assistant,parent=thread_id)

def main():
    worker=Worker();last_cleanup=0
    from .maintenance import cleanup
    while True:
        if time.time()-last_cleanup>60:
            try:cleanup(worker.db,worker.storage)
            except Exception:pass  # Availability failures retry next tick; no source content is logged.
            last_cleanup=time.time()
        if not worker.once(): time.sleep(.5)

if __name__=='__main__': main()
