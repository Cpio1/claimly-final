"""Minimal server-only Supabase Storage REST adapter, with redirects disabled."""

from pathlib import Path
from urllib.parse import quote
import logging
import socket
import ssl

import httpx

from app.config import StorageSettings
from app.errors import ApiError

logger = logging.getLogger("uvicorn.error.claimly.storage")

# Only known protocol codes may reach logs; response messages and headers never do.
KNOWN_CODES = frozenset({
    "InvalidJWT", "AccessDenied", "NoSuchBucket", "NoSuchKey", "TenantNotFound",
    "InvalidApiKey", "Unauthorized", "InvalidRequest", "EntityTooLarge", "InternalError",
    "ResourceAlreadyExists", "KeyAlreadyExists", "InvalidMimeType", "DatabaseTimeout",
    "SignatureDoesNotMatch", "DatabaseError", "SlowDown", "not_found", "unauthorized",
    "already_exists", "BucketNotFound", "InvalidSignature",
})


def transport_category(error: httpx.HTTPError) -> str:
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.ProxyError):
        return "proxy"
    current, seen = error, set()
    for _ in range(10):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        # HTTP libraries may wrap native exceptions or retain only their message.
        detail = str(current).lower()
        if isinstance(current, ssl.SSLCertVerificationError) or "certificate_verify_failed" in detail:
            return "tls_certificate"
        if isinstance(current, ssl.SSLError):
            return "tls"
        if isinstance(current, socket.gaierror) or "getaddrinfo" in detail or "name resolution" in detail:
            return "dns"
        if getattr(current, "winerror", None) == 10013 or "10013" in detail:
            return "network_denied"
        current = current.__cause__ or current.__context__
    return "network" if isinstance(error, httpx.ConnectError) else "transport"


def http_category(status: int, code: str | None) -> str:
    if status == 401 or code in {"InvalidJWT", "InvalidApiKey", "Unauthorized"}:
        return "authentication"
    if status == 403 or code in {"AccessDenied", "unauthorized"}:
        return "permission"
    if status == 404 or code in {"NoSuchBucket", "BucketNotFound", "not_found"}:
        return "not_found"
    if status == 409:
        return "conflict"
    if status == 413:
        return "size_limit"
    if status == 429 or code == "SlowDown":
        return "rate_limit"
    if 300 <= status < 400:
        return "redirect_rejected"
    return "upstream" if status >= 500 else "invalid_request"


class StorageError(ApiError):
    def __init__(self, category="unknown", http_status=None, operation="unknown", storage_code=None):
        super().__init__(503, "INTERNAL_ERROR", "Private file storage is unavailable. Retry later.", True)
        self.category = category
        self.http_status = http_status
        self.operation = operation
        self.storage_code = storage_code


def fail(operation, category, http_status=None, storage_code=None):
    logger.warning("storage_failure operation=%s category=%s http_status=%s storage_code=%s",
                   operation, category, http_status if http_status is not None else "none",
                   storage_code or "none")
    raise StorageError(category, http_status, operation, storage_code) from None


class StorageClient:
    def __init__(self, settings: StorageSettings, transport=None):
        self.settings = settings
        self.transport = transport

    def _request(self, method, path, *, operation, **kwargs):
        try:
            with httpx.Client(base_url=self.settings.url.rstrip("/") + "/storage/v1/",
                              headers={"apikey": self.settings.secret_key},
                              timeout=httpx.Timeout(30, connect=10), follow_redirects=False,
                              transport=self.transport) as client:
                response = client.request(method, path, **kwargs)
            if not response.is_success:
                try:
                    body = response.json()
                    candidate = (body.get("code") or body.get("error")) if isinstance(body, dict) else None
                    code = candidate if isinstance(candidate, str) and candidate in KNOWN_CODES else None
                except ValueError:
                    code = None
                fail(operation, http_category(response.status_code, code), response.status_code, code)
            return response
        except httpx.HTTPError as error:
            fail(operation, transport_category(error))

    def ensure_private(self):
        response = self._request("GET", "bucket/" + quote(self.settings.bucket, safe=""), operation="bucket_check")
        try:
            bucket = response.json()
            if not isinstance(bucket, dict):
                fail("bucket_check", "invalid_bucket_response", response.status_code)
            if bucket.get("id") != self.settings.bucket:
                fail("bucket_check", "bucket_mismatch", response.status_code)
            if bucket.get("public") is True:
                fail("bucket_check", "bucket_not_private", response.status_code)
            if bucket.get("public") is not False:
                fail("bucket_check", "invalid_bucket_response", response.status_code)
        except (ValueError, AttributeError):
            fail("bucket_check", "invalid_bucket_response", response.status_code)

    def upload(self, path: str, content: bytes, mime_type: str):
        self._request("POST", "object/" + quote(self.settings.bucket, safe="") + "/" + quote(path, safe="/"),
                      operation="upload", content=content, headers={"Content-Type": mime_type, "x-upsert": "false"})

    def remove(self, bucket: str, path: str):
        # Recovery must use the bucket persisted with the intent, even if config changes.
        self._request("DELETE", "object/" + quote(bucket, safe=""), operation="recovery_delete", json={"prefixes": [path]})

    def download(self, path: str) -> bytes:
        return self._request("GET", "object/authenticated/" + quote(self.settings.bucket, safe="") + "/" + quote(path, safe="/"),
                             operation="download").content

    def delete(self, path: str):
        # Supabase bulk delete succeeds for already-missing objects, so retries are idempotent.
        self.remove(self.settings.bucket, path)

    def describe(self) -> str:
        return "supabase:" + self.settings.bucket


