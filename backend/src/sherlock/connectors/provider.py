from typing import Protocol

from sherlock.domain.models import Investigation


class MetadataProvider(Protocol):
    """Boundary for metadata sources used during an investigation."""

    def load_stale_pipeline_demo(self) -> Investigation:
        """Return the stale-pipeline investigation available from this source."""
