"""Discover -> evidence -> reasoning -> preview, all pure and Docker-free.

These functions turn one MCP `get_entities` payload into `DataHubEvidence`,
derive an observable `ReasoningConsequence` that cites that evidence, and
render the `DocumentPreview` that would be published. Nothing here calls
MCP or DataHub — that happens in `sherlock.connectors.datahub.writeback`,
which calls these functions with a real payload and then decides whether to
publish. Keeping this layer pure is what makes it testable without Docker.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sherlock.domain.models import DataHubEvidence, DocumentPreview, ReasoningConsequence
from sherlock.integrations.sherlock_core.contracts import EvidenceMcpSource, SherlockBaselineRequest, SherlockEvidence


def evidence_from_entity(tool: str, urn: str, entity: dict[str, Any], observed_at: datetime) -> list[DataHubEvidence]:
    """Turn one get_entities-shaped entity payload into DataHubEvidence facts."""
    facts: list[DataHubEvidence] = []

    name = entity.get("name") or entity.get("properties", {}).get("name")
    if name:
        facts.append(
            DataHubEvidence(id=f"ev-name-{urn}", tool=tool, urn=urn, observed_fact=f"Entity name is {name}.", observed_at=observed_at)
        )

    owners = entity.get("ownership", {}).get("owners", [])
    owner_names = [
        owner.get("owner", {}).get("properties", {}).get("displayName")
        for owner in owners
        if isinstance(owner, dict) and owner.get("owner", {}).get("properties", {}).get("displayName")
    ]
    if owner_names:
        facts.append(
            DataHubEvidence(
                id=f"ev-owners-{urn}", tool=tool, urn=urn, observed_fact=f"Owners on record: {', '.join(owner_names)}.", observed_at=observed_at
            )
        )

    terms = entity.get("glossaryTerms", {}).get("terms", [])
    term_names = [
        term.get("term", {}).get("properties", {}).get("name")
        for term in terms
        if isinstance(term, dict) and term.get("term", {}).get("properties", {}).get("name")
    ]
    if term_names:
        facts.append(
            DataHubEvidence(
                id=f"ev-terms-{urn}", tool=tool, urn=urn, observed_fact=f"Glossary terms attached: {', '.join(term_names)}.", observed_at=observed_at
            )
        )

    return facts


def evidence_from_lineage(tool: str, urn: str, upstream_payload: dict[str, Any], observed_at: datetime) -> list[DataHubEvidence]:
    """Turn one get_lineage(upstream=True)-shaped payload into DataHubEvidence.

    Upstream dependency count is incident-relevant on its own (a delayed or
    failed upstream can explain a stale/incomplete downstream asset) without
    needing to inspect what any upstream dataset actually contains.
    """
    raw = upstream_payload.get("upstreams", upstream_payload)
    if isinstance(raw, dict):
        entities = raw.get("entities", raw.get("results", raw.get("searchResults", [])))
    elif isinstance(raw, list):
        entities = raw
    else:
        entities = []

    names: list[str] = []
    if isinstance(entities, list):
        for item in entities:
            if not isinstance(item, dict):
                continue
            entity = item.get("entity") if isinstance(item.get("entity"), dict) else item
            name = entity.get("name") or entity.get("properties", {}).get("name") or entity.get("urn")
            if name:
                names.append(str(name))

    if not names:
        return []
    return [
        DataHubEvidence(
            id=f"ev-upstream-{urn}",
            tool=tool,
            urn=urn,
            observed_fact=f"{len(names)} upstream dependency(ies) at one hop: {', '.join(names)}.",
            observed_at=observed_at,
        )
    ]


def derive_reasoning_consequence(urn: str, evidence: list[DataHubEvidence]) -> ReasoningConsequence:
    """Derive one observable reasoning consequence from real DataHub evidence.

    Raises if there is no evidence to reason over — a consequence must always
    cite at least one real DataHubEvidence id, never a fabricated one.

    Priority order is deliberate: upstream lineage first (an incident-relevant
    signal — a failed/delayed upstream can explain a stale or incomplete
    downstream asset), then ownership (an escalation path), then a plain
    context fallback. Glossary/PII evidence, if present, stays in the
    evidence list and the rendered document for context, but is never chosen
    here as the cause of an incident — governance classification is not an
    operational root cause.
    """
    if not evidence:
        raise ValueError("Cannot derive a reasoning consequence without DataHub evidence")

    upstream_evidence = next((item for item in evidence if item.id.startswith("ev-upstream-")), None)
    if upstream_evidence is not None:
        return ReasoningConsequence(
            id=f"consequence-lineage-{urn}",
            statement=(
                f"{urn} depends on upstream data; if an upstream dependency failed or was delayed, "
                f"{urn} and anything derived from it (such as order reporting) could be stale or incomplete."
            ),
            evidence_ids=[upstream_evidence.id],
            next_test=f"Check the latest run status of the upstream dependencies feeding {urn} before ruling them out as the cause of the incident.",
        )

    owner_evidence = next((item for item in evidence if item.observed_fact.startswith("Owners on record:")), None)
    if owner_evidence is not None:
        return ReasoningConsequence(
            id=f"consequence-ownership-{urn}",
            statement=f"{urn} has identifiable ownership on record, so an escalation path exists for governance follow-up.",
            evidence_ids=[owner_evidence.id],
            next_test=f"Verify the listed owners of {urn} are still active before relying on them for escalation.",
        )

    return ReasoningConsequence(
        id=f"consequence-context-{urn}",
        statement=f"{urn} was read from DataHub, but no upstream lineage or ownership evidence was available to narrow the incident further.",
        evidence_ids=[evidence[0].id],
        next_test=f"Gather ownership or lineage metadata for {urn} to identify an escalation path before proceeding.",
    )


def deterministic_idempotency_key(urn: str, reasoning_consequence_id: str) -> str:
    """Same (urn, consequence) always yields the same key — required because
    mcp-server-datahub has no document-delete tool: a non-deterministic key
    would create a new permanent document on every retry."""
    digest = hashlib.sha256(f"{urn}|{reasoning_consequence_id}".encode()).hexdigest()[:16]
    return f"sherlock-investigation-{digest}"


def build_document_preview(urn: str, evidence: list[DataHubEvidence], consequence: ReasoningConsequence, idempotency_key: str) -> DocumentPreview:
    """Render the exact content that would be published. No MCP call happens here."""
    lines = [
        f"# Sherlock investigation preview for {urn}",
        "",
        f"Reasoning consequence: {consequence.statement}",
        f"Next test: {consequence.next_test}",
        "",
        "Evidence:",
    ]
    for item in evidence:
        lines.append(f"- [{item.tool}] {item.observed_fact} (urn={item.urn}, observed_at={item.observed_at.isoformat()})")
    lines.append("")
    lines.append(f"Idempotency marker: {idempotency_key}")

    return DocumentPreview(
        idempotency_key=idempotency_key,
        document_type="Insight",
        title=f"Sherlock investigation: {urn} ({idempotency_key})",
        content="\n".join(lines),
        related_assets=[urn],
        reasoning_consequence=consequence,
        evidence=evidence,
    )


def compute_preview_hash(preview: DocumentPreview) -> str:
    """Deterministic fingerprint of the substance of what would be published.

    The publish endpoint recomputes a fresh preview server-side and compares
    its hash to what the client is confirming — the client never gets to
    submit title/content directly, so there is no channel for altered content
    to reach save_document, and a hash mismatch (a real DataHub change between
    preview and approval, or a tampered hash) is rejected rather than silently
    published.

    Deliberately excludes each evidence item's `observed_at` timestamp: that
    field changes on every re-read even when the underlying DataHub facts have
    not, so hashing it would make a fresh, substantively-unchanged preview
    mismatch its own predecessor on every single publish attempt — a few
    seconds of clock drift between preview and approval must not be treated
    as tampering. `content` is likewise excluded from the hash directly
    because it embeds those same timestamps; everything that actually
    determines its substance (evidence facts, reasoning, title, document
    type, related assets, idempotency key) is hashed instead, so any real
    change still changes the hash.
    """
    canonical = {
        "idempotency_key": preview.idempotency_key,
        "document_type": preview.document_type,
        "title": preview.title,
        "related_assets": preview.related_assets,
        "reasoning_consequence": preview.reasoning_consequence.model_dump(),
        "engine_source": preview.engine_source,
        "evidence": [
            {"id": item.id, "tool": item.tool, "urn": item.urn, "observed_fact": item.observed_fact, "provenance": item.provenance}
            for item in preview.evidence
        ],
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


def to_canonical_evidence(datahub_evidence: list[DataHubEvidence], existing_ids: set[str] | None = None) -> list[SherlockEvidence]:
    """Deterministic DataHubEvidence -> canonical SherlockEvidence conversion.

    `content` carries only the observed fact (evidence_from_entity/
    evidence_from_lineage already produce pure observations, never
    interpretation). `source` records tool/URN/timestamp/provenance so the
    canonical investigation itself carries DataHub provenance, per the
    schema's new optional `source` field. IDs are assigned E<n>, skipping any
    already in `existing_ids` so a follow-up never collides with prior
    evidence in the same case.
    """
    used = set(existing_ids or ())
    canonical: list[SherlockEvidence] = []
    next_number = 1
    for item in datahub_evidence:
        while f"E{next_number}" in used:
            next_number += 1
        evidence_id = f"E{next_number}"
        used.add(evidence_id)
        next_number += 1
        canonical.append(
            SherlockEvidence(
                id=evidence_id,
                label=f"DataHub {item.tool}",
                content=item.observed_fact,
                source=EvidenceMcpSource(tool=item.tool, entity_urn=item.urn, retrieved_at=item.observed_at),
            )
        )
    return canonical


def build_baseline_request(urn: str, canonical_evidence: list[SherlockEvidence]) -> SherlockBaselineRequest:
    """The case sent to Sherlock-Core. Deliberately generic, not a fabricated
    incident: this flow has no simulated incident narrative (unlike the
    Frozen Dashboard demo) — it asks the canonical engine to reason over real
    DataHub context and surface whatever it finds worth a next test."""
    return SherlockBaselineRequest(
        case_id=f"datahub-document:{urn}",
        case_title=f"DataHub-observed context for {urn}",
        domain="DataHub metadata investigation",
        observed_outcome="DataHub governed metadata was read for this asset; no specific incident narrative was supplied by the caller.",
        expected_behavior=(
            "Investigate whether the observed DataHub context (lineage, ownership, schema, glossary) reveals a plausible "
            "operational or governance concern worth a next test. Lineage identifies candidate investigation paths, not "
            "proven causes; ownership, classifications, glossary terms, and schema must not be presented as incident "
            "causes unless case evidence establishes a causal link."
        ),
        evidence=canonical_evidence,
        user_hypotheses=[],
    )


def build_document_preview_from_engine_snapshot(
    urn: str,
    datahub_evidence: list[DataHubEvidence],
    canonical_evidence: list[SherlockEvidence],
    snapshot: dict[str, Any],
    idempotency_key: str,
) -> DocumentPreview | None:
    """Build a DocumentPreview from a REAL Sherlock-Core canonical investigation
    snapshot — the decisive path this flow exists for. Returns None (the
    caller must fall back) if the snapshot does not actually cite any
    DataHub-sourced evidence id anywhere reachable: a hypothesis's
    supported_by/contradicted_by/expected_but_absent_ids, an
    expectation_matrix entry's evidence_ids, or the next_test description.
    derive_reasoning_consequence()'s output must never be mistaken for this.
    """
    datahub_ids = {item.id for item in canonical_evidence}
    hypotheses = snapshot.get("hypotheses", [])
    if not isinstance(hypotheses, list) or not hypotheses:
        return None

    cited_datahub_ids: set[str] = set()
    contradicting: list[dict[str, Any]] = []
    prime_suspect = snapshot.get("prime_suspect", {}) if isinstance(snapshot.get("prime_suspect"), dict) else {}
    prime_hypothesis_id = prime_suspect.get("hypothesis_id")

    for hypothesis in hypotheses:
        if not isinstance(hypothesis, dict):
            continue
        for key in ("supported_by", "contradicted_by"):
            for link in hypothesis.get(key) or []:
                evidence_id = link.get("evidence_id") if isinstance(link, dict) else None
                if evidence_id in datahub_ids:
                    cited_datahub_ids.add(evidence_id)
                    if key == "contradicted_by" and hypothesis.get("id") == prime_hypothesis_id:
                        contradicting.append(link)
        for evidence_id in hypothesis.get("expected_but_absent_ids") or []:
            if evidence_id in datahub_ids:
                cited_datahub_ids.add(evidence_id)

    matrix_sections = snapshot.get("expectation_matrix", {})
    if isinstance(matrix_sections, dict):
        for entries in matrix_sections.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                for evidence_id in entry.get("evidence_ids") or []:
                    if evidence_id in datahub_ids:
                        cited_datahub_ids.add(evidence_id)

    next_test = snapshot.get("next_test", {}) if isinstance(snapshot.get("next_test"), dict) else {}
    next_test_description = str(next_test.get("description") or "")
    cited_datahub_ids.update(evidence_id for evidence_id in datahub_ids if evidence_id in next_test_description)

    if not cited_datahub_ids:
        return None

    prime_hypothesis = next((h for h in hypotheses if isinstance(h, dict) and h.get("id") == prime_hypothesis_id), None)
    if prime_hypothesis is None:
        prime_hypothesis = next(h for h in hypotheses if isinstance(h, dict))

    statement = str(prime_hypothesis.get("statement") or "")
    status = str(prime_hypothesis.get("status") or "unknown")
    case_title = str(snapshot.get("meta", {}).get("case_title") or urn) if isinstance(snapshot.get("meta"), dict) else urn
    open_case = snapshot.get("open_case_index", {})
    limitations = [str(open_case.get("explanation"))] if isinstance(open_case, dict) and open_case.get("explanation") else []

    id_by_datahub_evidence = dict(zip((item.id for item in datahub_evidence), (item.id for item in canonical_evidence), strict=True))

    lines = [
        f"# Sherlock investigation (canonical engine) for {urn}",
        "",
        f"Case: {case_title}",
        f"Hypothesis {prime_hypothesis.get('id')} ({status}): {statement}",
        "",
        "DataHub evidence submitted to this investigation:",
    ]
    for item in datahub_evidence:
        canonical_id = id_by_datahub_evidence.get(item.id, "?")
        cited = " — cited by the investigation" if canonical_id in cited_datahub_ids else " — not cited"
        lines.append(f"- {canonical_id} [{item.tool}] {item.observed_fact} (urn={item.urn}, observed_at={item.observed_at.isoformat()}){cited}")
    if contradicting:
        lines.append("")
        lines.append("Contradicting evidence for the leading hypothesis:")
        for link in contradicting:
            lines.append(f"- {link.get('evidence_id')}: {link.get('reason', '')}")
    lines.append("")
    lines.append(f"Next test: {next_test_description}")
    if limitations:
        lines.append("")
        lines.append("Limitations:")
        for item_text in limitations:
            lines.append(f"- {item_text}")
    lines.append("")
    lines.append(f"Idempotency marker: {idempotency_key}")

    consequence = ReasoningConsequence(
        id=f"engine-{prime_hypothesis.get('id')}-{urn}",
        statement=statement,
        evidence_ids=sorted(cited_datahub_ids),
        next_test=next_test_description,
    )

    return DocumentPreview(
        idempotency_key=idempotency_key,
        document_type="Insight",
        title=f"Sherlock investigation: {urn} ({idempotency_key})",
        content="\n".join(lines),
        related_assets=[urn],
        reasoning_consequence=consequence,
        evidence=datahub_evidence,
        engine_source="sherlock_core_canonical",
    )
