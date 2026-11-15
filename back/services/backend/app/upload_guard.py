"""Bound request bodies before JSON/multipart parsing and bound concurrent uploads per process."""

import os
from threading import BoundedSemaphore

import anyio

from app.errors import ApiError, error_response
from app.file_validation import MAX_FILE_BYTES

JSON_LIMIT = 256 * 1024
UPLOAD_PATH = "/api/v1/documents"


class UploadGuard:
    def __init__(self, app, slots: int | None = None):
        self.app = app
        self.slots = BoundedSemaphore(slots or int(os.environ.get("UPLOAD_CONCURRENCY", "4")))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        upload = scope["path"] == UPLOAD_PATH and scope["method"] == "POST"
        if upload and not self.slots.acquire(blocking=False):
            return await error_response(ApiError(429, "RATE_LIMITED", "Uploads are busy. Retry shortly.", True))(scope, receive, send)
        limit = MAX_FILE_BYTES + 64 * 1024 if upload else JSON_LIMIT
        try:
            content = bytearray()
            try:
                with anyio.fail_after(30 if upload else 10):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(content) + len(chunk) > limit:
                            error = ApiError(413, "FILE_TOO_LARGE", "Request body exceeds the size limit.")
                            return await error_response(error)(scope, receive, send)
                        content.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await error_response(ApiError(408, "VALIDATION_ERROR", "Request body timed out."))(scope, receive, send)
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(content), "more_body": False}
                return await receive()

            await self.app(scope, replay, send)
        finally:
            if upload:
                self.slots.release()
