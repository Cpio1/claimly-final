"""Validate requests/responses against the shared backend contract (2.0.0); never edit it here."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from app.errors import ApiError, CONTRACT_VERSION
from app.settings import Settings


@lru_cache(maxsize=4)
def _spec(directory: str) -> dict:
    path = Path(directory) / "backend.openapi.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("info", {}).get("version") != CONTRACT_VERSION:
        raise RuntimeError("Backend contract version does not match 2.0.0.")
    return spec


@lru_cache(maxsize=256)
def _validator(directory: str, name: str) -> Draft202012Validator:
    spec = _spec(directory)
    schema = {"$ref": f"#/components/schemas/{name}", "components": spec["components"]}
    return Draft202012Validator(schema, format_checker=FormatChecker())


_DIR: str | None = None


def configure(settings: Settings) -> None:
    global _DIR
    _DIR = settings.contracts_dir


def validate(name: str, value, *, output: bool = False):
    directory = _DIR or Settings().contracts_dir
    if next(_validator(directory, name).iter_errors(value), None) is not None:
        # Never echo user/model content or validator reprs.
        if output:
            raise ApiError(500, "INTERNAL_ERROR", f"{name} failed server-side contract validation.", True)
        raise ApiError(422, "VALIDATION_ERROR", f"Request does not match the {name} contract.")
    return value


def paths() -> dict:
    return _spec(_DIR or Settings().contracts_dir)["paths"]
