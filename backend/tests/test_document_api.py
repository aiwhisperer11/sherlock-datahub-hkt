"""No-Docker HTTP tests for the preview/publish/retrieve endpoints. MCP is never
touched here — DocumentWritebackProvider methods are monkeypatched, exactly like
test_writeback.py mocks McpWritebackProvider at the endpoint layer.

The publish tests specifically cover the preview-cache fix: POST /publish
must publish the exact server-side-cached preview a prior GET /preview
returned, keyed by preview_hash, and must never call .preview() again —
regenerating a preview means re-running MCP and (if configured) the live,
non-deterministic Sherlock-Core engine, which is exactly the bug this cache
exists to avoid.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import sherlock.api.main as main_module
from sherlock.api.main import app
from sherlock.api.preview_cache import PreviewCache
from sherlock.connectors.datahub.provider import DataHubProviderError
from sherlock.connectors.datahub.writeback import DocumentWritebackProvider
from sherlock.domain.models import DataHubEvidence, DocumentPreview, DocumentRetrievalResult, DocumentWritebackResult, ReasoningConsequence

URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)"


@pytest.fixture(autouse=True)
def fresh_preview_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets its own empty cache — the real one is a module-level
    singleton and must not leak entries between tests."""
    monkeypatch.setattr(main_module, "_document_preview_cache", PreviewCache())


def _preview(statement: str = "ORDER_DETAILS depends on upstream data; if an upstream dependency failed or was delayed, it could be stale.") -> DocumentPreview:
    consequence = ReasoningConsequence(
        id="consequence-lineage-x",
        statement=statement,
        evidence_ids=["ev-upstream-x"],
        next_test="Check the latest run status of the upstream dependencies.",
    )
    evidence = [
        DataHubEvidence(id="ev-upstream-x", tool="get_lineage", urn=URN, observed_fact="2 upstream dependency(ies) at one hop: INVENTORIES, ORDERS.", observed_at=datetime.now(UTC))
    ]
    return DocumentPreview(
        idempotency_key="sherlock-investigation-deadbeefcafebabe",
        document_type="Insight",
        title="Sherlock investigation: ORDER_DETAILS (sherlock-investigation-deadbeefcafebabe)",
        content=f"preview content: {statement}",
        related_assets=[URN],
        reasoning_consequence=consequence,
        evidence=evidence,
    )


def _fail_if_called(name: str):
    def _fake(self, *args, **kwargs):
        raise AssertionError(f"{name} must not be called in this scenario")

    return _fake


def _get_preview(client: TestClient) -> tuple[dict, str]:
    response = client.get("/api/v1/documents/preview")
    assert response.status_code == 200
    body = response.json()
    return body, body["preview_hash"]


# --- preview endpoint --------------------------------------------------------

