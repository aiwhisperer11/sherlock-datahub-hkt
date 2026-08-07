"""Real HTTP transport to the Sherlock-Core canonical investigation engine.

This did not exist before: SHERLOCK_CORE_INTEGRATION.md explicitly recorded
"Remote transport or embedded Sherlock-Core has not been added in this gate."
No prior environment variable name exists anywhere in this repository for it
(verified by grep before adding this module) — SHERLOCK_CORE_URL is new and
is documented here and in SHERLOCK_CORE_INTEGRATION.md.

When unset, the engine is treated as not configured; callers must fall back
to a clearly disclosed local path (see datahub_document_flow.py) rather than
fabricate an engine response. This module never invents a response either —
a transport failure always raises.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from .contracts import SherlockBaselineRequest


class SherlockCoreUnavailableError(RuntimeError):
    """Sherlock-Core could not be reached, timed out, or returned a non-JSON body."""


class SherlockCoreClient:
    # 90s, not 30s: measured against the real deployed engine
    # (https://sherlock-engine.vercel.app), a 1-evidence-item smoke test
    # returned in ~15s, but a real 4-item DataHub baseline (the shape this
    # flow actually sends) took long enough to exceed 30s and hit
    # TimeoutError — the LLM does more reasoning work per evidence item.
    # Still fully overridable via SHERLOCK_CORE_TIMEOUT_SECONDS.
    def __init__(self, base_url: str | None, timeout_seconds: float = 90.0) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> SherlockCoreClient:
        return cls(
            base_url=os.getenv("SHERLOCK_CORE_URL") or None,
            timeout_seconds=float(os.getenv("SHERLOCK_CORE_TIMEOUT_SECONDS", "90")),
        )

    @property
    def configured(self) -> bool:
        return self.base_url is not None

    def run_baseline_investigation(self, request: SherlockBaselineRequest) -> dict[str, Any]:
        """POST {base_url}/api/investigate; returns the raw parsed JSON body.

        Does not validate the response against the canonical schema — that is
        the caller's job (sherlock.integrations.sherlock_core.boundary), kept
        separate so a transport failure and a schema-conformance failure are
        never confused with each other in the caller's error handling.
        """
        if self.base_url is None:
            raise SherlockCoreUnavailableError("SHERLOCK_CORE_URL is not configured")
        payload = json.dumps(request.model_dump(mode="json", exclude_none=True)).encode()
        http_request = Request(
            f"{self.base_url}/api/investigate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=self.timeout_seconds) as response:  # noqa: S310 - operator-configured Sherlock-Core endpoint
                body = json.loads(response.read())
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise SherlockCoreUnavailableError("Sherlock-Core investigation request failed") from error
        if not isinstance(body, dict):
            raise SherlockCoreUnavailableError("Sherlock-Core returned an unexpected response shape")
        return body
