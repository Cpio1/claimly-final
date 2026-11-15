"""Upload/chat integration slice of the unchanged Backend contract."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import time
from urllib.parse import quote
from uuid import UUID
from fastapi import FastAPI, Request, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, FileResponse
from starlette.exceptions import HTTPException
from services.llm.app.contracts import Failure, VERSION, validate
from services.llm.parsing.ingestion_lab import validate_bytes, InvalidSource
from .config import BackendSettings
from .db import Database, get, put, objects, job, now, uid, sha, encoded
from .storage import Storage

WEB=Path(__file__).with_name('web')

def create_app(settings=None, *, database=None, storage=None):
    settings=settings or BackendSettings.env()
    db=database or Database(settings); blobs=storage or Storage(settings)
    app=FastAPI(title='Claimly upload and chat',docs_url=None,redoc_url=None)
    app.state.database=db; app.state.storage=blobs
    app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.frontend_origins.split(',') if x.strip()],
                       allow_methods=['GET','POST','PATCH','DELETE'],allow_headers=['X-Demo-Session','Idempotency-Key','Content-Type'])
    from services.llm.app.body_limit import BodyLimitMiddleware
    app.add_middleware(BodyLimitMiddleware)
    @app.middleware('http')
    async def request_headers(request,call_next):
        request.state.request_id=uid()
        response=await call_next(request)
        response.headers.update({'X-Contract-Version':VERSION,'X-Content-Type-Options':'nosniff',
                                 'Cache-Control':'no-store','Referrer-Policy':'same-origin',
                                 'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
        return response
    @app.exception_handler(Failure)
    async def fail(request,exc):
        return JSONResponse({'error':exc.dto(),'request_id':request.state.request_id},status_code=exc.status)
    @app.exception_handler(RequestValidationError)
    async def invalid(request,exc):
        return await fail(request,Failure('VALIDATION_ERROR','Invalid request fields.'))
    @app.exception_handler(HTTPException)
    async def http_error(request,exc):
        return await fail(request,Failure('NOT_FOUND' if exc.status_code==404 else 'VALIDATION_ERROR','Request could not be processed.',exc.status_code))
    @app.exception_handler(Exception)
    async def internal(request,exc):
        return await fail(request,Failure('INTERNAL_ERROR','The server could not complete this request.',500,True))
    def envelope(request,data): return {'data':data,'request_id':request.state.request_id}
    def owner(request):
        token=request.headers.get('X-Demo-Session','')
        if len(token)<43 or len(token)>128: raise Failure('DEMO_SESSION_REQUIRED','A demo session is required.',401)
        with db.tx() as c:
            row=c.execute('SELECT id,expires FROM claimly_sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if row is None: raise Failure('DEMO_SESSION_REQUIRED','A demo session is required.',401)
        if row['expires']<time.time(): raise Failure('DEMO_SESSION_EXPIRED','This demo session has expired. Start a new session.',401)
        return row['id']
    def identity(value):
        try: return str(UUID(value))
        except (ValueError,TypeError): raise Failure('VALIDATION_ERROR','Expected a valid object UUID.') from None
    def idem(c,request,session,payload,status,operation):
        key=request.headers.get('Idempotency-Key','')
        if not 8<=len(key)<=128: raise Failure('VALIDATION_ERROR','Idempotency-Key must contain 8 to 128 characters.')
        route=request.url.path; digest=sha(payload)
        c.lock_key(session+route+key)
        old=c.execute('SELECT * FROM claimly_idempotency WHERE session_id=? AND route=? AND key=?',(session,route,key)).fetchone()
        if old:
            if old['request_hash']!=digest: raise Failure('CONFLICT','This idempotency key was used for different input.',409)
            return JSONResponse(json.loads(old['response']),status_code=old['status'])
        result=envelope(request,operation())
        c.execute('INSERT INTO claimly_idempotency VALUES(?,?,?,?,?,?)',(session,route,key,digest,encoded(result),status))
        return JSONResponse(result,status_code=status)
    def listing(request,items,cursor,limit):
        if cursor:
            indexes=[i for i,x in enumerate(items) if x['id']==cursor]
            if not indexes: raise Failure('VALIDATION_ERROR','The pagination cursor is not valid for this collection.')
            items=items[indexes[0]+1:]
        page=items[:limit]
        return {'data':page,'next_cursor':page[-1]['id'] if len(items)>limit else None,'request_id':request.state.request_id}
    @app.get('/')
    def index(): return FileResponse(WEB/'index.html')
    @app.get('/app.js')
    def script(): return FileResponse(WEB/'app.js',media_type='application/javascript')
    @app.get('/style.css')
    def style(): return FileResponse(WEB/'style.css',media_type='text/css')
    @app.get('/health')
    def health(request:Request):
        return envelope(request,{'status':'ok' if settings.database_url else 'degraded','service':'backend','contract_version':VERSION})
    @app.post('/api/v1/demo/sessions')
    def session(request:Request):
        creator=hashlib.sha256((request.client.host if request.client else 'unknown').encode()).hexdigest()
        token=secrets.token_urlsafe(32); session_id=uid(); stamp=time.time()
        with db.tx(write=True) as c:
            c.lock_key('session-rate:'+creator)
            count=c.execute('SELECT COUNT(*) AS n FROM claimly_sessions WHERE creator_hash=? AND created>?',(creator,stamp-3600)).fetchone()['n']
            if count>=20: raise Failure('RATE_LIMITED','Too many demo sessions. Try again later.',429,True)
            c.execute('INSERT INTO claimly_sessions VALUES(?,?,?,?,?)',(session_id,hashlib.sha256(token.encode()).hexdigest(),stamp+settings.session_hours*3600,creator,stamp))
        data={'id':session_id,'session_token':token,'expires_at':datetime.fromtimestamp(stamp+settings.session_hours*3600,timezone.utc).isoformat().replace('+00:00','Z')}
        validate('DemoSession',data)
        return JSONResponse(envelope(request,data),status_code=201)
    @app.post('/api/v1/entries')
    def entry_create(request:Request,body:dict):
        session=owner(request); validate('EntryCreate',body)
        with db.tx(write=True) as c:
            def operation():
                entry={'id':uid(),'title':body['title'],'category':body['category'],'provider':body.get('provider'),
                       'subject':body.get('subject'),'facts':{},'data_version':1,'document_ids':[],'benefit_ids':[],
                       'created_at':now(),'updated_at':now()}
                validate('Entry',entry); put(c,session,'entry',entry,{'admitted':False})
                return entry
            return idem(c,request,session,body,201,operation)
    @app.get('/api/v1/entries')
    def entries(request:Request,cursor:str|None=None,limit:int=Query(25,ge=1,le=100)):
        session=owner(request)
        with db.tx() as c: items=[b for b,p in objects(c,session,'entry') if p.get('admitted')]
        return listing(request,items,cursor,limit)
    @app.get('/api/v1/entries/{entry_id}')
    def entry_get(entry_id:str,request:Request):
        session=owner(request)
        with db.tx() as c: body,_=get(c,session,'entry',identity(entry_id))
        return envelope(request,body)
    @app.post('/api/v1/documents')
    async def upload(request:Request):
        session=owner(request)
        try:
            async with request.form(max_files=1,max_fields=1,max_part_size=10*1024*1024+1) as form:
                entry_id=identity(form['entry_id']); file=form['file']
                data=await file.read(10*1024*1024+1)
                filename=Path(file.filename or 'upload').name[:255]
                source=validate_bytes(data,filename,declared_mime=file.content_type)
        except Failure: raise
        except InvalidSource as exc:
            raise Failure('FILE_TOO_LARGE' if len(data)>10*1024*1024 else 'VALIDATION_ERROR',str(exc)) from None
        except (KeyError,TypeError,AttributeError):
            raise Failure('VALIDATION_ERROR','Expected multipart entry_id and PDF/JPEG/PNG file.') from None
        created=[]
        try:
            with db.tx(write=True) as c:
                entry,private=get(c,session,'entry',entry_id)
                def operation():
                    doc={'id':uid(),'entry_id':entry_id,'name':filename,'mime_type':source.mime_type,'version':1,
                         'status':'uploaded','page_count':source.page_count,'facts':{},'review_flags':[], 'created_at':now()}
                    key=session+'/'+doc['id']+'/1'; blobs.write(key,data,source.mime_type); created.append(key)
                    put(c,session,'document',doc,{'source_sha256':source.sha256,'storage_key':key},entry_id)
                    entry['document_ids'].append(doc['id']); entry['updated_at']=now()
                    put(c,session,'entry',entry,private)
                    queued=job(c,session,'extract',doc['id'],{'document_id':doc['id'],'version':1})
                    return {'document':doc,'job':queued}
                return idem(c,request,session,{'entry_id':entry_id,'source_sha':source.sha256,'filename':filename,'mime':source.mime_type},202,operation)
        except Exception:
            for key in created: blobs.delete(key)
            raise
    @app.get('/api/v1/documents/{document_id}')
    def document_get(document_id:str,request:Request):
        session=owner(request)
        with db.tx() as c: doc,private=get(c,session,'document',identity(document_id))
        if private.get('deleted'):raise Failure('NOT_FOUND','Document was deleted.',404)
        return envelope(request,doc)
    @app.get('/api/v1/documents/{document_id}/content')
    def content(document_id:str,request:Request):
        session=owner(request)
        with db.tx() as c: doc,private=get(c,session,'document',identity(document_id))
        if private.get('deleted'):raise Failure('NOT_FOUND','Document was deleted.',404)
        return Response(blobs.read(private['storage_key']),media_type=doc['mime_type'],
                        headers={'Content-Disposition':"inline; filename*=UTF-8''"+quote(doc['name'],safe='')})
    @app.post('/api/v1/documents/{document_id}/analyze')
    def analyze(document_id:str,request:Request,body:dict):
        session=owner(request); validate('AnalyzeRequest',body)
        with db.tx(write=True) as c:
            doc,private=get(c,session,'document',identity(document_id))
            if private.get('deleted'):raise Failure('NOT_FOUND','Document was deleted.',404)
            def operation():
                doc['status']='processing'; put(c,session,'document',doc,private,doc['entry_id'])
                return job(c,session,'extract',doc['id'],{'document_id':doc['id'],'version':doc['version']})
            return idem(c,request,session,body,202,operation)
    @app.delete('/api/v1/documents/{document_id}')
    def remove(document_id:str,request:Request):
        session=owner(request)
        with db.tx(write=True) as c:
            doc,private=get(c,session,'document',identity(document_id))
            # Make every derived source inaccessible in the same state transaction.
            for row in c.execute("SELECT * FROM claimly_jobs WHERE session_id=?",(session,)).fetchall():
                jb=json.loads(row['body']); payload=json.loads(row['payload'])
                refs=(jb.get('result') or {}).get('assistant_message',{}).get('evidence_refs',[])
                historical=any(r['document_id']==doc['id'] for r in refs) or ((jb.get('result') or {}).get('document_id')==doc['id'])
                active=jb['status'] in {'queued','running'}
                if historical or (active and (row['kind']=='answer' or payload.get('document_id')==doc['id'])):
                    jb.update(status='stale' if historical else 'cancelled',result=None,error=None,updated_at=now())
                    c.execute('UPDATE claimly_jobs SET status=?,body=?,lease_token=NULL WHERE id=? AND session_id=?',(jb['status'],encoded(jb),jb['id'],session))
            for message,mp in objects(c,session,'message'):
                if any(r['document_id']==doc['id'] for r in message['evidence_refs']):
                    message.update(content='This response is unavailable because a supporting source was deleted.',evidence_refs=[],matched_benefit_ids=[],next_actions=[],questions=[])
                    put(c,session,'message',message,mp,message['thread_id'])
            for benefit,bp in objects(c,session,'benefit',doc['entry_id']):
                if bp.get('document_id')==doc['id']:
                    c.execute('DELETE FROM claimly_objects WHERE id=? AND session_id=?',(benefit['id'],session))
            private['deleted']=True;doc['status']='failed'
            put(c,session,'document',doc,private,doc['entry_id'])
            c.execute('DELETE FROM claimly_vectors WHERE document_id=? AND session_id=?',(doc['id'],session))
            entry,ep=get(c,session,'entry',doc['entry_id'])
            remaining=[(d,p) for d,p in objects(c,session,'document',doc['entry_id']) if d['id']!=doc['id'] and not p.get('deleted')]
            entry['document_ids']=[d['id'] for d,_ in remaining]
            entry['benefit_ids']=[b['id'] for b,_ in objects(c,session,'benefit',entry['id'])]
            entry['facts']={k:v for d,p in remaining if d['status']=='ready' for k,v in p.get('extraction',{}).get('facts',{}).items()}
            ep['admitted']=any(d['status']=='ready' for d,_ in remaining)
            entry['data_version']+=1; entry['updated_at']=now(); put(c,session,'entry',entry,ep)
        # A committed tombstone makes the source inaccessible even if private-storage cleanup fails.
        blobs.delete(private['storage_key'])
        with db.tx(write=True) as c:
            c.execute('DELETE FROM claimly_objects WHERE id=? AND session_id=?',(doc['id'],session))
        return Response(status_code=204)
    @app.get('/api/v1/benefits')
    def benefits(request:Request,entry_id:str|None=None,cursor:str|None=None,limit:int=Query(25,ge=1,le=100)):
        session=owner(request)
        with db.tx() as c:
            if entry_id: get(c,session,'entry',identity(entry_id))
            items=[b for b,_ in objects(c,session,'benefit',entry_id)]
        return listing(request,items,cursor,limit)
    @app.post('/api/v1/threads')
    def thread_create(request:Request,body:dict):
        session=owner(request); validate('ThreadCreate',body)
        if body['scope']=='case': raise Failure('VALIDATION_ERROR','Case workflows are outside this upload/chat integration slice.')
        with db.tx(write=True) as c:
            if body['scope']=='entry':
                if not body['entry_id']: raise Failure('VALIDATION_ERROR','Entry threads require entry_id.')
                get(c,session,'entry',body['entry_id'])
            elif body['entry_id'] is not None or body['case_id'] is not None:
                raise Failure('VALIDATION_ERROR','Vault threads cannot specify entry_id or case_id.')
            for doc_id in body['document_ids']:
                d,_=get(c,session,'document',doc_id)
                if body['scope']=='entry' and d['entry_id']!=body['entry_id']:
                    raise Failure('VALIDATION_ERROR','Thread documents must belong to the selected entry.')
            def operation():
                thread=dict(body,id=uid(),created_at=now()); put(c,session,'thread',thread,parent=body['entry_id'])
                return thread
            return idem(c,request,session,body,201,operation)
    @app.get('/api/v1/threads')
    def threads(request:Request,scope:str|None=None,entry_id:str|None=None,case_id:str|None=None,cursor:str|None=None,limit:int=Query(25,ge=1,le=100)):
        session=owner(request)
        with db.tx() as c: items=[t for t,_ in objects(c,session,'thread') if (not scope or t['scope']==scope) and (not entry_id or t['entry_id']==entry_id) and (not case_id or t['case_id']==case_id)]
        return listing(request,items,cursor,limit)
    @app.post('/api/v1/threads/{thread_id}/messages')
    def send(thread_id:str,request:Request,body:dict):
        session=owner(request); validate('MessageCreate',body)
        if body['purpose']!='answer' or not body['content'].strip() or len(body['content'])>12000:
            raise Failure('VALIDATION_ERROR','Provide an answer question of 1 to 12,000 characters.')
        with db.tx(write=True) as c:
            thread,_=get(c,session,'thread',identity(thread_id))
            def operation():
                message={'id':uid(),'thread_id':thread['id'],'role':'user','content':body['content'],
                         'evidence_refs':[],'matched_benefit_ids':[],'questions':[],'next_actions':[],'created_at':now()}
                put(c,session,'message',message,parent=thread['id'])
                queued=job(c,session,'answer',thread['id'],{'thread_id':thread['id'],'message_id':message['id']})
                return {'message':message,'job':queued}
            return idem(c,request,session,body,202,operation)
    @app.get('/api/v1/threads/{thread_id}/messages')
    def messages(thread_id:str,request:Request,cursor:str|None=None,limit:int=Query(25,ge=1,le=100)):
        session=owner(request)
        with db.tx() as c:
            get(c,session,'thread',identity(thread_id))
            items=[m for m,_ in objects(c,session,'message',thread_id)]
        return listing(request,items,cursor,limit)
    @app.get('/api/v1/jobs/{job_id}')
    def get_job(job_id:str,request:Request):
        session=owner(request)
        with db.tx() as c:
            row=c.execute('SELECT body FROM claimly_jobs WHERE id=? AND session_id=?',(identity(job_id),session)).fetchone()
        if row is None: raise Failure('NOT_FOUND','Job not found in this session.',404)
        return envelope(request,json.loads(row['body']))
    return app

app=create_app()
