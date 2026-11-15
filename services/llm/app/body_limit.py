"""Bound the actual request stream, including chunked uploads, before multipart spooling grows."""
import json
from .contracts import Failure,VERSION

class BodyLimitMiddleware:
    def __init__(self,app,limit=10*1024*1024+65536):self.app,self.limit=app,limit
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[]));length=headers.get(b'content-length',b'0')
        try:oversized=int(length)>self.limit
        except ValueError:oversized=True
        if oversized:
            body=json.dumps({'error':{'code':'FILE_TOO_LARGE','message':'Request exceeds the upload size limit.','retryable':False},'request_id':scope.get('state',{}).get('request_id','request-too-large')}).encode()
            await send({'type':'http.response.start','status':413,'headers':[(b'content-type',b'application/json'),(b'x-contract-version',VERSION.encode())]})
            await send({'type':'http.response.body','body':body});return
        count=0
        async def limited_receive():
            nonlocal count
            message=await receive()
            if message['type']=='http.request':
                count+=len(message.get('body',b''))
                if count>self.limit:raise Failure('FILE_TOO_LARGE','Request exceeds the upload size limit.',413)
            return message
        await self.app(scope,limited_receive,send)
