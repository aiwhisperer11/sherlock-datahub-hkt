"""Server-side cache of previews already shown to a human, keyed by their
content hash.

This exists to fix a real gap: with the canonical Sherlock-Core engine live,
GET /api/v1/documents/preview is not deterministic (the LLM's wording
differs between calls even for identical DataHub evidence, confirmed
against https://sherlock-engine.vercel.app). POST /publish used to
re-run preview() — MCP context fetch and the Sherlock-Core call — to
recompute a hash to compare against; on a non-deterministic engine, a
freshly regenerated preview's hash almost never matches what the human
actually approved, so real publishes failed with 409 "stale" even though
nothing was stale. The fix: publish must publish the exact object the
human reviewed, not a regenerated one. This module is that exact object's
home between preview and publish.

Expiry: entries expire `ttl_seconds` after they were stored (default 900s /
15 minutes) — long enough for a human to review and approve, short enough
that an old preview is not publishable indefinitely.

Restart behavior: purely in-memory (a plain dict on this object). A backend
restart clears every cached preview with no persistence anywhere. Any
preview_hash issued before a restart is unrecoverable; POST /publish must
(and does, via a cache miss) return 409 for it — there is no exact
previously-reviewed content left to publish.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from sherlock.domain.models import DocumentPreview
from sherlock.investigations.datahub_document_flow import compute_preview_hash

DEFAULT_TTL_SECONDS = 900.0


class PreviewCache:
    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[str, tuple[DocumentPreview, float]] = {}

    def put(self, preview: DocumentPreview) -> str:
        """Store the exact preview object and return its content hash."""
        self._sweep_expired()
        preview_hash = compute_preview_hash(preview)
        self._entries[preview_hash] = (preview, self._clock())
        return preview_hash

    def get_verified(self, preview_hash: str) -> DocumentPreview | None:
        """Look up by hash, expire on read, and re-verify the stored object's
        own hash still matches the key it is stored under before returning
        it — defense in depth against any future in-place mutation bug, not
        just a dict lookup."""
        entry = self._entries.get(preview_hash)
        if entry is None:
            return None
        preview, stored_at = entry
        if self._clock() - stored_at > self._ttl_seconds:
            del self._entries[preview_hash]
            return None
        if compute_preview_hash(preview) != preview_hash:
            del self._entries[preview_hash]
            return None
        return preview

    def _sweep_expired(self) -> None:
        now = self._clock()
        expired = [key for key, (_, stored_at) in self._entries.items() if now - stored_at > self._ttl_seconds]
        for key in expired:
            del self._entries[key]
