"""Automatic validation against the packaged canonical Sherlock schema."""
from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
import json
from typing import Any

from jsonschema import Draft202012Validator, SchemaError, ValidationError


class CanonicalInvestigationError(ValueError):
    """A sanitized integration-boundary validation failure."""


@lru_cache(maxsize=1)
def canonical_validator() -> Draft202012Validator:
    schema_file = files("sherlock.integrations.sherlock_core").joinpath("schemas/sherlock-investigation-1.0.0.schema.json")
    try:
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, SchemaError) as error:
        raise CanonicalInvestigationError("packaged canonical Sherlock schema is unavailable or invalid") from error
    return Draft202012Validator(schema)


def validate_unchanged(investigation: dict[str, Any]) -> dict[str, Any]:
    """Validate without changing the canonical object or exposing its contents."""
    if investigation.get("schema_version") != "1.0.0":
        raise CanonicalInvestigationError("incompatible SherlockInvestigation schema_version")
    try:
        canonical_validator().validate(investigation)
    except ValidationError as error:
        path = ".".join(str(part) for part in error.absolute_path) or "root"
        raise CanonicalInvestigationError(f"incompatible SherlockInvestigation at {path}") from error
    return investigation
