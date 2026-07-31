from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

from sherlock.domain.models import (
    Anomaly,
    ConfidenceFactor,
    ConfidenceUpdate,
    DataHubObservation,
    ExplainableConfidence,
    FinalResult,
    FrozenDashboardHypothesis,
    FrozenDashboardResult,
    InitialHypothesis,
    InvestigationEvidence,
    HypothesisMatrixEntry,
    LineageEntity,
    LineagePage,
    McpSampleEntity,
    McpSampleResult,
    PrimeSuspect,
    ProviderAttempt,
    ObservedDataHubAsset,
    SchemaField,
    SimulatedTelemetry,
    WaldMissingEvidence,
)

ORDER_DETAILS_URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)"
INVENTORIES_URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.inventories,PROD)"
_ALLOWED_MCP_TOOLS = {"get_entities", "list_schema_fields", "get_lineage"}
_ALLOWED_SAMPLE_MCP_TOOLS = {"search", "get_entities", "get_lineage"}
_URN_TYPE_RE = re.compile(r"^urn:li:([a-zA-Z]+):")


class DataHubProviderError(RuntimeError):
    """A provider failed without exposing transport or credential details."""


def _extract_mcp_structured_result(result: Any, tool_name: str) -> dict[str, Any]:
    """Return the single structured object carried by an MCP tool result."""
    if getattr(result, "isError", False) or getattr(result, "is_error", False):
        raise DataHubProviderError(f"MCP {tool_name} returned an error")

    structured_payloads: list[dict[str, Any]] = []
    has_structured_content = False
    for attribute in ("structuredContent", "structured_content"):
        value = getattr(result, attribute, None)
        if value is not None:
            has_structured_content = True
            if isinstance(value, Mapping):
                structured_payloads.append(dict(value))

    if not has_structured_content:
        for block in getattr(result, "content", ()) or ():
            text = getattr(block, "text", None)
            if not isinstance(text, str):
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                structured_payloads.append(payload)

    unique_payloads: list[dict[str, Any]] = []
    for payload in structured_payloads:
        if payload not in unique_payloads:
            unique_payloads.append(payload)
    if len(unique_payloads) == 1:
        return unique_payloads[0]
    if len(unique_payloads) > 1:
        raise DataHubProviderError(f"MCP {tool_name} returned ambiguous structured results")
    raise DataHubProviderError(f"MCP {tool_name} returned no structured result")


def _require_token(settings: DataHubSettings) -> None:
    if not settings.token:
        raise DataHubProviderError("MCP requires DATAHUB_GMS_TOKEN")


def _run_mcp_fetch(fetch_coro: Any, timeout_seconds: float) -> Any:
    """Run an MCP fetch coroutine, sanitising timeouts and SDK/transport exceptions."""
    try:
        return asyncio.run(asyncio.wait_for(fetch_coro, timeout=timeout_seconds))
    except TimeoutError as error:
        raise DataHubProviderError("MCP metadata request timed out") from error
    except DataHubProviderError:
        raise
    except Exception as error:  # SDK and transport exceptions are deliberately sanitised.
        raise DataHubProviderError("MCP metadata request failed") from error


def _build_stdio_parameters(settings: DataHubSettings) -> Any:
    from mcp import StdioServerParameters

    return StdioServerParameters(
        command=settings.mcp_command,
        args=[settings.mcp_package],
        env={
            "DATAHUB_GMS_URL": settings.gms_url,
            "DATAHUB_GMS_TOKEN": settings.token,
            "TOOLS_IS_MUTATION_ENABLED": "false",
        },
    )


async def _call_mcp_tool(session: Any, tool_name: str, arguments: dict[str, Any], allowed_tools: set[str]) -> dict[str, Any]:
    if tool_name not in allowed_tools:
        raise DataHubProviderError("MCP mutation tools are not permitted")
    result = await session.call_tool(tool_name, arguments)
    return _extract_mcp_structured_result(result, tool_name)


@dataclass(frozen=True)
class DataHubSettings:
    mode: str = "sandbox"
    gms_url: str = "http://localhost:8080"
    token: str | None = None
    mcp_command: str = "/home/work/.local/bin/uvx"
    mcp_package: str = "mcp-server-datahub@latest"
    timeout_seconds: float = 15.0

    @classmethod
    def from_environment(cls) -> DataHubSettings:
        return cls(
            mode=os.getenv("SHERLOCK_METADATA_MODE", "sandbox").lower(),
            gms_url=os.getenv("DATAHUB_GMS_URL", "http://localhost:8080").rstrip("/"),
            token=os.getenv("DATAHUB_GMS_TOKEN") or None,
            mcp_command=os.getenv("SHERLOCK_DATAHUB_MCP_COMMAND", "/home/work/.local/bin/uvx"),
            mcp_package=os.getenv("SHERLOCK_DATAHUB_MCP_PACKAGE", "mcp-server-datahub@latest"),
            timeout_seconds=float(os.getenv("SHERLOCK_DATAHUB_TIMEOUT_SECONDS", "15")),
        )


class FrozenDashboardSource(Protocol):
    def fetch(self) -> DataHubObservation:
        """Return normalized observed metadata for ORDER_DETAILS."""


