"""No-Docker unit tests for the MCP subprocess parameter fix and the document
allowlist. These do not start any subprocess; they only inspect what
_build_stdio_parameters constructs."""

from __future__ import annotations

from sherlock.connectors.datahub.provider import (
    _ALLOWED_DOCUMENT_MCP_TOOLS,
    _ALLOWED_MCP_TOOLS,
    _ALLOWED_SAMPLE_MCP_TOOLS,
    DataHubSettings,
    _build_stdio_parameters,
)


def test_missing_token_no_longer_crashes_pydantic_validation() -> None:
    """Regression test for the spike finding: settings.token=None used to raise a
    pydantic ValidationError before any MCP call happened, because
    StdioServerParameters.env requires dict[str, str]. An unset token is a real,
    supported configuration (an instance with METADATA_SERVICE_AUTH_ENABLED=false),
    not something that should crash construction."""
    settings = DataHubSettings(token=None)

    parameters = _build_stdio_parameters(settings)

    assert parameters.env["DATAHUB_GMS_TOKEN"] == ""


def test_empty_token_stays_empty_not_a_placeholder() -> None:
    settings = DataHubSettings(token=None)

    parameters = _build_stdio_parameters(settings)

    # No fake/placeholder credential is ever substituted.
    assert parameters.env["DATAHUB_GMS_TOKEN"] != "not-printed"
    assert parameters.env["DATAHUB_GMS_TOKEN"] == ""


def test_real_token_is_passed_through_unchanged() -> None:
    settings = DataHubSettings(token="a-real-token")

    parameters = _build_stdio_parameters(settings)

    assert parameters.env["DATAHUB_GMS_TOKEN"] == "a-real-token"


def test_mutation_enabled_flag_controls_the_env_var() -> None:
    settings = DataHubSettings(token="x")

    read_only = _build_stdio_parameters(settings, mutation_enabled=False)
    mutation = _build_stdio_parameters(settings, mutation_enabled=True)

    assert read_only.env["TOOLS_IS_MUTATION_ENABLED"] == "false"
    assert mutation.env["TOOLS_IS_MUTATION_ENABLED"] == "true"


def test_document_allowlist_is_separate_from_general_read_allowlists() -> None:
    assert _ALLOWED_DOCUMENT_MCP_TOOLS == {"search_documents", "save_document"}
    assert _ALLOWED_DOCUMENT_MCP_TOOLS.isdisjoint(_ALLOWED_MCP_TOOLS)
    assert _ALLOWED_DOCUMENT_MCP_TOOLS.isdisjoint(_ALLOWED_SAMPLE_MCP_TOOLS)


def test_default_timeout_is_30_seconds() -> None:
    """Regression test for a reproduced failure: GET /api/v1/documents/preview
    returned 502 "MCP metadata request timed out" against a real local
    Quickstart instance under normal load, because DocumentWritebackProvider
    .preview() runs two MCP tool calls (get_entities + get_lineage) in one
    session/timeout budget, and that round trip measured 14-17s against the
    old 15.0s default — not a code defect, an insufficient default. This does
    not hide the error with retries; it raises the budget and keeps
    SHERLOCK_DATAHUB_TIMEOUT_SECONDS fully overridable."""
    settings = DataHubSettings()

    assert settings.timeout_seconds == 30.0


def test_timeout_env_var_still_overrides_the_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SHERLOCK_DATAHUB_TIMEOUT_SECONDS", "5")

    settings = DataHubSettings.from_environment()

    assert settings.timeout_seconds == 5.0
