"""Explicit HTTP mocks exercise integration; no paid inference or fabricated live-model score."""
from dataclasses import replace
import hashlib
from io import BytesIO
import json
from pathlib import Path
import time
import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from services.llm.app.config import Settings, ROOT
from services.llm.app.contracts import Failure, validate, answer_check
from services.llm.app.hf import HFClient, TokenBudget, checked_url
from services.llm.app.processing import Processor, DoclingParser
from services.llm.app.main import create_app as llm_app
from services.llm.rag.runtime import page_hash,chunks_for_pages
from services.backend.config import BackendSettings
from services.backend.db import Database,get,put,objects,encoded,now
from services.backend.storage import Storage
from services.backend.api import create_app
from services.backend.worker import Worker
from services.backend.review import approve

PDF=ROOT/'services/llm/parsing/fixtures/warranty.pdf'
class Budget:
    def embedding_count(self,text): return len(text.split())+2
    def chat_count(self,messages): return sum(len(m['content'].split()) for m in messages)+20

class NativeFixtureParser:
    """Test-only native PDF parser, injected explicitly. Production always uses DoclingParser."""
    def parse(self,data,metadata):
        return ([{'page':i,'text':p.extract_text(),'needs_review':False} for i,p in enumerate(PdfReader(BytesIO(data)).pages,1)],{'passed':True})

class Provider:
    def __init__(self): self.calls=[];self.mode='normal';self.answer_hook=None
    def __call__(self,request):
        data=json.loads(request.content);self.calls.append((request.url.path,data))
        if request.url.path.endswith('/embed'):
            vectors=[[1.,0.,0.] for _ in data['inputs']]
            if self.mode=='bad-vector': vectors=[[float('nan'),0.,0.] for _ in data['inputs']]
            if self.mode=='wrong-dimension':vectors=[[1.,0.] for _ in data['inputs']]
            return httpx.Response(200,json=vectors)
        if self.mode=='timeout': raise httpx.ReadTimeout('test only',request=request)
        if self.mode=='unavailable':return httpx.Response(503,json={'error':'test only'})
        if self.mode=='malformed':return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'not JSON'}}]})
        payload=json.loads(data['messages'][1]['content'].split('\n',1)[1]);system=data['messages'][0]['content']
        if 'Classify actual readable content only' in system and 'Extract only' not in system:
            page=payload['pages'][0];quote=page['text'].splitlines()[0]
            value={'outcome':'out_of_scope' if self.mode=='out-of-scope' else 'relevant','category':'warranty','reason':'Fixture source content.',
                'evidence_refs':[{'document_id':payload['document_id'],'document_version':payload['document_version'],'page':page['page'],'quote':quote}]}
        elif 'Extract only' in system:
            value={'category':'warranty','title':'Warranty','provider':None,'subject':None,'facts':{},'benefits':[],'review_flags':[]}
        else:
            docs=payload['context']['documents'];page=docs[0]['pages'][0]
            quote=page['text'].splitlines()[0]
            ref={'document_id':docs[0]['document_id'],'document_version':docs[0]['document_version'],'page':page['page'],'quote':quote}
            if self.mode=='bad-citation':ref['quote']='INVENTED TEXT THAT IS NOT IN SOURCE'
            value={'answer':'The document states: '+quote,'evidence_refs':[ref],'matched_benefit_ids':[],'questions':[],'next_actions':[]}
            if self.answer_hook:self.answer_hook()
        content='not JSON' if self.mode=='malformed' else json.dumps(value)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':content}}]})

class LocalLlm:
    """Cross the real internal API with contract validation, using explicit HTTP test transport."""
    def __init__(self,app,token): self.client=TestClient(app);self.token=token
    def extract(self,data,metadata,as_of):
        r=self.client.post('/internal/v1/extract',headers={'Authorization':'Bearer '+self.token,'X-Claimly-As-Of':as_of},
            files={'file':(metadata['filename'],data,metadata['mime_type'])},data={'metadata':json.dumps(metadata)})
        return self.result(r,'ExtractionResponse')
    def answer(self,request):
        r=self.client.post('/internal/v1/answer',json=request,headers={'Authorization':'Bearer '+self.token})
        return self.result(r,'AnswerResponse')
    def result(self,r,schema):
        value=r.json()
        if r.status_code>=400:
            validate('ErrorEnvelope',value);e=value['error'];raise Failure(e['code'],e['message'],r.status_code,e['retryable'])
        validate(schema,value);return value['data']

