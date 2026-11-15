"""FastAPI entry point for the merged Claimly product Backend (isolated anonymous demo sessions)."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException

from app import contract
from app.db import Database
from app.errors import CONTRACT_VERSION, ApiError, as_api_error, error_response
from app.routes import build_router
from app.settings import ConfigurationError, Settings
from app.storage import make_storage
from app.support import Api, envelope
from app.upload_guard import UploadGuard

LOG = logging.getLogger("claimly.backend")


def create_app(settings: Settings | None = None, *, database: Database | None = None, storage=None) -> FastAPI:
    settings = settings or Settings.from_env()
    contract.configure(settings)
    db = database or Database(settings)
    api = Api(settings, db, (lambda: storage) if storage is not None else (lambda: make_storage(settings)))
    app = FastAPI(title="Claimly Backend API", version=CONTRACT_VERSION, docs_url=None, redoc_url=None, openapi_url=None,
                  description="Anonymous isolated demo sessions; no login. Do not upload real personal documents in a demo.")
    app.state.api = api
    app.include_router(build_router(api))
    app.add_middleware(UploadGuard)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.frontend_origins),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Accept", "Content-Type", "Idempotency-Key", "X-Demo-Session"],
        expose_headers=["X-Contract-Version", "X-Request-Id", "Retry-After"],
        allow_credentials=False,
        max_age=600,
    )

    @app.middleware("http")
    async def request_headers(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers.update({
            "X-Contract-Version": CONTRACT_VERSION, "X-Request-Id": request.state.request_id,
            "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
        })
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    def rid(request: Request) -> str:
        return getattr(request.state, "request_id", None) or str(uuid4())

    @app.exception_handler(ApiError)
    async def api_error(request, error):
        return error_response(error, rid(request))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return error_response(ApiError(422, "VALIDATION_ERROR", "Invalid request fields."), rid(request))

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        code = "NOT_FOUND" if error.status_code == 404 else "VALIDATION_ERROR"
        return error_response(ApiError(error.status_code, code, "Request could not be handled."), rid(request))

    @app.exception_handler(ConfigurationError)
    async def configuration_error(request, error):
        return error_response(ApiError(503, "INTERNAL_ERROR", "Backend configuration is missing or invalid.", True), rid(request))

    @app.exception_handler(Exception)
    async def internal(request, error):
        if hasattr(error, "code") and hasattr(error, "status") and hasattr(error, "retryable"):
            return error_response(as_api_error(error), rid(request))
        LOG.error("unhandled_error type=%s request_id=%s", type(error).__name__, rid(request))  # no content or secrets
        return error_response(ApiError(500, "INTERNAL_ERROR", "The server could not complete this request.", True), rid(request))

    readiness = {"at": 0.0, "ok": False}

    @app.get("/health")
    def health(request: Request):
        """Liveness plus cached dependency readiness (database schema, storage configuration)."""
        if time.monotonic() - readiness["at"] > 15:
            ok = True
            try:
                with db.tx() as c:
                    ok = c.execute("SELECT 1 AS ok FROM claimly.schema_migrations WHERE version='0004'").fetchone() is not None
                api.storage  # validates Storage configuration without a network call
            except Exception:
                ok = False
            readiness.update(at=time.monotonic(), ok=ok)
        data = {"status": "ok" if readiness["ok"] else "degraded", "service": "backend", "contract_version": CONTRACT_VERSION}
        return envelope(request, data)

    return app


def _default_app():
    try:
        return create_app()
    except ConfigurationError as error:
        # Keep the process up with an explicit degraded state instead of a crash loop.
        LOG.error("configuration_error %s", error)
        fallback = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @fallback.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
        def unavailable(path: str):
            return error_response(ApiError(503, "INTERNAL_ERROR", "Backend configuration is missing or invalid.", True))
        return fallback


app = _default_app()
