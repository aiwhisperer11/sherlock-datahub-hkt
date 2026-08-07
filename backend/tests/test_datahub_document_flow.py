"""No-Docker unit tests for the pure discover -> evidence -> reasoning -> preview
pipeline. Nothing here touches MCP or a subprocess."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sherlock.investigations.datahub_document_flow import (
    build_document_preview,
    compute_preview_hash,
    derive_reasoning_consequence,
    deterministic_idempotency_key,
    evidence_from_entity,
    evidence_from_lineage,
)

URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)"
OBSERVED_AT = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def _entity_with_pii() -> dict[str, object]:
    return {
        "urn": URN,
        "name": "ORDER_DETAILS",
        "ownership": {"owners": [{"owner": {"properties": {"displayName": "Data Platform Team"}}}]},
        "glossaryTerms": {"terms": [{"term": {"properties": {"name": "PII"}}}]},
    }


def _entity_without_pii() -> dict[str, object]:
    return {
        "urn": URN,
        "name": "ORDER_DETAILS",
        "ownership": {"owners": [{"owner": {"properties": {"displayName": "Data Platform Team"}}}]},
        "glossaryTerms": {"terms": []},
    }


def _upstream_payload_fixed() -> dict[str, object]:
    return {
        "upstreams": {
            "entities": [
                {"entity": {"name": "INVENTORIES", "urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.inventories,PROD)"}},
            ]
        }
    }


def test_evidence_from_entity_captures_tool_urn_fact_timestamp_provenance() -> None:
    evidence = evidence_from_entity("get_entities", URN, _entity_with_pii(), OBSERVED_AT)

    assert evidence, "expected at least one evidence fact"
    for item in evidence:
        assert item.tool == "get_entities"
        assert item.urn == URN
        assert item.observed_fact
        assert item.observed_at == OBSERVED_AT
        assert item.provenance == "observed_from_datahub"

    facts = {item.observed_fact for item in evidence}
    assert any("PII" in fact for fact in facts)
    assert any("Data Platform Team" in fact for fact in facts)


def test_evidence_from_entity_with_no_fields_returns_nothing_fabricated() -> None:
    evidence = evidence_from_entity("get_entities", URN, {"urn": URN}, OBSERVED_AT)

    assert evidence == []


def test_evidence_from_lineage_captures_upstream_dependency_names() -> None:
    evidence = evidence_from_lineage("get_lineage", URN, _upstream_payload_fixed(), OBSERVED_AT)

    assert len(evidence) == 1
    item = evidence[0]
    assert item.tool == "get_lineage"
    assert item.urn == URN
    assert "INVENTORIES" in item.observed_fact
    assert item.provenance == "observed_from_datahub"


def test_evidence_from_lineage_with_no_upstream_returns_nothing_fabricated() -> None:
    evidence = evidence_from_lineage("get_lineage", URN, {"upstreams": {"entities": []}}, OBSERVED_AT)

    assert evidence == []


def test_reasoning_consequence_cites_real_evidence_ids() -> None:
    """The requirement this proves: at least one DataHub-sourced evidence id is
    referenced by the reasoning consequence's evidence_ids (and therefore by
    what becomes the document's next_test)."""
    evidence = evidence_from_entity("get_entities", URN, _entity_with_pii(), OBSERVED_AT) + evidence_from_lineage(
        "get_lineage", URN, _upstream_payload_fixed(), OBSERVED_AT
    )
    evidence_ids = {item.id for item in evidence}

    consequence = derive_reasoning_consequence(URN, evidence)

    assert consequence.evidence_ids, "reasoning consequence must cite at least one evidence id"
    assert set(consequence.evidence_ids).issubset(evidence_ids), "cited evidence ids must be real, not fabricated"
    assert consequence.next_test
    assert URN in consequence.next_test