@pytest.fixture
def rig(tmp_path):
    settings=BackendSettings(database_url='sqlite:///'+str(tmp_path/'backend.sqlite'),local_storage=True,storage_dir=str(tmp_path/'sources'),service_token='test-service-token')
    db=Database(settings);db.setup();storage=Storage(settings)
    provider=Provider()
    hs=Settings(service_token='test-service-token',hf_token='test-hf-secret',embedding_url='https://embedding.test/embed',chat_url='https://chat.test/v1',
                embedding_revision='a'*40,chat_revision='b'*40,embedding_dimension=3,chunk_tokens=128)
    hf=HFClient(hs,transport=httpx.MockTransport(provider),budget=Budget())
    llm=LocalLlm(llm_app(hs,processor=Processor(hf,NativeFixtureParser())),hs.service_token)
    worker=Worker(settings,db=db,storage=storage,llm=llm,hf=hf)
    client=TestClient(create_app(settings,database=db,storage=storage))
    session=client.post('/api/v1/demo/sessions').json()['data']
    client.headers['X-Demo-Session']=session['session_token']
    return {'client':client,'session':session,'db':db,'storage':storage,'hf':hf,'provider':provider,'worker':worker,'llm':llm,'tmp':tmp_path}

def post(client,path,body,key='idempotency-0001'):
    return client.post(path,json=body,headers={'Idempotency-Key':key})

def upload(rig,key='upload-0001'):
    c=rig['client'];entry=post(c,'/api/v1/entries',{'title':'Pending document','category':'other'},'entry-'+key)
    assert entry.status_code==201,entry.text
    entry=entry.json()['data']
    result=c.post('/api/v1/documents',headers={'Idempotency-Key':key},data={'entry_id':entry['id']},files={'file':('warranty.pdf',PDF.read_bytes(),'application/pdf')})
    assert result.status_code==202,result.text
    validate('UploadAcceptedEnvelope',result.json())
    return result.json()['data']

def approve_uploaded(rig,result):
    assert rig['worker'].once()
    owner=rig['session']['id'];doc_id=result['document']['id']
    with rig['db'].tx() as c: doc,private=get(c,owner,'document',doc_id)
    assert doc['status']=='needs_review'
    approved=approve(rig['db'],rig['storage'],owner,doc_id,private['source_sha256'],private['pages_sha256'])
    assert rig['worker'].once()
    r=rig['client'].get('/api/v1/jobs/'+approved['id']);assert r.json()['data']['status']=='succeeded',r.text
    return doc_id

def question(rig,text='What does this warranty say?'):
    c=rig['client'];thread=post(c,'/api/v1/threads',{'scope':'vault','entry_id':None,'case_id':None,'document_ids':[]},'thread-0001').json()['data']
    response=post(c,'/api/v1/threads/'+thread['id']+'/messages',{'content':text,'purpose':'answer'},'message-0001')
    assert response.status_code==202,response.text
    return response.json()['data']

def test_full_upload_review_embedding_retrieval_chat_and_citation(rig):
    result=upload(rig);doc_id=approve_uploaded(rig,result);q=question(rig)
    assert rig['worker'].once()
    job=rig['client'].get('/api/v1/jobs/'+q['job']['id']).json()['data'];validate('Job',job)
    assert job['status']=='succeeded',job
    message=job['result']['assistant_message'];assert message['evidence_refs'][0]['document_id']==doc_id
    source=rig['client'].get('/api/v1/documents/'+doc_id+'/content')
    assert source.content==PDF.read_bytes()
    assert 'test-hf-secret' not in encoded(job)
    assert any(path.endswith('/embed') and not body['truncate'] for path,body in rig['provider'].calls)

