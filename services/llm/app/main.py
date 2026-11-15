"""Contract-compatible stateless internal extract/answer API."""
import hmac
import json
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from .config import Settings
from .contracts import Failure, VERSION, validate
from .hf import HFClient
from .processing import Processor, DoclingParser

def create_app(settings=None, *, processor=None):
    settings = settings or Settings.env()
    app = FastAPI(title='Claimly internal LLM', docs_url=None, redoc_url=None)
    engine = processor or Processor(HFClient(settings), DoclingParser(settings))
    from services.llm.app.body_limit import BodyLimitMiddleware
    app.add_middleware(BodyLimitMiddleware)
    @app.middleware('http')
    async def headers(request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers['X-Contract-Version'] = VERSION
        return response
    @app.exception_handler(Failure)
    async def failure(request, exc):
        return JSONResponse({'error':exc.dto(),'request_id':request.state.request_id},status_code=exc.status)
    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return await failure(request, Failure("VALIDATION_ERROR", "Invalid request fields."))
    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return await failure(request, Failure("NOT_FOUND" if exc.status_code == 404 else "VALIDATION_ERROR", "Request could not be processed.", exc.status_code))
    @app.exception_handler(Exception)
    async def internal(request, exc):
        return await failure(request, Failure("INTERNAL_ERROR", "The LLM service could not complete this request.", 500))
    def authorize(request):
        expected = 'Bearer ' + settings.service_token
        if not settings.service_token or not hmac.compare_digest(request.headers.get('Authorization',''), expected):
            raise Failure('UNAUTHORIZED','An internal service token is required.',401)
    @app.get('/health')
    def health(request: Request):
        return {'data':{'status':'ok' if settings.hf_token and settings.chat_url else 'degraded',
                        'service':'llm','contract_version':VERSION},'request_id':request.state.request_id}
    @app.post('/internal/v1/extract')
    async def extract(request: Request):
        authorize(request)
        try:
            async with request.form(max_files=1, max_fields=1, max_part_size=10*1024*1024+1) as form:
                metadata = json.loads(form['metadata'])
                validate('ExtractRequest', metadata)
                file = form['file']
                data = await file.read(10*1024*1024+1)
        except Failure: raise
        except (KeyError, ValueError, TypeError, AttributeError):
            raise Failure('VALIDATION_ERROR','Expected multipart file and valid metadata JSON.') from None
        from starlette.concurrency import run_in_threadpool
        value = await run_in_threadpool(engine.extract, data, metadata, request.headers.get('X-Claimly-As-Of'))
        validate('ExtractionOutput',value,output=True)
        return {'data':value,'request_id':metadata['request_id'],'contract_version':VERSION}
    @app.post('/internal/v1/answer')
    def answer(request: Request, body: dict):
        authorize(request)
        validate('AnswerRequest',body)
        value = engine.answer(body)
        return {'data':value,'request_id':body['request_id'],'contract_version':VERSION}
    return app

app = create_app()