class LocalStorage:
    """Explicit LOCAL_DEV-only private directory (0700/0600); never used in production."""

    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise StorageError("invalid_path", operation="path")
        return path

    def ensure_private(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def upload(self, path: str, content: bytes, mime_type: str):
        target = self._path(path)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            with target.open("xb") as handle:
                handle.write(content)
        except FileExistsError:
            fail("upload", "conflict")
        target.chmod(0o600)

    def download(self, path: str) -> bytes:
        try:
            return self._path(path).read_bytes()
        except FileNotFoundError:
            fail("download", "not_found")

    def delete(self, path: str):
        self._path(path).unlink(missing_ok=True)

    def describe(self) -> str:
        return "local"


class S3Storage:
    """S3-compatible private bucket (e.g. Railway Bucket, Cloudflare R2, AWS S3) via boto3."""

    def __init__(self, settings, client=None, anonymous=None):
        self.settings = settings
        self._client, self._anonymous = client, anonymous
        self._checked = 0.0

    def _clients(self):
        if self._client is None:
            import boto3
            from botocore import UNSIGNED
            from botocore.config import Config

            common = {"endpoint_url": self.settings.endpoint, "region_name": self.settings.region}
            config = Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 2}, s3={"addressing_style": self.settings.addressing_style})
            self._client = boto3.client("s3", aws_access_key_id=self.settings.access_key_id,
                                        aws_secret_access_key=self.settings.secret_access_key, config=config, **common)
            self._anonymous = boto3.client("s3", config=Config(signature_version=UNSIGNED, connect_timeout=10, read_timeout=15,
                                                               retries={"max_attempts": 1}, s3={"addressing_style": self.settings.addressing_style}), **common)
        return self._client, self._anonymous

    def _call(self, operation, fn):
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            return fn()
        except ClientError as error:
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            code = error.response.get("Error", {}).get("Code")
            fail(operation, http_category(status or 500, code if code in KNOWN_CODES else None), status)
        except BotoCoreError:
            fail(operation, "transport")

    def ensure_private(self):
        import time as _time
        from botocore.exceptions import BotoCoreError, ClientError

        if _time.monotonic() - self._checked < 600:
            return
        client, anonymous = self._clients()
        self._call("bucket_check", lambda: client.head_bucket(Bucket=self.settings.bucket))
        try:
            anonymous.list_objects_v2(Bucket=self.settings.bucket, MaxKeys=1)
        except ClientError as error:
            if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") not in (401, 403):
                fail("bucket_check", "invalid_bucket_response")
        except BotoCoreError:
            fail("bucket_check", "transport")
        else:
            fail("bucket_check", "bucket_not_private")
        self._checked = _time.monotonic()

    def upload(self, path: str, content: bytes, mime_type: str):
        client, _ = self._clients()
        self._call("upload", lambda: client.put_object(Bucket=self.settings.bucket, Key=path, Body=content,
                                                       ContentType=mime_type))  # UUID paths; no overwrite of other keys

    def download(self, path: str) -> bytes:
        client, _ = self._clients()
        return self._call("download", lambda: client.get_object(Bucket=self.settings.bucket, Key=path)["Body"].read())

    def delete(self, path: str):
        client, _ = self._clients()
        self._call("delete", lambda: client.delete_object(Bucket=self.settings.bucket, Key=path))

    def describe(self) -> str:
        return "s3:" + self.settings.bucket


def make_storage(settings):
    """Select the configured private Storage adapter; configuration errors surface as 503s."""
    from app.config import s3_settings, storage_settings

    if settings.storage_backend == "local":
        return LocalStorage(settings.local_storage_dir)
    if settings.storage_backend == "s3":
        return S3Storage(s3_settings(settings))
    return StorageClient(storage_settings(settings))
