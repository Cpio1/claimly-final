"""Public errors contain curated messages, never external exception details."""

from uuid import uuid4

from fastapi.responses import JSONResponse

CONTRACT_VERSION = "2.0.0"


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.status, self.code, self.message, self.retryable = status, code, message, retryable

    def dto(self) -> dict:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


def as_api_error(error) -> ApiError:
    """Map the shared LLM-package Failure (same public fields) onto ApiError."""
    if isinstance(error, ApiError):
        return error
    return ApiError(getattr(error, "status", 500), getattr(error, "code", "INTERNAL_ERROR"),
                    getattr(error, "message", "The server could not complete this request."),
                    bool(getattr(error, "retryable", False)))


def error_response(error: ApiError, request_id: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content={"error": error.dto(), "request_id": request_id or str(uuid4())},
        headers={"X-Contract-Version": CONTRACT_VERSION, **({"Retry-After": "60"} if error.status == 429 else {})},
    )


def not_found(what: str = "Object") -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{what} not found in this demo session.")


def invalid(message: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message)


def conflict(message: str = "The resource changed. Reload the latest version.") -> ApiError:
    return ApiError(409, "CONFLICT", message)
