import json
from pathlib import Path

from sherlock.domain.models import Investigation


class SandboxMetadataProvider:
    """Loads deterministic demo data from a local JSON snapshot."""

    def __init__(self, fixture_path: Path | None = None) -> None:
        self.fixture_path = fixture_path or Path(__file__).resolve().parent / "fixtures" / "stale_pipeline_demo.json"

    def load_stale_pipeline_demo(self) -> Investigation:
        with self.fixture_path.open(encoding="utf-8") as fixture:
            return Investigation.model_validate(json.load(fixture))
