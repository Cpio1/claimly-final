from dataclasses import dataclass
import os
from services.llm.app.config import ROOT

@dataclass(frozen=True)
class BackendSettings:
    database_url: str = ''
    local_storage: bool = False
    storage_dir: str = str(ROOT/'services/backend/.data/originals')
    supabase_url: str = ''
    supabase_key: str = ''
    bucket: str = 'claimly-private'
    llm_url: str = 'http://127.0.0.1:8001'
    service_token: str = ''
    session_hours: int = 168
    lease_seconds: int = 1200
    frontend_origins: str = 'http://localhost:8000'
    @classmethod
    def env(cls):
        return cls(database_url=os.getenv('DATABASE_URL',''), local_storage=os.getenv('LOCAL_DEV_STORAGE','false').lower()=='true',
                   storage_dir=os.getenv('LOCAL_STORAGE_DIR',str(ROOT/'services/backend/.data/originals')),
                   supabase_url=os.getenv('SUPABASE_URL',''),supabase_key=os.getenv('SUPABASE_SERVICE_ROLE_KEY',''),
                   bucket=os.getenv('SUPABASE_BUCKET','claimly-private'),llm_url=os.getenv('LLM_BASE_URL','http://127.0.0.1:8001'),
                   service_token=os.getenv('LLM_SERVICE_TOKEN',''),session_hours=int(os.getenv('DEMO_SESSION_TTL_HOURS','168')),
                   frontend_origins=os.getenv('FRONTEND_ORIGINS','http://localhost:8000'))