def test_unreviewed_conversion_never_indexed_or_admitted(rig):
    upload(rig);rig['worker'].once()
    with rig['db'].tx() as c: assert c.execute('SELECT COUNT(*) AS n FROM claimly_vectors').fetchone()['n']==0
    assert rig['client'].get('/api/v1/entries').json()['data']==[]
    assert not any(path.endswith('/embed') for path,_ in rig['provider'].calls)

def test_review_hash_mismatch_cannot_activate(rig):
    result=upload(rig);rig['worker'].once()
    with pytest.raises(Failure,match='hashes'):
        approve(rig['db'],rig['storage'],rig['session']['id'],result['document']['id'],'wrong','wrong')

def test_out_of_scope_removes_original_and_draft_entry(rig):
    result=upload(rig);rig['provider'].mode='out-of-scope';rig['worker'].once()
    assert rig['client'].get('/api/v1/documents/'+result['document']['id']).status_code==404
    assert not list(Path(rig['storage'].settings.storage_dir).rglob('1'))
    assert rig['client'].get('/api/v1/entries').json()['data']==[]
    assert rig['client'].get('/api/v1/jobs/'+result['job']['id']).json()['data']['status']=='failed'

def test_two_sessions_cannot_read_content_jobs_threads_or_retrieve(rig):
    result=upload(rig);doc_id=approve_uploaded(rig,result)
    other=rig['client'].post('/api/v1/demo/sessions').json()['data']
    for path in ['/api/v1/documents/'+doc_id,'/api/v1/documents/'+doc_id+'/content','/api/v1/jobs/'+result['job']['id']]:
        assert rig['client'].get(path,headers={'X-Demo-Session':other['session_token']}).status_code==404
    rig['client'].headers['X-Demo-Session']=other['session_token']
    q=question(rig);rig['worker'].once();j=rig['client'].get('/api/v1/jobs/'+q['job']['id']).json()['data']
    assert j['status']=='succeeded' and j['result']['assistant_message']['evidence_refs']==[]
    assert 'no approved document' in j['result']['assistant_message']['content']

def test_idempotency_replay_and_conflicting_payload(rig):
    c=rig['client'];body={'title':'Pending document','category':'other'}
    first=post(c,'/api/v1/entries',body);second=post(c,'/api/v1/entries',body)
    assert first.json()==second.json()
    assert post(c,'/api/v1/entries',dict(body,title='different')).status_code==409

def test_upload_replay_does_not_duplicate_jobs_or_files(rig):
    first=upload(rig);second=upload(rig)
    assert first==second
    with rig['db'].tx() as c:assert c.execute('SELECT COUNT(*) AS n FROM claimly_jobs').fetchone()['n']==1

def test_deletion_removes_vectors_and_invalidates_old_citations(rig):
    result=upload(rig);doc_id=approve_uploaded(rig,result);q=question(rig);rig['worker'].once()
    assert rig['client'].delete('/api/v1/documents/'+doc_id).status_code==204
    with rig['db'].tx() as c:assert c.execute('SELECT COUNT(*) AS n FROM claimly_vectors').fetchone()['n']==0
    msgs=rig['client'].get('/api/v1/threads/'+q['message']['thread_id']+'/messages').json()['data']
    assert all(not m['evidence_refs'] for m in msgs)
    historical=rig['client'].get('/api/v1/jobs/'+q['job']['id']).json()['data']
    assert historical['status']=='stale' and historical['result'] is None
    assert rig['client'].get('/api/v1/documents/'+doc_id+'/content').status_code==404

def test_deleted_source_cannot_publish_inflight_answer(rig):
    result=upload(rig);doc_id=approve_uploaded(rig,result);q=question(rig)
    rig['provider'].answer_hook=lambda:rig['client'].delete('/api/v1/documents/'+doc_id)
    rig['worker'].once()
    job=rig['client'].get('/api/v1/jobs/'+q['job']['id']).json()['data']
    assert job['status'] in {'cancelled','stale'}
    assert job['result'] is None

def test_bad_quote_blocks_answer_after_single_repair(rig):
    approve_uploaded(rig,upload(rig));q=question(rig);rig['provider'].mode='bad-citation';rig['worker'].once()
    j=rig['client'].get('/api/v1/jobs/'+q['job']['id']).json()['data']
    assert j['status']=='failed' and j['error']['code']=='INVALID_LLM_OUTPUT'

