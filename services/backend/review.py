"""Trusted operator source review, bound to original bytes and canonical pages. No browser admin token."""
import argparse
import hashlib
import json
from .config import BackendSettings
from .db import Database,get,put,job,now
from .storage import Storage
from services.llm.app.contracts import Failure
from services.llm.rag.runtime import page_hash

def approve(db,storage,owner,document_id,source_sha,pages_sha):
    with db.tx(write=True) as c:
        doc,private=get(c,owner,'document',document_id)
        output=private.get('extraction')
        if private.get('deleted') or output is None or 'quality:blocked' in output['review_flags']:
            raise Failure('VALIDATION_ERROR','This conversion is incomplete or semantically unresolved; quality review cannot override its gate.')
        if source_sha!=private['source_sha256'] or hashlib.sha256(storage.read(private['storage_key'])).hexdigest()!=source_sha or page_hash(output['pages'])!=pages_sha:
            raise Failure('STALE_INPUT','Review hashes do not match the current original and canonical pages.',409)
        private['quality_review']={'source_sha256':source_sha,'pages_sha256':pages_sha,'approved_at':now()}
        doc['status']='processing'; put(c,owner,'document',doc,private,doc['entry_id'])
        return job(c,owner,'extract',document_id,{'document_id':document_id,'version':doc['version']})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('document_id',nargs='?'); p.add_argument('--session-id')
    p.add_argument('--list',action='store_true');p.add_argument('--local',action='store_true');p.add_argument('--env-file',default='.env')
    p.add_argument('--approve',action='store_true');p.add_argument('--source-sha');p.add_argument('--pages-sha')
    args=p.parse_args()
    from services.envfile import load
    from services.llm.app.config import ROOT
    import os
    load(args.env_file)
    if args.local:
        os.environ['LOCAL_DEV_STORAGE']='true'
        if not os.environ.get('DATABASE_URL'):os.environ['DATABASE_URL']='sqlite:///'+str(ROOT/'services/backend/.data/claimly.sqlite')
    settings=BackendSettings.env(); db=Database(settings); storage=Storage(settings)
    if args.list:
        with db.tx() as c:
            for row in c.execute("SELECT id,session_id,body FROM claimly_objects WHERE kind='document'").fetchall():
                body=json.loads(row['body'])
                print(json.dumps({'document_id':row['id'],'session_id':row['session_id'],'status':body['status']}))
        return
    if not args.document_id or not args.session_id:p.error('Specify document_id and --session-id, or use --list.')
    if args.approve:
        if not args.source_sha or not args.pages_sha: p.error('Approval requires both hashes after visual/source review.')
        result=approve(db,storage,args.session_id,args.document_id,args.source_sha,args.pages_sha)
        print('Approved exact source/conversion; indexing job:',result['id'])
    else:
        with db.tx() as c: doc,private=get(c,args.session_id,'document',args.document_id)
        print(json.dumps({'document':doc,'source_sha256':private['source_sha256'],'pages_sha256':private.get('pages_sha256'),
                          'extraction':private.get('extraction')},ensure_ascii=False,indent=2))
        print('Compare canonical pages to the original in the authenticated UI before approving these hashes.')

if __name__=='__main__':main()
