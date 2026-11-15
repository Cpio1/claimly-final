"""Explicit provider configuration check; --live performs two small paid inference requests."""
import argparse
import json
from pathlib import Path
from services.envfile import load
from services.llm.app.config import Settings,ROOT
from services.llm.app.hf import HFClient,checked_url
from services.llm.app.contracts import Failure

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--env-file',default='.env');p.add_argument('--live',action='store_true');args=p.parse_args()
    load(args.env_file);s=Settings.env();client=HFClient(s)
    try:
        checked_url(s.embedding_url);checked_url(s.chat_url);client.embedding_identity
        if not s.hf_token:raise Failure('AI_NOT_CONFIGURED','Set HF_TOKEN in the server environment.',503)
        lock=json.loads((ROOT/'services/llm/hf-models.lock.json').read_text())
        for role,path,revision in [('embedding',Path(s.embedding_tokenizer),s.embedding_revision),('chat',Path(s.chat_tokenizer),s.chat_revision)]:
            import hashlib
            for name,digest in lock[role]['files'].items():
                if hashlib.sha256((path/name).read_bytes()).hexdigest()!=digest:raise Failure('AI_NOT_CONFIGURED','Tokenizer integrity check failed.',503)
            if revision!=lock[role]['revision']:raise Failure('AI_NOT_CONFIGURED','Tokenizer revision differs from the model lock.',503)
        print('Local tokenizer hashes, pinned revisions and endpoint URL format: valid.')
        if not args.live:
            print('No live inference performed. Use --live explicitly to test endpoint access and responses.');return
        vector=client.embed(['Fictional test warranty: coverage lasts two years.'])[0]
        schema={'type':'object','properties':{'status':{'const':'ok'}},'required':['status'],'additionalProperties':False}
        value=client.structured(schema,'This is a connection test. Return status=ok.',{})
        print(json.dumps({'embedding_dimension':len(vector),'chat':value,'live_inference':True}))
    except (Failure,FileNotFoundError,KeyError) as exc:
        print('NOT CONFIGURED: '+(exc.message if isinstance(exc,Failure) else 'Prefetch the model tokenizer/config assets.'))
        raise SystemExit(2)

if __name__=='__main__':main()