def test_no_credentials_is_explicit_not_a_fake_answer(rig):
    hf=HFClient(replace(rig['hf'].settings,hf_token=''),budget=Budget())
    with pytest.raises(Failure) as e:hf.embed(['Warranty'])
    assert e.value.code=='AI_NOT_CONFIGURED'

@pytest.mark.parametrize('url',['https://huggingface.co/Qwen/Qwen3.8-27B','http://endpoint.test','https://token:secret@endpoint.test','https://endpoint.test?token=secret'])
def test_model_pages_and_unsafe_endpoint_configuration_rejected(url):
    with pytest.raises(Failure):checked_url(url)

def test_embedding_dimension_mismatch_blocks_atomic_index(rig):
    result=upload(rig);rig['worker'].once()
    with rig['db'].tx() as c:doc,p=get(c,rig['session']['id'],'document',result['document']['id'])
    approve(rig['db'],rig['storage'],rig['session']['id'],doc['id'],p['source_sha256'],p['pages_sha256'])
    rig['provider'].mode='wrong-dimension';rig['worker'].once()
    with rig['db'].tx() as c:
        assert c.execute('SELECT COUNT(*) AS n FROM claimly_vectors').fetchone()['n']==0
        assert get(c,rig['session']['id'],'document',doc['id'])[0]['status']!='ready'

def test_native_pdf_real_docling_conversion_and_public_dto(rig):
    settings=rig['hf'].settings
    processor=Processor(rig['hf'],DoclingParser(settings))
    metadata={'request_id':'real-conversion-test','contract_version':'2.0.0','document_id':'10000000-0000-4000-8000-000000000001',
              'document_version':1,'filename':'warranty.pdf','mime_type':'application/pdf'}
    output=processor.extract(PDF.read_bytes(),metadata,'2026-11-15')
    validate('ExtractionOutput',output)
    assert output['pages'] and 'warranty' in output['pages'][0]['text'].lower()
    assert 'quality:source_review_required' in output['review_flags'],output['review_flags']

def test_pinned_real_qwen_tokenizers_count_full_chat_template():
    budget=TokenBudget(Settings.env())
    count=budget.chat_count([{'role':'system','content':'Use only source evidence.'},{'role':'user','content':'When does this warranty expire?'}])
    assert count>20  # catches BatchEncoding key-count versus actual input_ids length
    assert budget.embedding_count('Warranty coverage lasts two years.')>5

def test_chunks_map_exactly_and_fit_real_qwen_tokenizer(rig):
    hf=HFClient(replace(rig['hf'].settings,chunk_tokens=64),budget=TokenBudget(Settings.env()))
    text=('Warranty coverage applies only to manufacturing defects. Accidental damage is excluded.\n'*50)
    pages=[{'page':1,'text':text,'needs_review':False}]
    chunks=chunks_for_pages('10000000-0000-4000-8000-000000000001',1,pages,hf)
    assert len(chunks)>1 and ''.join(c['source_text'] for c in chunks)==text
    for c in chunks:
        assert text[c['start']:c['end']]==c['source_text']
        assert hf.budget.embedding_count(c['contextualized_text'])<=64

def test_expired_session_isolated_and_validation_errors_follow_contract(rig):
    with rig['db'].tx(write=True) as c:c.execute('UPDATE claimly_sessions SET expires=? WHERE id=?',(time.time()-1,rig['session']['id']))
    r=rig['client'].get('/api/v1/entries');assert r.status_code==401;validate('ErrorEnvelope',r.json())
    assert r.json()['error']['code']=='DEMO_SESSION_EXPIRED'

def test_corrupt_oversized_and_over_page_limit_stop_before_model_calls(rig):
    c=rig['client'];entry=post(c,'/api/v1/entries',{'title':'Pending','category':'other'}).json()['data']
    writer=PdfWriter()
    for _ in range(26):writer.add_blank_page(width=100,height=100)
    out=BytesIO();writer.write(out)
    for name,data,mime in [('bad.pdf',b'%PDF-broken','application/pdf'),('huge.png',b'x'*(10*1024*1024+1),'image/png'),('many.pdf',out.getvalue(),'application/pdf')]:
        r=c.post('/api/v1/documents',headers={'Idempotency-Key':'invalid-'+name},data={'entry_id':entry['id']},files={'file':(name,data,mime)})
        assert r.status_code==422,r.text
        validate('ErrorEnvelope',r.json())
    assert rig['provider'].calls==[]

