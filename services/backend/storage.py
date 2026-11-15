"""Original bytes are private and owned by Backend, never model repositories."""
from pathlib import Path
from urllib.parse import quote, urlsplit
import httpx
from services.llm.app.contracts import Failure

class Storage:
    def __init__(self, settings): self.settings=settings
    def _path(self,key):
        root=Path(self.settings.storage_dir).resolve(); path=(root/key).resolve()
        if root not in path.parents: raise Failure('FORBIDDEN','Invalid storage identity.',403)
        return path
    def _request(self,method,path,**kwargs):
        s=self.settings
        if urlsplit(s.supabase_url).scheme!='https' or not s.supabase_key:
            raise Failure('AI_NOT_CONFIGURED','Configure server-side private Supabase Storage credentials.',503)
        headers={'Authorization':'Bearer '+s.supabase_key,'apikey':s.supabase_key}
        headers.update(kwargs.pop('headers',{}))
        try:
            with httpx.Client(timeout=60,follow_redirects=False) as client:
                r=client.request(method,s.supabase_url.rstrip('/')+'/storage/v1/'+path,headers=headers,**kwargs)
        except httpx.HTTPError:
            raise Failure('LLM_UNAVAILABLE','Private storage is temporarily unavailable.',503,True) from None
        if not r.is_success:
            raise Failure('INTERNAL_ERROR','Private storage operation failed.',503,True)
        return r
    def key(self,key): return quote(self.settings.bucket,safe='')+'/'+quote(key,safe='/')
    def write(self,key,data,mime):
        if self.settings.local_storage:
            path=self._path(key); path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with path.open('xb') as f: f.write(data)
            path.chmod(0o600)
        else:
            bucket=self._request('GET','bucket/'+quote(self.settings.bucket,safe='')).json()
            if bucket.get('public') is not False:
                raise Failure('AI_NOT_CONFIGURED','The Claimly source bucket must be private.',503)
            self._request('POST','object/'+self.key(key),content=data,headers={'Content-Type':mime,'x-upsert':'false'})
    def read(self,key):
        if self.settings.local_storage:
            try: return self._path(key).read_bytes()
            except FileNotFoundError: raise Failure('NOT_FOUND','Original source is unavailable.',404) from None
        return self._request('GET','object/authenticated/'+self.key(key)).content
    def delete(self,key):
        if self.settings.local_storage: self._path(key).unlink(missing_ok=True)
        else: self._request('DELETE','object/'+quote(self.settings.bucket,safe=''),json={'prefixes':[key]})