def test_reasoning_prefers_lineage_over_pii_and_never_cites_pii_as_cause() -> None:
    """Upstream lineage evidence must win over glossary/PII evidence: PII is a
    governance classification, not an incident cause. Even though PII evidence
    is present here (real ORDER_DETAILS carries a PII term), it must not be
    the cited evidence and must not appear in the statement or next_test."""
    evidence = evidence_from_entity("get_entities", URN, _entity_with_pii(), OBSERVED_AT) + evidence_from_lineage(
        "get_lineage", URN, _upstream_payload_fixed(), OBSERVED_AT
    )

    consequence = derive_reasoning_consequence(URN, evidence)

    assert consequence.id.startswith("consequence-lineage-")
    assert consequence.evidence_ids == ["ev-upstream-" + URN]
    assert "PII" not in consequence.statement
    assert "PII" not in consequence.next_test
    assert "INVENTORIES" in consequence.statement or "upstream" in consequence.statement.lower()


def test_reasoning_falls_back_to_ownership_when_no_lineage() -> None:
    evidence = evidence_from_entity("get_entities", URN, _entity_with_pii(), OBSERVED_AT)  # no lineage evidence added

    consequence = derive_reasoning_consequence(URN, evidence)

    assert consequence.id.startswith("consequence-ownership-")
    assert "PII" not in consequence.statement
    assert "PII" not in consequence.next_test


def test_reasoning_falls_back_to_context_when_no_lineage_or_ownership() -> None:
    evidence = evidence_from_entity("get_entities", URN, {"urn": URN, "name": "ORDER_DETAILS"}, OBSERVED_AT)

    consequence = derive_reasoning_consequence(URN, evidence)

    assert consequence.id.startswith("consequence-context-")


def test_reasoning_consequence_requires_evidence() -> None:
    with pytest.raises(ValueError, match="without DataHub evidence"):
        derive_reasoning_consequence(URN, [])


def test_idempotency_key_is_deterministic_for_the_same_inputs() -> None:
    key_a = deterministic_idempotency_key(URN, "consequence-lineage-x")
    key_b = deterministic_idempotency_key(URN, "consequence-lineage-x")

    assert key_a == key_b


def test_idempotency_key_differs_for_different_consequences() -> None:
    key_a = deterministic_idempotency_key(URN, "consequence-lineage-x")
    key_b = deterministic_idempotency_key(URN, "consequence-ownership-x")

    assert key_a != key_b


def test_preview_never_fabricates_evidence_and_discloses_permanence() -> None:
    evidence = evidence_from_entity("get_entities", URN, _entity_with_pii(), OBSERVED_AT) + evidence_from_lineage(
        "get_lineage", URN, _upstream_payload_fixed(), OBSERVED_AT
    )
    consequence = derive_reasoning_consequence(URN, evidence)
    key = deterministic_idempotency_key(URN, consequence.id)

    preview = build_document_preview(URN, evidence, consequence, key)

    assert preview.idempotency_key == key
    assert preview.evidence == evidence
    assert preview.reasoning_consequence == consequence
    assert preview.related_assets == [URN]
    assert consequence.statement in preview.content
    assert consequence.next_test in preview.content
    for item in evidence:
        assert item.observed_fact in preview.content
    assert key in preview.title
    assert "no document-delete" in preview.persistence_warning.lower()


def test_preview_hash_is_deterministic_for_identical_previews() -> None:
    evidence = evidence_from_entity("get_entities", URN, _entity_with_pii(), OBSERVED_AT)
    consequence = derive_reasoning_consequence(URN, evidence)
    key = deterministic_idempotency_key(URN, consequence.id)
    preview_a = build_document_preview(URN, evidence, consequence, key)
    preview_b = build_document_preview(URN, evidence, consequence, key)

    assert compute_preview_hash(preview_a) == compute_preview_hash(preview_b)