def test_internal_api_requires_separate_service_token(rig):
    r=rig['llm'].client.post('/internal/v1/answer',json={})
    assert r.status_code==401;validate('ErrorEnvelope',r.json())

def test_embedding_budget_does_not_truncate_or_call_provider(rig):
    with pytest.raises(Failure):rig['hf'].embed(['text '*200])
    assert rig['provider'].calls==[]


@pytest.mark.parametrize('mode,expected',[('timeout','LLM_UNAVAILABLE'),('unavailable','LLM_UNAVAILABLE'),('malformed','INVALID_LLM_OUTPUT')])
def test_provider_failures_are_explicit(rig,mode,expected):
    rig['provider'].mode=mode
    with pytest.raises(Failure) as exc:
        rig['hf'].structured({'type':'object'},'Return JSON.',{})
    assert exc.value.code==expected


def test_crashed_job_is_reclaimed_without_duplicate_active_work(rig):
    uploaded=upload(rig)
    first=rig['db'].claim(1);assert first['id']==uploaded['job']['id']
    assert rig['db'].claim(1) is None
    with rig['db'].tx(write=True) as c:c.execute('UPDATE claimly_jobs SET lease_until=0 WHERE id=?',(first['id'],))
    second=rig['db'].claim(1)
    assert second['id']==first['id'] and second['lease_token']!=first['lease_token']
    from services.backend.db import finish
    with pytest.raises(Failure):
        with rig['db'].tx(write=True) as c:finish(c,first,result=None)


def test_exhausted_crashed_job_becomes_terminal(rig):
    result=upload(rig)
    with rig['db'].tx(write=True) as c:c.execute("UPDATE claimly_jobs SET attempts=3,status='running',lease_until=0 WHERE id=?",(result['job']['id'],))
    assert rig['db'].claim() is None
    value=rig['client'].get('/api/v1/jobs/'+result['job']['id']).json()['data']
    assert value['status']=='failed' and value['error']['code']=='LLM_UNAVAILABLE'


def test_reindex_is_idempotent_and_does_not_rerun_conversion(rig):
    result=upload(rig);doc_id=approve_uploaded(rig,result)
    with rig['db'].tx() as c:first=c.execute('SELECT COUNT(*) AS n FROM claimly_vectors').fetchone()['n']
    before=len([p for p,_ in rig['provider'].calls if not p.endswith('/embed')])
    r=post(rig['client'],'/api/v1/documents/'+doc_id+'/analyze',{'force':False},'analyze-0001')
    assert r.status_code==202,r.text
    rig['worker'].once()
    with rig['db'].tx() as c:assert c.execute('SELECT COUNT(*) AS n FROM claimly_vectors').fetchone()['n']==first
    assert len([p for p,_ in rig['provider'].calls if not p.endswith('/embed')])==before


def test_http_body_limit_blocks_oversized_stream_before_provider(rig):
    r=rig['client'].post('/api/v1/documents',content=b'x',headers={'Content-Length':str(20*1024*1024),'Content-Type':'application/octet-stream'})
    assert r.status_code==413;validate('ErrorEnvelope',r.json())
    assert rig['provider'].calls==[]


def test_child_process_secrets_are_separated():
    from services.run_pipeline import child_environment
    source={'DATABASE_URL':'private-db','SUPABASE_SERVICE_ROLE_KEY':'private-storage','HF_TOKEN':'private-model','LLM_SERVICE_TOKEN':'internal'}
    llm=child_environment('llm',source);api=child_environment('backend',source);worker=child_environment('worker',source)
    assert 'DATABASE_URL' not in llm and 'SUPABASE_SERVICE_ROLE_KEY' not in llm
    assert 'HF_TOKEN' not in api
    assert worker['HF_TOKEN'] and worker['DATABASE_URL']


