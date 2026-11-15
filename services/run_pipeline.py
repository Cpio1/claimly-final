"""Run the local integration UI, internal LLM API and durable worker; no inference on startup."""
import argparse
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
from services.envfile import load
from services.llm.app.config import ROOT


def child_environment(role, source=None):
    env=dict(source or os.environ)
    storage_keys={'DATABASE_URL','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','SUPABASE_BUCKET','LOCAL_STORAGE_DIR','LOCAL_DEV_STORAGE'}
    model_keys={'HF_TOKEN','HUGGING_FACE_HUB_TOKEN','MODEL_PROVIDER_API_KEY','MODEL_BASE_URL','HF_EMBEDDING_URL'}
    for key in (storage_keys if role=='llm' else model_keys if role=='backend' else set()):env.pop(key,None)
    return env

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',default='.env')
    parser.add_argument('--local',action='store_true',help='Explicit SQLite/private local storage development mode')
    parser.add_argument('--host',default='127.0.0.1')
    args=parser.parse_args();os.chdir(ROOT);load(args.env_file)
    if args.local:
        path=ROOT/'services/backend/.data';path.mkdir(parents=True,exist_ok=True)
        os.environ['LOCAL_DEV_STORAGE']='true'
        if not os.environ.get('DATABASE_URL'):os.environ['DATABASE_URL']='sqlite:///'+str(path/'claimly.sqlite')
        if not os.environ.get('LOCAL_STORAGE_DIR'):os.environ['LOCAL_STORAGE_DIR']=str(path/'originals')
        if not os.environ.get('LLM_SERVICE_TOKEN'):os.environ['LLM_SERVICE_TOKEN']=secrets.token_urlsafe(32)
    from services.backend.config import BackendSettings
    from services.backend.db import Database
    Database(BackendSettings.env()).setup()
    commands=[
        [sys.executable,'-B','-m','uvicorn','services.llm.app.main:app','--host','127.0.0.1','--port','8001','--no-access-log'],
        [sys.executable,'-B','-m','uvicorn','services.backend.api:app','--host',args.host,'--port','8000','--no-access-log'],
        [sys.executable,'-B','-m','services.backend.worker'],
    ]
    signal.signal(signal.SIGTERM,lambda signum,frame:(_ for _ in ()).throw(KeyboardInterrupt()))
    children=[]
    try:
        children=[subprocess.Popen(cmd,cwd=ROOT,env=child_environment(role)) for role,cmd in zip(['llm','backend','worker'],commands,strict=True)]
        print('Claimly upload/chat UI: http://localhost:8000',flush=True)
        print('Model calls require configured HF endpoint URLs and server token. No fixture fallback is enabled.',flush=True)
        while all(p.poll() is None for p in children):time.sleep(.5)
    except KeyboardInterrupt:pass
    finally:
        for process in children:
            if process.poll() is None:process.terminate()
        for process in children:
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()

if __name__=='__main__':main()