def test_preview_hash_is_stable_across_different_observed_at_timestamps() -> None:
    """Regression test: publish() always re-derives a fresh preview server-side,
    and every fresh read stamps a new observed_at. If the hash depended on that
    timestamp, a substantively-unchanged preview would always mismatch its own
    predecessor and publish would 409 on every real attempt — this must not
    happen when nothing about the DataHub facts actually changed."""
    evidence_now = evidence_from_entity("get_entities", URN, _entity_with_pii(), OBSERVED_AT)
    evidence_later = evidence_from_entity("get_entities", URN, _entity_with_pii(), datetime(2026, 8, 7, 12, 5, 0, tzinfo=UTC))
    consequence = derive_reasoning_consequence(URN, evidence_now)
    key = deterministic_idempotency_key(URN, consequence.id)
    preview_now = build_document_preview(URN, evidence_now, consequence, key)
    preview_later = build_document_preview(URN, evidence_later, consequence, key)

    assert preview_now.content != preview_later.content  # the embedded timestamp text really did change
    assert compute_preview_hash(preview_now) == compute_preview_hash(preview_later)


def test_preview_hash_changes_when_an_observed_fact_changes() -> None:
    evidence = evidence_from_entity("get_entities", URN, _entity_with_pii(), OBSERVED_AT)
    consequence = derive_reasoning_consequence(URN, evidence)
    key = deterministic_idempotency_key(URN, consequence.id)
    original = build_document_preview(URN, evidence, consequence, key)
    tampered_evidence = [item.model_copy(update={"observed_fact": "TAMPERED FACT"}) if item.id == evidence[0].id else item for item in evidence]
    tampered = build_document_preview(URN, tampered_evidence, consequence, key)

    assert compute_preview_hash(original) != compute_preview_hash(tampered)


# --- DataHub evidence -> canonical Sherlock evidence adapter ---------------

from sherlock.investigations.datahub_document_flow import (  # noqa: E402
    build_document_preview_from_engine_snapshot,
    to_canonical_evidence,
)


def _two_datahub_facts() -> list:
    return evidence_from_entity("get_entities", URN, _entity_with_pii(), OBSERVED_AT) + evidence_from_lineage(
        "get_lineage", URN, _upstream_payload_fixed(), OBSERVED_AT
    )


def test_to_canonical_evidence_preserves_tool_urn_fact_timestamp_and_source() -> None:
    facts = _two_datahub_facts()

    canonical = to_canonical_evidence(facts)

    assert len(canonical) == len(facts)
    for fact, item in zip(facts, canonical, strict=True):
        assert item.content == fact.observed_fact  # content is the observed fact only, no interpretation
        assert item.source is not None
        assert item.source.type == "datahub_mcp"
        assert item.source.tool == fact.tool
        assert item.source.entity_urn == fact.urn
        assert item.source.retrieved_at == fact.observed_at


def test_to_canonical_evidence_ids_never_collide_with_existing_case_evidence() -> None:
    facts = _two_datahub_facts()  # 4 facts: name, owners, glossary terms, upstream lineage

    canonical = to_canonical_evidence(facts, existing_ids={"E1", "E2", "E3"})

    assigned_ids = {item.id for item in canonical}
    assert len(assigned_ids) == len(facts)
    assert assigned_ids.isdisjoint({"E1", "E2", "E3"})
    assert assigned_ids == {"E4", "E5", "E6", "E7"}


def test_to_canonical_evidence_ids_are_sequential_from_e1_with_no_existing_evidence() -> None:
    facts = _two_datahub_facts()

    canonical = to_canonical_evidence(facts)

    assert [item.id for item in canonical] == [f"E{n}" for n in range(1, len(facts) + 1)]


# --- Engine-snapshot-driven preview construction ----------------------------