def test_quarantine_expiry_removes_unapproved_originals(rig):
    result=upload(rig);rig['worker'].once()
    with rig['db'].tx(write=True) as c:
        doc,p=get(c,rig['session']['id'],'document',result['document']['id'])
        doc['created_at']='2020-01-01T00:00:00Z';put(c,rig['session']['id'],'document',doc,p,doc['entry_id'])
    from services.backend.maintenance import cleanup
    assert cleanup(rig['db'],rig['storage'])==1
    assert rig['client'].get('/api/v1/documents/'+doc['id']).status_code==404


def test_failed_storage_deletion_still_blocks_source_and_old_answers(rig,monkeypatch):
    result=upload(rig);doc_id=approve_uploaded(rig,result);question_result=question(rig);rig['worker'].once()
    def unavailable(key):raise Failure('INTERNAL_ERROR','Storage unavailable.',503,True)
    monkeypatch.setattr(rig['storage'],'delete',unavailable)
    r=rig['client'].delete('/api/v1/documents/'+doc_id)
    assert r.status_code==503
    assert rig['client'].get('/api/v1/documents/'+doc_id+'/content').status_code==404
    historical=rig['client'].get('/api/v1/jobs/'+question_result['job']['id']).json()['data']
    assert historical['status']=='stale' and historical['result'] is None
    with rig['db'].tx() as c:assert c.execute('SELECT COUNT(*) AS n FROM claimly_vectors').fetchone()['n']==0


# Hallucination mitigation: a follow-up question cannot authorize unsupported assertions.
def hallucination_context():
    return {'documents':[{'document_id':'10000000-0000-4000-8000-000000000001','document_version':1,
                         'name':'Warranty','pages':[{'page':1,'text':'Accidental damage is excluded.','needs_review':False}]}],
            'benefits':[],'case':None}

def unsupported_answer():
    return {'answer':'You are guaranteed a $500 refund.','evidence_refs':[],'matched_benefit_ids':[],
            'questions':['When would you like the refund?'],'next_actions':[]}

def test_uncited_claim_cannot_bypass_validation_by_asking_a_question():
    with pytest.raises(Failure):answer_check(unsupported_answer(),hallucination_context())

def test_guard_replaces_unsupported_assertion_with_controlled_abstention():
    from services.llm.app.contracts import guard_answer,insufficient_answer
    value=unsupported_answer();guard_answer(value,hallucination_context())
    assert value==insufficient_answer(True) and '$500' not in value['answer']

def test_guard_clears_unsupported_benefit_matches_and_actions():
    from services.llm.app.contracts import guard_answer
    value=unsupported_answer();value['matched_benefit_ids']=['20000000-0000-4000-8000-000000000001']
    value['next_actions']=[{'type':'open_benefit','target_id':value['matched_benefit_ids'][0],'label':'Claim refund'}]
    guard_answer(value,hallucination_context())
    assert value['matched_benefit_ids']==[] and value['next_actions']==[]

def test_guard_preserves_cited_answer_and_still_rejects_fabricated_quotes():
    from services.llm.app.contracts import guard_answer
    value=unsupported_answer();value['answer']='Accidental damage is excluded.';value['questions']=[]
    value['evidence_refs']=[{'document_id':'10000000-0000-4000-8000-000000000001','document_version':1,'page':1,'quote':'Accidental damage is excluded.'}]
    expected=json.loads(json.dumps(value));guard_answer(value,hallucination_context());assert value==expected
    value['evidence_refs'][0]['quote']='The warranty guarantees a refund.'
    with pytest.raises(Failure):guard_answer(value,hallucination_context())

@pytest.mark.parametrize('page',[{'page':1,'text':'','needs_review':False},{'page':1,'text':'Unverified scan content.','needs_review':True}])
def test_no_usable_pages_abstains_without_model_call(rig,page):
    context=hallucination_context();context['documents'][0]['pages']=[page]
    result=Processor(rig['hf'],NativeFixtureParser()).answer({'context':context})
    assert result['evidence_refs']==[] and 'enough evidence' in result['answer']
    assert rig['provider'].calls==[]
