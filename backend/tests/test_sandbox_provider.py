from sherlock.connectors.sandbox import SandboxMetadataProvider


def test_loads_demo_fixture() -> None:
    investigation = SandboxMetadataProvider().load_stale_pipeline_demo()

    assert investigation.incident.id == "incident-stale-nyc-taxi"
    assert len(investigation.assets) == 3
    assert investigation.hypotheses[0].confidence.score == 0.769
