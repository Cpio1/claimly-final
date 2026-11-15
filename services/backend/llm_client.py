import httpx
from services.llm.app.contracts import Failure, validate, VERSION

class HttpLlmClient:
    def __init__(self,settings,transport=None): self.settings,self.transport=settings,transport
    def _post(self,path,**kwargs):
        if not self.settings.service_token:
            raise Failure('AI_NOT_CONFIGURED','Set the server-side LLM_SERVICE_TOKEN.',503)
        headers={'Authorization':'Bearer '+self.settings.service_token}
        headers.update(kwargs.pop('headers',{}))
        try:
            with httpx.Client(timeout=600,transport=self.transport,follow_redirects=False) as client:
                r=client.post(self.settings.llm_url.rstrip('/')+path,headers=headers,**kwargs)
        except httpx.HTTPError:
            raise Failure('LLM_UNAVAILABLE','The internal LLM service is unavailable.',503,True) from None
        try: value=r.json()
        except ValueError: raise Failure('INVALID_LLM_OUTPUT','The internal LLM service returned invalid JSON.',502) from None
        if not r.is_success:
            validate('ErrorEnvelope',value,output=True)
            e=value['error']; raise Failure(e['code'],e['message'],r.status_code,e['retryable'])
        return value
    def extract(self,data,metadata,as_of):
        r=self._post('/internal/v1/extract',data={'metadata':__import__('json').dumps(metadata)},
               files={'file':(metadata['filename'],data,metadata['mime_type'])},headers={'X-Claimly-As-Of':as_of})
        validate('ExtractionResponse',r,output=True)
        if r['request_id']!=metadata['request_id']: raise Failure('INVALID_LLM_OUTPUT','Extraction request identity mismatch.',502)
        return r['data']
    def answer(self,request):
        r=self._post('/internal/v1/answer',json=request)
        validate('AnswerResponse',r,output=True)
        if r['request_id']!=request['request_id']: raise Failure('INVALID_LLM_OUTPUT','Answer request identity mismatch.',502)
        return r['data']