def _snapshot_citing(evidence_id: str, *, via: str = "supported_by", statement: str = "ORDER_DETAILS depends on ORDERS_TRANSFORM.") -> dict:
    hypothesis: dict = {
        "id": "H1",
        "statement": statement,
        "status": "active",
        "confidence": 70,
        "supported_by": [],
        "contradicted_by": [],
        "expected_but_absent_ids": [],
    }
    if via == "supported_by":
        hypothesis["supported_by"] = [{"evidence_id": evidence_id, "reason": "lineage links the two datasets"}]
    elif via == "contradicted_by":
        hypothesis["contradicted_by"] = [{"evidence_id": evidence_id, "reason": "contradicts the timeline"}]
    elif via == "expected_but_absent_ids":
        hypothesis["expected_but_absent_ids"] = [evidence_id]

    return {
        "schema_version": "1.0.0",
        "meta": {"case_id": "datahub-document:x", "case_title": "DataHub-observed context", "domain": "d", "iteration": 1},
        "case": {"evidence": [], "observed_outcome": "o", "expected_behavior": "e"},
        "hypotheses": [hypothesis],
        "prime_suspect": {"hypothesis_id": "H1", "justification": "j", "condemning_datum": "c", "absolving_datum": "a"},
        "next_test": {"description": "Compare row counts before and after ORDERS_TRANSFORM.", "discriminates_between": ["H1"], "outcome_map": []},
        "expectation_matrix": {"expected_present": [], "expected_absent": [], "unexpected_present": [], "unexpected_absent": []},
        "open_case_index": {"explanation": "Execution logs were not observed.", "score": 40},
    }


def test_preview_from_engine_snapshot_cites_datahub_evidence_via_hypothesis() -> None:
    facts = _two_datahub_facts()
    canonical = to_canonical_evidence(facts)
    lineage_canonical_id = canonical[-1].id  # evidence_from_lineage's item is last
    snapshot = _snapshot_citing(lineage_canonical_id)

    preview = build_document_preview_from_engine_snapshot(URN, facts, canonical, snapshot, "sherlock-investigation-test")

    assert preview is not None
    assert preview.engine_source == "sherlock_core_canonical"
    assert lineage_canonical_id in preview.reasoning_consequence.evidence_ids
    assert preview.reasoning_consequence.statement == "ORDER_DETAILS depends on ORDERS_TRANSFORM."
    assert "Next test: Compare row counts" in preview.content


def test_preview_from_engine_snapshot_returns_none_when_no_datahub_evidence_is_cited() -> None:
    facts = _two_datahub_facts()
    canonical = to_canonical_evidence(facts)
    snapshot = _snapshot_citing("E99")  # not one of our canonical DataHub ids

    preview = build_document_preview_from_engine_snapshot(URN, facts, canonical, snapshot, "sherlock-investigation-test")

    assert preview is None


def test_preview_from_engine_snapshot_accepts_citation_via_next_test_text() -> None:
    facts = _two_datahub_facts()
    canonical = to_canonical_evidence(facts)
    lineage_id = canonical[-1].id
    snapshot = _snapshot_citing("E99")  # hypothesis links do NOT cite it
    snapshot["next_test"]["description"] = f"Re-check {lineage_id} against the warehouse before other tests."

    preview = build_document_preview_from_engine_snapshot(URN, facts, canonical, snapshot, "sherlock-investigation-test")

    assert preview is not None
    assert lineage_id in preview.reasoning_consequence.evidence_ids


def test_preview_from_engine_snapshot_includes_contradicting_evidence_section() -> None:
    facts = _two_datahub_facts()
    canonical = to_canonical_evidence(facts)
    lineage_id = canonical[-1].id
    snapshot = _snapshot_citing(lineage_id, via="contradicted_by")

    preview = build_document_preview_from_engine_snapshot(URN, facts, canonical, snapshot, "sherlock-investigation-test")

    assert preview is not None
    assert "Contradicting evidence" in preview.content
    assert lineage_id in preview.content


def test_preview_from_engine_snapshot_never_injects_causal_language_beyond_the_snapshot() -> None:
    """The renderer must echo the engine's own (non-causal, per P12) statement
    verbatim — it must not itself add causal framing on top of it."""
    facts = _two_datahub_facts()
    canonical = to_canonical_evidence(facts)
    lineage_id = canonical[-1].id
    neutral_statement = "ORDER_DETAILS has an upstream dependency; this makes the dependency a candidate for the next test, not a demonstrated cause."
    snapshot = _snapshot_citing(lineage_id, statement=neutral_statement)

    preview = build_document_preview_from_engine_snapshot(URN, facts, canonical, snapshot, "sherlock-investigation-test")

    assert preview is not None
    assert preview.reasoning_consequence.statement == neutral_statement
    assert "caused by" not in preview.content.lower()
    assert "proves" not in preview.content.lower()