class SnapshotMetadataProvider:
    def __init__(self, fixture_path: Path | None = None) -> None:
        self.fixture_path = fixture_path or Path(__file__).resolve().parents[4] / "fixtures" / "frozen_dashboard_snapshot.json"

    def fetch(self) -> DataHubObservation:
        with self.fixture_path.open(encoding="utf-8") as fixture:
            return DataHubObservation.model_validate(json.load(fixture))


class GraphQLMetadataProvider:
    def __init__(self, settings: DataHubSettings) -> None:
        self.settings = settings

    def fetch(self) -> DataHubObservation:
        payload = json.dumps({"query": _graphql_query()}).encode()
        headers = {"Content-Type": "application/json"}
        if self.settings.token:
            headers["Authorization"] = f"Bearer {self.settings.token}"
        request = Request(f"{self.settings.gms_url}/api/graphql", data=payload, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:  # noqa: S310 - configured local GMS endpoint
                body = json.loads(response.read())
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise DataHubProviderError("GraphQL metadata request failed") from error
        if body.get("errors") or not isinstance(body.get("data"), dict) or not isinstance(body["data"].get("dataset"), dict):
            raise DataHubProviderError("GraphQL metadata response was invalid")
        return _normalise_graphql_payload(body["data"])


class McpMetadataProvider:
    def __init__(self, settings: DataHubSettings) -> None:
        self.settings = settings

    def fetch(self) -> DataHubObservation:
        _require_token(self.settings)
        return _run_mcp_fetch(self._fetch(), self.settings.timeout_seconds)

    async def _fetch(self) -> DataHubObservation:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        parameters = _build_stdio_parameters(self.settings)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                listed_names = {tool.name for tool in listed.tools}
                if not _ALLOWED_MCP_TOOLS.issubset(listed_names):
                    raise DataHubProviderError("MCP read tools required for frozen dashboard are unavailable")
                entities = await self._call(session, "get_entities", {"urns": [ORDER_DETAILS_URN, INVENTORIES_URN]})
                fields = await self._call(
                    session,
                    "list_schema_fields",
                    {"urn": ORDER_DETAILS_URN, "keywords": None, "limit": 100, "offset": 0},
                )
                upstream = await self._call(
                    session,
                    "get_lineage",
                    {"urn": ORDER_DETAILS_URN, "column": None, "query": "*", "upstream": True, "max_hops": 1, "max_results": 20, "offset": 0},
                )
                downstream = await self._call(
                    session,
                    "get_lineage",
                    {"urn": ORDER_DETAILS_URN, "column": None, "query": "*", "upstream": False, "max_hops": 1, "max_results": 20, "offset": 0},
                )
        return _normalise_mcp(entities, fields, upstream, downstream)

    async def _call(self, session: Any, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await _call_mcp_tool(session, tool_name, arguments, _ALLOWED_MCP_TOOLS)


class McpSampleProvider:
    """Discovers one real DataHub entity over MCP and normalises it for the minimal sample endpoint.

    Unlike McpMetadataProvider, this does not target a fixed URN: it searches DataHub for
    whatever entities actually exist, so it works against any DataHub instance's real data.
    """

    def __init__(self, settings: DataHubSettings | None = None) -> None:
        self.settings = settings or DataHubSettings.from_environment()

    def fetch_sample(self) -> McpSampleResult:
        if self.settings.mode != "mcp":
            raise DataHubProviderError("MCP sample requires SHERLOCK_METADATA_MODE=mcp")
        _require_token(self.settings)
        return _run_mcp_fetch(self._fetch(), self.settings.timeout_seconds)

    async def _fetch(self) -> McpSampleResult:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        parameters = _build_stdio_parameters(self.settings)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                listed_names = {tool.name for tool in listed.tools}
                if not _ALLOWED_SAMPLE_MCP_TOOLS.issubset(listed_names):
                    raise DataHubProviderError("MCP read tools required for the sample endpoint are unavailable")

                urn = await self._discover(session)
                entities = await self._call(session, "get_entities", {"urns": [urn]})
                upstream = await self._call(
                    session,
                    "get_lineage",
                    {"urn": urn, "column": None, "query": "*", "upstream": True, "max_hops": 1, "max_results": 10, "offset": 0},
                )
                downstream = await self._call(
                    session,
                    "get_lineage",
                    {"urn": urn, "column": None, "query": "*", "upstream": False, "max_hops": 1, "max_results": 10, "offset": 0},
                )
        return _normalise_mcp_sample(entities, upstream, downstream)

    async def _discover(self, session: Any) -> str:
        """Return the URN of one real entity, preferring a DATASET, from a broad search."""
        result = await self._call(session, "search", {"query": "*", "num_results": 10})
        raw_results = result.get("searchResults", result.get("results", []))
        if not isinstance(raw_results, list):
            raise DataHubProviderError("MCP search response was invalid")
        candidates = [item.get("entity") for item in raw_results if isinstance(item, dict) and isinstance(item.get("entity"), dict)]
        total = _integer(result.get("total")) or len(candidates)
        if total == 0 or not candidates:
            raise DataHubProviderError("MCP search returned zero entities")
        dataset = next((item for item in candidates if str(item.get("urn", "")).startswith("urn:li:dataset:")), None)
        chosen = dataset or candidates[0]
        urn = chosen.get("urn")
        if not urn:
            raise DataHubProviderError("MCP search result was missing a urn")
        return str(urn)

    async def _call(self, session: Any, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await _call_mcp_tool(session, tool_name, arguments, _ALLOWED_SAMPLE_MCP_TOOLS)


class DataHubMetadataProvider:
    """Provider orchestrator for the Frozen Dashboard investigation."""

    def __init__(self, settings: DataHubSettings | None = None, sources: dict[str, FrozenDashboardSource] | None = None) -> None:
        self.settings = settings or DataHubSettings.from_environment()
        self.sources = sources or {
            "mcp": McpMetadataProvider(self.settings),
            "graphql": GraphQLMetadataProvider(self.settings),
            "snapshot": SnapshotMetadataProvider(),
        }

    def load_stale_pipeline_demo(self) -> None:
        """The legacy stale-pipeline endpoint remains owned by SandboxMetadataProvider."""
        raise NotImplementedError("Use SandboxMetadataProvider for the stale-pipeline demo")

    def load_frozen_dashboard(self) -> FrozenDashboardResult:
        mode = self.settings.mode
        if mode not in {"sandbox", "mcp", "graphql", "auto"}:
            raise DataHubProviderError("Unsupported SHERLOCK_METADATA_MODE")
        order = ["snapshot"] if mode == "sandbox" else [mode] if mode in {"mcp", "graphql"} else ["mcp", "graphql", "snapshot"]
        attempts: list[ProviderAttempt] = []
        for provider_name in order:
            started = time.monotonic()
            if provider_name == "mcp" and isinstance(self.sources[provider_name], McpMetadataProvider) and not self.settings.token:
                attempts.append(_attempt(provider_name, "not_configured", started, "MCP requires DATAHUB_GMS_TOKEN"))
                if mode != "auto":
                    raise DataHubProviderError("MCP requires DATAHUB_GMS_TOKEN")
                continue
            try:
                observed = self.sources[provider_name].fetch()
            except DataHubProviderError as error:
                attempts.append(_attempt(provider_name, "failed", started, str(error)))
                if mode != "auto":
                    raise
            else:
                attempts.append(_attempt(provider_name, "succeeded", started))
                return _build_frozen_dashboard_result(observed, attempts, provider_name)
        raise DataHubProviderError("No metadata provider returned evidence")


def _attempt(provider: str, status: Literal["succeeded", "failed", "not_configured"], started: float, error: str | None = None) -> ProviderAttempt:
    return ProviderAttempt(provider=provider, status=status, duration_ms=round((time.monotonic() - started) * 1000), error=error)


def _normalise_mcp(entities: dict[str, Any], fields: dict[str, Any], upstream: dict[str, Any], downstream: dict[str, Any]) -> DataHubObservation:
    entity_list = entities.get("entities", entities.get("results", entities))
    if not isinstance(entity_list, list):
        raise DataHubProviderError("MCP entity response was invalid")
    central = next((item for item in entity_list if isinstance(item, dict) and item.get("urn") == ORDER_DETAILS_URN), None)
    if central is None:
        raise DataHubProviderError("MCP did not return ORDER_DETAILS")
    schema_payload = fields
    schema_fields = schema_payload.get("fields", [])
    if not isinstance(schema_fields, list):
        raise DataHubProviderError("MCP schema response was invalid")
    return DataHubObservation(
        urn=ORDER_DETAILS_URN,
        name=str(central.get("name") or central.get("properties", {}).get("name") or "ORDER_DETAILS"),
        platform=_platform_name(central),
        schema_total=_integer(schema_payload.get("totalFields")),
        schema_fields=[_schema_field(item) for item in schema_fields if isinstance(item, dict)],
        structured_properties=_structured_properties(central),
        owners=_owners(central),
        escalation_contact=_escalation_contact(central),
        tags=_tags(central),
        glossary_terms=_terms(central),
        upstream=_normalise_mcp_lineage("upstream", upstream),
        downstream=_normalise_mcp_lineage("downstream", downstream),
        consumers=_consumer_entities(_normalise_mcp_lineage("downstream", downstream).entities),
        related_assets=[_observed_asset(item) for item in entity_list if isinstance(item, dict) and item.get("urn") == INVENTORIES_URN],
        source="mcp",
        captured_at=datetime.now(UTC),
    )


def _normalise_mcp_lineage(direction: str, payload: dict[str, Any]) -> LineagePage:
    raw = payload.get(f"{direction}s", payload)
    if isinstance(raw, list):
        entities = raw
        metadata: dict[str, Any] = {}
    elif isinstance(raw, dict):
        metadata = raw
        entities = raw.get("entities", raw.get("results", raw.get("searchResults", [])))
    else:
        raise DataHubProviderError("MCP lineage response was invalid")
    if not isinstance(entities, list):
        raise DataHubProviderError("MCP lineage entities were invalid")
    normalised = [_lineage_entity(item) for item in entities if isinstance(item, dict)]
    return LineagePage(
        direction=direction,
        hops=1,
        offset=_integer(metadata.get("offset")) or 0,
        limit=20,
        total=_integer(metadata.get("total")),
        returned=_integer(metadata.get("returned")) or len(normalised),
        has_more=metadata.get("hasMore") if isinstance(metadata.get("hasMore"), bool) else None,
        entities=normalised,
    )


def _normalise_mcp_sample(entities: dict[str, Any], upstream: dict[str, Any], downstream: dict[str, Any]) -> McpSampleResult:
    entity_list = entities.get("entities", entities.get("results", entities.get("result", [])))
    if not isinstance(entity_list, list) or not entity_list:
        raise DataHubProviderError("MCP did not return entity details")
    raw = entity_list[0]
    if not isinstance(raw, dict):
        raise DataHubProviderError("MCP entity response was invalid")

    urn = str(raw.get("urn") or "unknown")
    schema_fields = raw.get("schemaMetadata", {}).get("fields", [])
    entity = McpSampleEntity(
        urn=urn,
        type=_entity_type_from_urn(urn),
        name=str(raw.get("name") or raw.get("properties", {}).get("name") or "unknown"),
        platform=_platform_name(raw),
        schema_fields=[str(field["fieldPath"]) for field in schema_fields if isinstance(field, dict) and field.get("fieldPath")],
        owners=_owners(raw),
        glossary_terms=_terms(raw),
        domains=_domains(raw),
        upstream_urns=_lineage_urns(upstream, "upstream"),
        downstream_urns=_lineage_urns(downstream, "downstream"),
    )
    return McpSampleResult(source_mode="mcp", source_verified=True, entity_count=1, entity=entity, captured_at=datetime.now(UTC), warnings=[])


def _entity_type_from_urn(urn: str) -> str:
    match = _URN_TYPE_RE.match(urn)
    return match.group(1).upper() if match else "UNKNOWN"


def _domains(value: dict[str, Any]) -> list[str]:
    domain = value.get("domain", {}).get("domain")
    if isinstance(domain, dict):
        name = domain.get("properties", {}).get("name")
        if name:
            return [str(name)]
    return []


def _lineage_urns(payload: dict[str, Any], direction: str) -> list[str]:
    raw = payload.get(f"{direction}s", payload)
    if isinstance(raw, dict):
        results = raw.get("searchResults", raw.get("entities", raw.get("results", [])))
    elif isinstance(raw, list):
        results = raw
    else:
        return []
    if not isinstance(results, list):
        return []
    urns: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        entity = item.get("entity") if isinstance(item.get("entity"), dict) else item
        urn = entity.get("urn")
        if urn:
            urns.append(str(urn))
    return urns


def _normalise_graphql_payload(payload: dict[str, Any]) -> DataHubObservation:
    dataset = payload["dataset"]
    schema = dataset.get("schemaMetadata") or {}
    downstream = _normalise_graphql_lineage("downstream", dataset.get("downstream") or {})
    related_assets = [
        _observed_asset(payload["inventories"])
        for _ in [None]
        if isinstance(payload.get("inventories"), dict)
    ]
    return DataHubObservation(
        urn=str(dataset.get("urn") or ORDER_DETAILS_URN),
        name=str(dataset.get("name") or dataset.get("properties", {}).get("name") or "ORDER_DETAILS"),
        platform=_platform_name(dataset),
        schema_total=_integer(schema.get("total")) or len(schema.get("fields", [])),
        schema_fields=[_schema_field(item) for item in schema.get("fields", []) if isinstance(item, dict)],
        structured_properties=_structured_properties(dataset),
        owners=_owners(dataset),
        escalation_contact=_escalation_contact(dataset),
        tags=_tags(dataset),
        glossary_terms=_terms(dataset),
        upstream=_normalise_graphql_lineage("upstream", dataset.get("upstream") or {}),
        downstream=downstream,
        consumers=_consumer_entities(downstream.entities),
        related_assets=related_assets,
        source="graphql",
        captured_at=datetime.now(UTC),
    )


def _normalise_graphql_lineage(direction: str, payload: dict[str, Any]) -> LineagePage:
    relationships = payload.get("relationships", [])
    if not isinstance(relationships, list):
        raise DataHubProviderError("GraphQL lineage response was invalid")
    entities = [_lineage_entity(item) for item in relationships if isinstance(item, dict)]
    return LineagePage(
        direction=direction,
        hops=1,
        offset=0,
        limit=100,
        total=_integer(payload.get("total")),
        returned=len(entities),
        entities=entities,
    )


def _schema_field(value: dict[str, Any]) -> SchemaField:
    return SchemaField(
        field_path=str(value.get("fieldPath") or value.get("field_path") or "unknown"),
        native_data_type=value.get("nativeDataType") or value.get("native_data_type"),
        description=value.get("description"),
    )


def _lineage_entity(value: dict[str, Any]) -> LineageEntity:
    entity = value.get("entity") if isinstance(value.get("entity"), dict) else value
    return LineageEntity(
        urn=str(entity.get("urn") or "unknown"),
        name=entity.get("name") or entity.get("properties", {}).get("name"),
        platform=_platform_name(entity),
        entity_type=entity.get("type"),
        relationship_type=value.get("type") if entity is not value else value.get("relationshipType"),
    )


def _observed_asset(value: dict[str, Any]) -> ObservedDataHubAsset:
    return ObservedDataHubAsset(
        urn=str(value.get("urn") or "unknown"),
        name=str(value.get("name") or value.get("properties", {}).get("name") or "unknown"),
        platform=_platform_name(value),
        structured_properties=_structured_properties(value),
        escalation_contact=_escalation_contact(value),
    )


def _platform_name(value: dict[str, Any]) -> str:
    platform = value.get("platform")
    if isinstance(platform, dict):
        return str(platform.get("name") or "unknown")
    return str(platform or "unknown")


def _structured_properties(value: dict[str, Any]) -> dict[str, str | float]:
    entries = value.get("structuredProperties", {}).get("properties", [])
    result: dict[str, str | float] = {}
    if not isinstance(entries, list):
        return result
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        definition = entry.get("structuredProperty", {}).get("definition", {})
        key = definition.get("qualifiedName") or entry.get("structuredProperty", {}).get("urn")
        values = entry.get("values", [])
        if not key or not isinstance(values, list) or not values or not isinstance(values[0], dict):
            continue
        raw = values[0]
        value_to_store = raw.get("stringValue", raw.get("numberValue"))
        if isinstance(value_to_store, (str, float, int)):
            result[str(key)] = float(value_to_store) if isinstance(value_to_store, int) else value_to_store
    return result


def _owners(value: dict[str, Any]) -> list[str]:
    owners = value.get("ownership", {}).get("owners", [])
    if not isinstance(owners, list):
        return []
    return [
        str(owner.get("owner", {}).get("properties", {}).get("displayName") or owner.get("owner", {}).get("name"))
        for owner in owners
        if isinstance(owner, dict) and (owner.get("owner", {}).get("properties", {}).get("displayName") or owner.get("owner", {}).get("name"))
    ]


def _escalation_contact(value: dict[str, Any]) -> str | None:
    entries = value.get("structuredProperties", {}).get("properties", [])
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("structuredProperty", {}).get("definition", {}).get("qualifiedName") != "showcase.escalationContact":
            continue
        entities = entry.get("valueEntities", [])
        if isinstance(entities, list) and entities and isinstance(entities[0], dict):
            return entities[0].get("properties", {}).get("displayName")
    return None


def _tags(value: dict[str, Any]) -> list[str]:
    entries = value.get("tags", {}).get("tags", [])
    return [str(item["tag"]["properties"]["name"]) for item in entries if isinstance(item, dict) and item.get("tag", {}).get("properties", {}).get("name")]


def _terms(value: dict[str, Any]) -> list[str]:
    entries = value.get("glossaryTerms", {}).get("terms", [])
    return [str(item["term"]["properties"]["name"]) for item in entries if isinstance(item, dict) and item.get("term", {}).get("properties", {}).get("name")]


def _consumer_entities(entities: list[LineageEntity]) -> list[LineageEntity]:
    return [entity for entity in entities if entity.platform and entity.platform.lower() in {"powerbi", "tableau", "looker", "dbt", "snowflake"}]


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _build_frozen_dashboard_result(observed: DataHubObservation, attempts: list[ProviderAttempt], selected_provider: str) -> FrozenDashboardResult:
    """Build a deterministic investigation; only telemetry is simulated, never DataHub evidence."""
    metadata_provenance: Literal["observed_from_datahub", "snapshot_fixture"] = "observed_from_datahub" if selected_provider in {"mcp", "graphql"} else "snapshot_fixture"
    telemetry = [
        SimulatedTelemetry(id="telemetry:dashboard-age", label="Dashboard data age", value_hours=31, context="Reported dashboard symptom."),
        SimulatedTelemetry(id="telemetry:dashboard-expectation", label="Expected dashboard age from DataHub Daily SLA", value_hours=24, context="Expectation derived from observed DataHub SLA."),
        SimulatedTelemetry(id="telemetry:order-details-age", label="ORDER_DETAILS observed age", value_hours=30, context="Incident telemetry, not a DataHub freshness timestamp."),
        SimulatedTelemetry(id="telemetry:inventories-age", label="INVENTORIES observed age", value_hours=4, context="Incident telemetry, not a DataHub freshness timestamp."),
    ]
    anomalies = [
        Anomaly(
            id="anomaly:missing-dashboard-update",
            type="missing_update",
            title="Dashboard missed its expected update",
            expected="Dashboard data age at or below 24 hours, derived from the observed Daily SLA.",
            observed="Simulated incident telemetry reports dashboard data age of 31 hours.",
            gap="7 hours beyond the expected update window.",
            severity="high",
            provenance=["telemetry:dashboard-age", "telemetry:dashboard-expectation", "datahub:sla"],
            why_it_matters="The expected update did not occur; this starts the investigation but does not identify a root cause.",
        ),
        Anomaly(
            id="anomaly:cross-layer-contradiction",
            type="cross_layer_contradiction",
            title="Upstream appears recent while ORDER_DETAILS remains stale",
            expected="If the upstream dependency were the primary delay, both upstream and derived stages would be similarly late.",
            observed="Simulated telemetry reports INVENTORIES at 4 hours and ORDER_DETAILS at 30 hours.",
            gap="26-hour stage difference across the observed lineage path.",
            severity="high",
            provenance=["telemetry:inventories-age", "telemetry:order-details-age", "datahub:lineage-upstream"],
            why_it_matters="The gap shifts attention from the upstream source to the transformation boundary, while remaining provisional.",
        ),
    ]
    initial_hypotheses = [
        InitialHypothesis(id="H1", statement="The dbt transformation producing ORDER_DETAILS is delayed or failed.", prior_confidence=0.45, evidence_needed=["Latest dbt run status and logs", "Real MAX(updated_at) for ORDER_DETAILS"], status="open"),
        InitialHypothesis(id="H2", statement="The INVENTORIES upstream dependency is delayed.", prior_confidence=0.30, evidence_needed=["Real INVENTORIES freshness", "Upstream job status"], status="open"),
        InitialHypothesis(id="H3", statement="A downstream BI refresh failed after ORDER_DETAILS updated.", prior_confidence=0.25, evidence_needed=["Power BI refresh timestamp and failure record", "Real MAX(updated_at) for ORDER_DETAILS"], status="open"),
    ]
    evidence = [
        InvestigationEvidence(id="E1", statement="Simulated dashboard telemetry shows data age of 31 hours against a 24-hour expectation.", provenance="simulated_incident_input", source_reference="telemetry:dashboard-age", reliability=0.65, limitations=["Synthetic incident telemetry; it is not a DataHub freshness signal."]),
        InvestigationEvidence(id="E2", statement="DataHub metadata for ORDER_DETAILS records a Daily freshness SLA.", provenance=metadata_provenance, source_reference=observed.urn, reliability=0.9, observed_at=observed.captured_at, limitations=["A Daily SLA is an expectation, not the actual latest data timestamp."]),
        InvestigationEvidence(id="E3", statement="Simulated incident telemetry reports ORDER_DETAILS at 30 hours old.", provenance="simulated_incident_input", source_reference=observed.urn, reliability=0.65, limitations=["Synthetic incident telemetry; it does not prove a dbt failure."]),
        InvestigationEvidence(id="E4", statement="Simulated incident telemetry reports INVENTORIES at 4 hours old.", provenance="simulated_incident_input", source_reference=INVENTORIES_URN, reliability=0.65, limitations=["Synthetic incident telemetry; live INVENTORIES freshness still needs verification."]),
        InvestigationEvidence(id="E5", statement=f"DataHub lineage shows {observed.upstream.total or observed.upstream.returned} upstream assets at one hop, including INVENTORIES.", provenance=metadata_provenance, source_reference=observed.urn, reliability=0.9, observed_at=observed.captured_at, limitations=["Lineage shows dependency structure, not execution status."]),
        InvestigationEvidence(id="E6", statement=f"DataHub lineage shows {observed.downstream.total or observed.downstream.returned} downstream assets at one hop, including BI consumers.", provenance=metadata_provenance, source_reference=observed.urn, reliability=0.9, observed_at=observed.captured_at, limitations=["No Power BI refresh timestamp or failure record was observed."]),
        InvestigationEvidence(id="E7", statement=f"ORDER_DETAILS has {observed.schema_total} schema fields, including quantity_on_hand, stock_status, and updated_at.", provenance=metadata_provenance, source_reference=observed.urn, reliability=0.9, observed_at=observed.captured_at, limitations=["Observed schema does not establish a recent contract change."]),
        InvestigationEvidence(id="E8", statement="No query history was retrieved; get_dataset_queries is not used by this read-only investigation path.", provenance="derived_by_sherlock", source_reference=observed.urn, reliability=0.5, limitations=["The absence of retrieved query history is not evidence that no queries or changes occurred."]),
    ]
    for asset in observed.related_assets:
        if asset.urn == INVENTORIES_URN:
            evidence.append(InvestigationEvidence(id="E9", statement=f"DataHub metadata for INVENTORIES records a {asset.structured_properties.get('showcase.dataFreshnessSla', 'recorded')} SLA, quality score {asset.structured_properties.get('showcase.dataQualityScore', 'not recorded')}, and escalation contact {asset.escalation_contact or 'not recorded'}.", provenance=metadata_provenance, source_reference=asset.urn, reliability=0.9, observed_at=observed.captured_at, limitations=["Metadata describes the asset but does not provide a live freshness timestamp."]))
    matrix = [
        HypothesisMatrixEntry(hypothesis_id="H1", evidence_id="E1", relationship="supports", weight=0.55, rationale="A missing dashboard update establishes a downstream symptom compatible with a stalled transformation."),
        HypothesisMatrixEntry(hypothesis_id="H1", evidence_id="E3", relationship="supports", weight=0.85, rationale="ORDER_DETAILS is already stale in simulated incident telemetry, before the BI layer."),
        HypothesisMatrixEntry(hypothesis_id="H1", evidence_id="E4", relationship="supports", weight=0.75, rationale="A recent upstream stage and stale derived stage point to the transformation boundary."),
        HypothesisMatrixEntry(hypothesis_id="H1", evidence_id="E5", relationship="supports", weight=0.55, rationale="Observed lineage places an upstream dependency directly before the affected asset."),
        HypothesisMatrixEntry(hypothesis_id="H1", evidence_id="dbt-logs", relationship="missing", weight=1.0, rationale="The latest dbt run and logs are required to confirm or reject H1."),
        HypothesisMatrixEntry(hypothesis_id="H2", evidence_id="E4", relationship="contradicts", weight=0.85, rationale="The simulated upstream age is much more recent than ORDER_DETAILS."),
        HypothesisMatrixEntry(hypothesis_id="H2", evidence_id="E5", relationship="supports", weight=0.35, rationale="INVENTORIES is an observed upstream dependency, but lineage alone does not show it is late."),
        HypothesisMatrixEntry(hypothesis_id="H2", evidence_id="inventories-freshness", relationship="missing", weight=1.0, rationale="Real freshness is needed because the current age is simulated."),
        HypothesisMatrixEntry(hypothesis_id="H3", evidence_id="E3", relationship="contradicts", weight=0.8, rationale="ORDER_DETAILS is already stale before a BI-only failure could explain the dashboard."),
        HypothesisMatrixEntry(hypothesis_id="H3", evidence_id="E6", relationship="supports", weight=0.25, rationale="Observed downstream BI consumers make a refresh issue possible, not demonstrated."),
        HypothesisMatrixEntry(hypothesis_id="H3", evidence_id="bi-refresh", relationship="missing", weight=1.0, rationale="A real Power BI refresh record is required to assess H3."),
    ]
    factor_sets = {
        "H1": _confidence_factors("H1", 0.82, 0.9, 0.88, 0.95),
        "H2": _confidence_factors("H2", 0.62, 0.9, 0.42, 0.72),
        "H3": _confidence_factors("H3", 0.58, 0.9, 0.38, 0.65),
    }
    priors = {hypothesis.id: hypothesis.prior_confidence for hypothesis in initial_hypotheses}
    updates = [
        ConfidenceUpdate(hypothesis_id=hypothesis_id, prior_confidence=priors[hypothesis_id], factors=list(factors.values()), final_confidence=_confidence_score(factors), explanation=_confidence_explanation(hypothesis_id))
        for hypothesis_id, factors in factor_sets.items()
    ]
    derived = [
        FrozenDashboardHypothesis(id=hypothesis_id.lower(), statement=next(item.statement for item in initial_hypotheses if item.id == hypothesis_id), confidence=ExplainableConfidence(**factors))
        for hypothesis_id, factors in factor_sets.items()
    ]
    h1_confidence = updates[0].final_confidence
    wald = [
        WaldMissingEvidence(id="W1", question="Did the dbt job complete and publish ORDER_DETAILS?", missing_evidence="Latest dbt run, status, and logs.", why_it_may_be_invisible="Execution logs are outside the metadata and lineage returned by DataHub.", hypotheses_affected=["H1", "H2"], information_value="high", acquisition_action="Open the ORDER_DETAILS dbt job run and retrieve its latest logs.", could_change_prime_suspect=True),
        WaldMissingEvidence(id="W2", question="Is ORDER_DETAILS truly stale in the warehouse?", missing_evidence="Real MAX(updated_at) for ORDER_DETAILS.", why_it_may_be_invisible="DataHub metadata records schema and SLA, not a live table-value query.", hypotheses_affected=["H1", "H3"], information_value="high", acquisition_action="Run a read-only warehouse query for MAX(updated_at).", could_change_prime_suspect=True),
        WaldMissingEvidence(id="W3", question="Was INVENTORIES actually fresh when the incident occurred?", missing_evidence="Real freshness timestamp for INVENTORIES.", why_it_may_be_invisible="The current comparison is explicitly simulated incident telemetry.", hypotheses_affected=["H1", "H2"], information_value="high", acquisition_action="Read the latest INVENTORIES timestamp from its source or operational monitor.", could_change_prime_suspect=True),
        WaldMissingEvidence(id="W4", question="Did the BI layer fail after a valid dataset update?", missing_evidence="Power BI refresh timestamp and failure details.", why_it_may_be_invisible="BI operational logs are not DataHub lineage evidence.", hypotheses_affected=["H3"], information_value="medium", acquisition_action="Inspect the latest Power BI refresh history for the affected report.", could_change_prime_suspect=True),
        WaldMissingEvidence(id="W5", question="Did a schema or contract change precede the incident?", missing_evidence="Real schema and contract change history.", why_it_may_be_invisible="The snapshot shows current schema only; query history is not retrieved.", hypotheses_affected=["H1", "H3"], information_value="medium", acquisition_action="Compare schema and contract history around the incident window.", could_change_prime_suspect=False),
    ]
    return FrozenDashboardResult(
        id="investigation-frozen-dashboard",
        title="The Case of the Frozen Dashboard",
        simulated_incident_input=["SIMULATED INCIDENT INPUT: a dashboard associated with ORDER_DETAILS missed its expected update."],
        observed_from_datahub=observed,
        simulated_telemetry=telemetry,
        anomalies=anomalies,
        initial_hypotheses=initial_hypotheses,
        evidence=evidence,
        hypothesis_matrix=matrix,
        confidence_update=updates,
        prime_suspect=PrimeSuspect(hypothesis_id="H1", label="The dbt transformation producing ORDER_DETAILS", status="provisional", confidence=h1_confidence, why_selected="The simulated upstream-to-derived stage gap and stale ORDER_DETAILS telemetry support a transformation-boundary investigation more than the alternatives.", strongest_supporting_evidence="ORDER_DETAILS is simulated as 30 hours old while INVENTORIES is simulated as 4 hours old.", strongest_counterevidence="No dbt execution log or real warehouse freshness value has been observed.", what_would_change_the_verdict="A successful recent dbt run with current ORDER_DETAILS data, or a confirmed BI refresh failure, would materially change the ranking."),
        wald=wald,
        final_result=FinalResult(verdict="The dbt transformation producing ORDER_DETAILS is the Prime Suspect; inspect its latest run and logs before declaring root cause.", verdict_status="provisional", confidence=h1_confidence, affected_assets=["ORDER_DETAILS", "Frozen dashboard", "Power BI, Tableau, and Looker downstream consumers"], business_impact="A stale dashboard can mislead operational and revenue decisions until the data path is confirmed.", immediate_action="Inspect the latest ORDER_DETAILS dbt run, then verify MAX(updated_at) in the warehouse.", owner_to_contact=observed.escalation_contact or "ORDER_DETAILS owner", confirmation_needed="Latest dbt logs and a real ORDER_DETAILS freshness value.", guardrail="This is an evidence-based confidence update, not a confirmed root cause or a Bayesian probability."),
        derived_by_sherlock=derived,
        limitations=["No dbt execution logs were observed.", "No live data freshness timestamp was observed.", "No BI refresh failure was observed.", "Synthetic incident telemetry is separate from observed DataHub metadata."],
        provider_attempts=attempts,
        selected_provider=selected_provider,
        conclusion="A provisional Prime Suspect is ranked, but root cause is not demonstrated by the available evidence.",
        recommended_action="Inspect the ORDER_DETAILS dbt execution first, then validate real warehouse freshness before investigating downstream BI refreshes.",
    )


def _confidence_factors(hypothesis_id: str, coverage: float, reliability: float, consistency: float, proximity: float) -> dict[str, ConfidenceFactor]:
    """Use the documented multiplicative confidence formula with hypothesis-specific evidence."""
    evidence_by_hypothesis = {
        "H1": (["E1", "E3", "E4", "E5"], "Evidence favours the transformation boundary, but dbt logs are missing."),
        "H2": (["E4", "E5"], "The simulated freshness comparison contradicts an upstream delay."),
        "H3": (["E3", "E6"], "ORDER_DETAILS appears stale before a BI-only explanation could account for the symptom."),
    }
    evidence_ids, consistency_explanation = evidence_by_hypothesis[hypothesis_id]
    return {
        "evidence_coverage": ConfidenceFactor(value=coverage, explanation="Coverage reflects the amount of relevant symptom, stage, and lineage evidence available.", evidence_ids=evidence_ids),
        "source_reliability": ConfidenceFactor(value=reliability, explanation="Observed metadata is high reliability; incident ages remain explicitly simulated.", evidence_ids=["E2", "E5", "E6"]),
        "consistency": ConfidenceFactor(value=consistency, explanation=consistency_explanation, evidence_ids=evidence_ids),
        "lineage_proximity": ConfidenceFactor(value=proximity, explanation="One-hop lineage ties the hypothesis to ORDER_DETAILS and its neighbours.", evidence_ids=["E5", "E6"]),
    }


def _confidence_score(factors: dict[str, ConfidenceFactor]) -> float:
    return round(factors["evidence_coverage"].value * factors["source_reliability"].value * factors["consistency"].value * factors["lineage_proximity"].value, 3)


def _confidence_explanation(hypothesis_id: str) -> str:
    explanations = {
        "H1": "H1 rises above its prior because the simulated stage gap and observed lineage align; it remains provisional because operational confirmation is absent.",
        "H2": "H2 falls below its prior because the simulated upstream age is recent relative to ORDER_DETAILS; live freshness remains missing.",
        "H3": "H3 falls below its prior because ORDER_DETAILS is already simulated as stale before the BI layer; a refresh record is still missing.",
    }
    return explanations[hypothesis_id]


def _graphql_query() -> str:
    return f'''query {{
      dataset(urn: "{ORDER_DETAILS_URN}") {{
        urn name platform {{ name }} properties {{ name description }}
        structuredProperties {{ properties {{ structuredProperty {{ urn definition {{ qualifiedName }} }} values {{ ... on StringValue {{ stringValue }} ... on NumberValue {{ numberValue }} }} valueEntities {{ __typename ... on CorpUser {{ properties {{ displayName }} }} }} }} }}
        schemaMetadata {{ fields {{ fieldPath nativeDataType description }} }}
        ownership {{ owners {{ owner {{ ... on CorpUser {{ properties {{ displayName }} }} ... on CorpGroup {{ name }} }} }} }}
        tags {{ tags {{ tag {{ properties {{ name }} }} }} }}
        glossaryTerms {{ terms {{ term {{ properties {{ name }} }} }} }}
        upstream: lineage(input: {{direction: UPSTREAM, start: 0, count: 100}}) {{ total relationships {{ type entity {{ urn type ... on Dataset {{ name platform {{ name }} properties {{ name }} }} }} }} }}
        downstream: lineage(input: {{direction: DOWNSTREAM, start: 0, count: 100}}) {{ total relationships {{ type entity {{ urn type ... on Dataset {{ name platform {{ name }} properties {{ name }} }} }} }} }}
      }}
      inventories: dataset(urn: "{INVENTORIES_URN}") {{
        urn name platform {{ name }} properties {{ name description }}
        structuredProperties {{ properties {{ structuredProperty {{ urn definition {{ qualifiedName }} }} values {{ ... on StringValue {{ stringValue }} ... on NumberValue {{ numberValue }} }} valueEntities {{ __typename ... on CorpUser {{ properties {{ displayName }} }} }} }} }}
      }}
    }}'''