def test_preview_endpoint_returns_preview_and_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    preview = _preview()
    monkeypatch.setattr(DocumentWritebackProvider, "preview", lambda self, urn: preview)
    monkeypatch.setattr(DocumentWritebackProvider, "publish", _fail_if_called("publish"))

    response = TestClient(app).get("/api/v1/documents/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["preview"]["idempotency_key"] == preview.idempotency_key
    assert body["preview"]["title"] == preview.title
    assert body["preview_hash"]


def test_preview_endpoint_surfaces_provider_error_as_502(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(self, urn):
        raise DataHubProviderError("MCP metadata request failed")

    monkeypatch.setattr(DocumentWritebackProvider, "preview", fail)

    response = TestClient(app).get("/api/v1/documents/preview")

    assert response.status_code == 502
    assert response.json()["detail"] == "MCP metadata request failed"


def test_preview_endpoint_calls_the_engine_exactly_once_per_request(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def counting_preview(self, urn: str) -> DocumentPreview:
        calls["count"] += 1
        return _preview()

    monkeypatch.setattr(DocumentWritebackProvider, "preview", counting_preview)

    response = TestClient(app).get("/api/v1/documents/preview")

    assert response.status_code == 200
    assert calls["count"] == 1


# --- publish endpoint: approval and request-shape guards ---------------------

def test_publish_endpoint_rejects_missing_approval_without_touching_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(DocumentWritebackProvider, "preview", _fail_if_called("preview"))
    monkeypatch.setattr(DocumentWritebackProvider, "publish", _fail_if_called("publish"))

    response = TestClient(app).post("/api/v1/documents/publish", json={"preview_hash": "irrelevant", "approved": False})

    assert response.status_code == 400
    assert "approval" in response.json()["detail"]


def test_publish_endpoint_defaults_approved_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(DocumentWritebackProvider, "preview", _fail_if_called("preview"))
    monkeypatch.setattr(DocumentWritebackProvider, "publish", _fail_if_called("publish"))

    response = TestClient(app).post("/api/v1/documents/publish", json={"preview_hash": "irrelevant"})

    assert response.status_code == 400


def test_publish_endpoint_cannot_accept_client_supplied_title_or_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """There is no request field for title/content — proving the request schema
    itself has no channel for altered content, not just that it's ignored."""
    fresh = _preview()
    published = DocumentWritebackResult(
        status="created", urn="urn:li:document:shared-x", idempotency_key=fresh.idempotency_key, document_type=fresh.document_type, title=fresh.title, detail="ok"
    )
    monkeypatch.setattr(DocumentWritebackProvider, "preview", lambda self, urn: fresh)
    monkeypatch.setattr(DocumentWritebackProvider, "publish", lambda self, preview, approved: published)

    client = TestClient(app)
    _, preview_hash = _get_preview(client)

    response = client.post(
        "/api/v1/documents/publish",
        json={"preview_hash": preview_hash, "approved": True, "title": "EVIL TITLE", "content": "EVIL CONTENT"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == fresh.title  # server's own preview.title, never the injected one


# --- publish endpoint: 409 for unknown/altered/expired hashes ----------------

def test_publish_endpoint_rejects_an_unknown_preview_hash_without_calling_preview_or_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(DocumentWritebackProvider, "preview", _fail_if_called("preview"))
    monkeypatch.setattr(DocumentWritebackProvider, "publish", _fail_if_called("publish"))

    response = TestClient(app).post("/api/v1/documents/publish", json={"preview_hash": "never-issued-by-a-preview-call", "approved": True})

    assert response.status_code == 409


def test_publish_endpoint_rejects_a_tampered_preview_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(DocumentWritebackProvider, "preview", lambda self, urn: _preview())
    monkeypatch.setattr(DocumentWritebackProvider, "publish", _fail_if_called("publish"))
    client = TestClient(app)
    _, preview_hash = _get_preview(client)
    tampered = ("0" if preview_hash[0] != "0" else "1") + preview_hash[1:]

    response = client.post("/api/v1/documents/publish", json={"preview_hash": tampered, "approved": True})

    assert response.status_code == 409


def test_publish_endpoint_rejects_an_expired_preview_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 0.0}
    cache = PreviewCache(ttl_seconds=900.0, clock=lambda: clock["now"])
    monkeypatch.setattr(main_module, "_document_preview_cache", cache)
    monkeypatch.setattr(DocumentWritebackProvider, "preview", lambda self, urn: _preview())
    monkeypatch.setattr(DocumentWritebackProvider, "publish", _fail_if_called("publish"))
    client = TestClient(app)
    _, preview_hash = _get_preview(client)

    clock["now"] += 901.0  # past the 900s TTL

    response = client.post("/api/v1/documents/publish", json={"preview_hash": preview_hash, "approved": True})

    assert response.status_code == 409


def test_publish_endpoint_rejects_a_preview_hash_from_before_a_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    """A backend restart clears the in-memory cache. Simulated here by simply
    never populating it: any preview_hash issued "before" is unrecoverable."""
    monkeypatch.setattr(DocumentWritebackProvider, "publish", _fail_if_called("publish"))

    response = TestClient(app).post("/api/v1/documents/publish", json={"preview_hash": "issued-before-a-restart", "approved": True})

    assert response.status_code == 409


# --- publish endpoint: publishes the cached content, never regenerates -------

def test_publish_endpoint_never_calls_preview_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requirement: POST /publish must not re-run MCP context acquisition or
    the Sherlock-Core engine. preview() is only allowed to run once, during
    the earlier GET /preview call that populated the cache."""
    fixed = _preview()
    monkeypatch.setattr(DocumentWritebackProvider, "preview", lambda self, urn: fixed)
    client = TestClient(app)
    _, preview_hash = _get_preview(client)

    # From here on, .preview() must never be called again.
    monkeypatch.setattr(DocumentWritebackProvider, "preview", _fail_if_called("preview"))
    monkeypatch.setattr(
        DocumentWritebackProvider,
        "publish",
        lambda self, preview, approved: DocumentWritebackResult(
            status="created", urn="urn:li:document:shared-x", idempotency_key=preview.idempotency_key, document_type=preview.document_type, title=preview.title, detail="ok"
        ),
    )

    response = client.post("/api/v1/documents/publish", json={"preview_hash": preview_hash, "approved": True})

    assert response.status_code == 200


def test_publish_endpoint_publishes_exactly_the_approved_content(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = _preview(statement="the exact approved statement")
    monkeypatch.setattr(DocumentWritebackProvider, "preview", lambda self, urn: fixed)
    client = TestClient(app)
    _, preview_hash = _get_preview(client)

    seen: dict[str, object] = {}

    def fake_publish(self, preview: DocumentPreview, approved: bool) -> DocumentWritebackResult:
        seen["preview"] = preview
        return DocumentWritebackResult(status="created", urn="urn:li:document:shared-x", idempotency_key=preview.idempotency_key, document_type=preview.document_type, title=preview.title, detail="ok")

    monkeypatch.setattr(DocumentWritebackProvider, "publish", fake_publish)

    response = client.post("/api/v1/documents/publish", json={"preview_hash": preview_hash, "approved": True})

    assert response.status_code == 200
    published_preview = seen["preview"]
    assert published_preview.title == fixed.title
    assert published_preview.content == fixed.content
    assert published_preview.reasoning_consequence.statement == "the exact approved statement"
    assert published_preview.evidence == fixed.evidence


def test_a_second_different_llm_response_does_not_affect_the_already_approved_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulates exactly the real failure: the canonical engine returns
    different wording on a second call. The first, already-approved preview
    must still publish with its own original content, unaffected."""
    client = TestClient(app)

    monkeypatch.setattr(DocumentWritebackProvider, "preview", lambda self, urn: _preview(statement="first LLM response"))
    _, first_hash = _get_preview(client)

    monkeypatch.setattr(DocumentWritebackProvider, "preview", lambda self, urn: _preview(statement="second, different LLM response"))
    _, second_hash = _get_preview(client)

    assert first_hash != second_hash

    seen: dict[str, object] = {}
    monkeypatch.setattr(DocumentWritebackProvider, "preview", _fail_if_called("preview"))
    monkeypatch.setattr(
        DocumentWritebackProvider,
        "publish",
        lambda self, preview, approved: (seen.__setitem__("preview", preview) or DocumentWritebackResult(status="created", urn="urn:li:document:shared-x", idempotency_key=preview.idempotency_key, document_type=preview.document_type, title=preview.title, detail="ok")),
    )

    response = client.post("/api/v1/documents/publish", json={"preview_hash": first_hash, "approved": True})

    assert response.status_code == 200
    assert seen["preview"].reasoning_consequence.statement == "first LLM response"


def test_double_publish_with_the_same_hash_returns_already_exists_on_the_second_call(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = _preview()
    monkeypatch.setattr(DocumentWritebackProvider, "preview", lambda self, urn: fixed)
    client = TestClient(app)
    _, preview_hash = _get_preview(client)

    call_count = {"n": 0}

    def fake_publish(self, preview: DocumentPreview, approved: bool) -> DocumentWritebackResult:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return DocumentWritebackResult(status="created", urn="urn:li:document:shared-x", idempotency_key=preview.idempotency_key, document_type=preview.document_type, title=preview.title, detail="created")
        return DocumentWritebackResult(status="already_exists", urn="urn:li:document:shared-x", idempotency_key=preview.idempotency_key, document_type=preview.document_type, title=preview.title, detail="already published")

    monkeypatch.setattr(DocumentWritebackProvider, "publish", fake_publish)

    first = client.post("/api/v1/documents/publish", json={"preview_hash": preview_hash, "approved": True})
    second = client.post("/api/v1/documents/publish", json={"preview_hash": preview_hash, "approved": True})

    assert first.status_code == 200
    assert first.json()["status"] == "created"
    assert second.status_code == 200
    assert second.json()["status"] == "already_exists"
    assert second.json()["idempotency_key"] == first.json()["idempotency_key"]


def test_publish_endpoint_surfaces_provider_error_as_502(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = _preview()

    def fail(self, preview, approved):
        raise DataHubProviderError("save_document did not report success")

    monkeypatch.setattr(DocumentWritebackProvider, "preview", lambda self, urn: fixed)
    client = TestClient(app)
    _, preview_hash = _get_preview(client)
    monkeypatch.setattr(DocumentWritebackProvider, "publish", fail)

    response = client.post("/api/v1/documents/publish", json={"preview_hash": preview_hash, "approved": True})

    assert response.status_code == 502


# --- retrieve endpoint --------------------------------------------------------

def test_retrieve_endpoint_returns_verified_result(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_retrieve(self, idempotency_key: str, expected_urn: str | None = None) -> DocumentRetrievalResult:
        seen["idempotency_key"] = idempotency_key
        seen["expected_urn"] = expected_urn
        return DocumentRetrievalResult(status="verified", urn="urn:li:document:shared-new-1", title="t", idempotency_key=idempotency_key, detail="ok")

    monkeypatch.setattr(DocumentWritebackProvider, "retrieve", fake_retrieve)

    response = TestClient(app).get(
        "/api/v1/documents/retrieve",
        params={"idempotency_key": "sherlock-investigation-deadbeefcafebabe", "expected_urn": "urn:li:document:shared-new-1"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "verified"
    assert seen["idempotency_key"] == "sherlock-investigation-deadbeefcafebabe"
    assert seen["expected_urn"] == "urn:li:document:shared-new-1"


def test_retrieve_endpoint_works_without_expected_urn(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_retrieve(self, idempotency_key: str, expected_urn: str | None = None) -> DocumentRetrievalResult:
        assert expected_urn is None
        return DocumentRetrievalResult(status="not_found", urn=None, title=None, idempotency_key=idempotency_key, detail="not found")

    monkeypatch.setattr(DocumentWritebackProvider, "retrieve", fake_retrieve)

    response = TestClient(app).get("/api/v1/documents/retrieve", params={"idempotency_key": "sherlock-investigation-x"})

    assert response.status_code == 200
    assert response.json()["status"] == "not_found"
