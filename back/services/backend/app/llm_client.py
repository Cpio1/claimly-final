"""HTTP adapter to the private internal LLM service (all six llm.openapi.json 2.0.0 operations).

LLM_SERVICE_TOKEN stays server-side; the LLM service holds no DB/Storage credentials.
Tests inject their own client object; there is no silent stub fallback in production.
"""

from __future__ import annotations

import json

import httpx

from app.errors import ApiError
from services.llm.app.contracts import validate as llm_validate

TIMEOUT = httpx.Timeout(600, connect=10)


class HttpLlmClient:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def _post(self, path: str, **kwargs) -> dict:
        if not self.settings.llm_service_token:
            raise ApiError(503, "AI_NOT_CONFIGURED", "AI is not configured on this server (LLM_SERVICE_TOKEN).")
        headers = {"Authorization": "Bearer " + self.settings.llm_service_token, **kwargs.pop("headers", {})}
        try:
            with httpx.Client(timeout=TIMEOUT, transport=self.transport, follow_redirects=False) as client:
                response = client.post(self.settings.llm_base_url.rstrip("/") + path, headers=headers, **kwargs)
        except httpx.HTTPError:
            raise ApiError(503, "LLM_UNAVAILABLE", "The internal AI service is unavailable.", True) from None
        try:
            value = response.json()
        except ValueError:
            raise ApiError(502, "INVALID_LLM_OUTPUT", "The internal AI service returned invalid JSON.") from None
        if not response.is_success:
            try:
                llm_validate("ErrorEnvelope", value, output=True)
                e = value["error"]
            except Exception:
                raise ApiError(502, "INVALID_LLM_OUTPUT", "The internal AI service returned an invalid error.") from None
            raise ApiError(response.status_code, e["code"], e["message"], e["retryable"])
        return value

    def _checked(self, value: dict, schema: str, request_id: str) -> dict:
        try:
            llm_validate(schema, value, output=True)
        except Exception:
            raise ApiError(502, "INVALID_LLM_OUTPUT", f"{schema} does not match the shared contract.") from None
        if value["request_id"] != request_id:
            raise ApiError(502, "INVALID_LLM_OUTPUT", "AI response request identity mismatch.")
        return value["data"]

    def extract(self, data: bytes, metadata: dict, as_of: str) -> dict:
        value = self._post("/internal/v1/extract", data={"metadata": json.dumps(metadata)},
                           files={"file": (metadata["filename"], data, metadata["mime_type"])}, headers={"X-Claimly-As-Of": as_of})
        return self._checked(value, "ExtractionResponse", metadata["request_id"])

    def answer(self, request: dict) -> dict:
        return self._checked(self._post("/internal/v1/answer", json=request), "AnswerResponse", request["request_id"])

    def match(self, request: dict) -> dict:
        return self._checked(self._post("/internal/v1/match", json=request), "AnswerResponse", request["request_id"])

    def assess(self, request: dict) -> dict:
        return self._checked(self._post("/internal/v1/assess", json=request), "AssessmentResponse", request["request_id"])

    def draft(self, request: dict) -> dict:
        return self._checked(self._post("/internal/v1/draft", json=request), "DraftResponse", request["request_id"])

    def analyze_reply(self, request: dict) -> dict:
        return self._checked(self._post("/internal/v1/analyze-reply", json=request), "ReplyResponse", request["request_id"])
