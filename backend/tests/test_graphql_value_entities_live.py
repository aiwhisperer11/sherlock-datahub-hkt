"""Live DataHub GraphQL compatibility check for the valueEntities selection.

Run on demand with:
DATAHUB_LIVE=1 uv run --project backend --frozen pytest \
  backend/tests/test_graphql_value_entities_live.py -q
"""

from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

import pytest

from sherlock.connectors.datahub.provider import _graphql_query


pytestmark = pytest.mark.skipif(
    os.getenv("DATAHUB_LIVE") != "1",
    reason="requires local DataHub GraphQL; set DATAHUB_LIVE=1 to run",
)


def test_value_entities_query_matches_live_datahub_schema() -> None:
    request = Request(
        "http://localhost:8080/api/graphql",
        data=json.dumps({"query": _graphql_query()}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:  # noqa: S310 - local test-only endpoint
        body = json.loads(response.read())

    assert "errors" not in body
    dataset = body["data"]["dataset"]
    assert isinstance(dataset, dict)
    value_entities = [
        entity
        for entry in dataset["structuredProperties"]["properties"]
        for entity in entry.get("valueEntities") or []
    ]
    assert value_entities
    assert {entity["__typename"] for entity in value_entities} == {"CorpUser"}
    assert all("properties" in entity and "displayName" in entity["properties"] for entity in value_entities)
