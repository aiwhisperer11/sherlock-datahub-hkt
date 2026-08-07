"""No-Docker unit tests for PreviewCache in isolation from FastAPI."""

from __future__ import annotations

from datetime import UTC, datetime

from sherlock.api.preview_cache import PreviewCache
from sherlock.domain.models import DataHubEvidence, DocumentPreview, ReasoningConsequence

URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,x,PROD)"


def _preview(statement: str = "s") -> DocumentPreview:
    return DocumentPreview(
        idempotency_key="sherlock-investigation-x",
        document_type="Insight",
        title="t",
        content=f"c-{statement}",
        related_assets=[URN],
        reasoning_consequence=ReasoningConsequence(id="c1", statement=statement, evidence_ids=["e1"], next_test="n"),
        evidence=[DataHubEvidence(id="e1", tool="get_lineage", urn=URN, observed_fact="f", observed_at=datetime(2026, 1, 1, tzinfo=UTC))],
    )


def test_put_then_get_returns_the_exact_same_object() -> None:
    cache = PreviewCache()
    preview = _preview()

    preview_hash = cache.put(preview)

    assert cache.get_verified(preview_hash) == preview


def test_unknown_hash_returns_none() -> None:
    cache = PreviewCache()

    assert cache.get_verified("never-stored") is None


def test_two_different_previews_get_two_different_hashes_and_both_are_retrievable() -> None:
    cache = PreviewCache()
    a, b = _preview("statement a"), _preview("statement b")

    hash_a = cache.put(a)
    hash_b = cache.put(b)

    assert hash_a != hash_b
    assert cache.get_verified(hash_a) == a
    assert cache.get_verified(hash_b) == b


def test_entry_expires_after_ttl() -> None:
    clock = {"now": 0.0}
    cache = PreviewCache(ttl_seconds=100.0, clock=lambda: clock["now"])
    preview_hash = cache.put(_preview())

    clock["now"] = 50.0
    assert cache.get_verified(preview_hash) is not None

    clock["now"] = 101.0
    assert cache.get_verified(preview_hash) is None


def test_a_fresh_cache_has_nothing_simulating_a_restart() -> None:
    cache = PreviewCache()
    preview_hash = cache.put(_preview())

    restarted = PreviewCache()  # a new process would construct a new, empty cache

    assert restarted.get_verified(preview_hash) is None


def test_put_opportunistically_sweeps_expired_entries() -> None:
    clock = {"now": 0.0}
    cache = PreviewCache(ttl_seconds=10.0, clock=lambda: clock["now"])
    cache.put(_preview("old"))
    assert len(cache._entries) == 1  # noqa: SLF001 - white-box check of internal cleanup

    clock["now"] = 11.0
    cache.put(_preview("new"))

    assert len(cache._entries) == 1  # noqa: SLF001 - the expired "old" entry was swept
