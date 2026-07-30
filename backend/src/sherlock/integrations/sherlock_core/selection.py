"""Pure, exclusive provider selection with explicit fallback attempts."""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping

from sherlock.domain.models import DataHubObservation
from .contracts import EvidenceProvider, ProviderAttempt

_ORDER: tuple[EvidenceProvider, ...] = ("mcp", "graphql", "snapshot")

def select_observation(mode: str, fetchers: Mapping[EvidenceProvider, Callable[[], DataHubObservation]]) -> tuple[DataHubObservation, EvidenceProvider, list[ProviderAttempt]]:
    normalized_mode = "snapshot" if mode == "sandbox" else mode
    order = _ORDER if normalized_mode == "auto" else (normalized_mode,)
    attempts: list[ProviderAttempt] = []
    for provider in order:
        if provider not in _ORDER or provider not in fetchers:
            raise ValueError("unsupported or unavailable metadata provider")
        try:
            observed = fetchers[provider]()  # exactly one successful provider is selected
        except Exception as error:
            attempts.append(ProviderAttempt(provider=provider, status="failed", error_code="metadata_unavailable", message=_sanitize(str(error))))
            if normalized_mode != "auto":
                raise
        else:
            attempts.append(ProviderAttempt(provider=provider, status="succeeded"))
            return observed, provider, attempts
    raise RuntimeError("no metadata provider returned evidence")

def _sanitize(message: str) -> str:
    return re.sub(r"(?i)\b(bearer|token|password|secret|api[_ -]?key)\b\s*[:=]?\s*[^\s,;]+", r"\1 [redacted]", " ".join(message.split()))[:512]
