from fastapi.testclient import TestClient

from sherlock.api.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_stale_pipeline_demo() -> None:
    response = client.get("/api/v1/demo/stale-pipeline")

    assert response.status_code == 200
    assert response.json()["title"] == "The Case of the Stale Pipeline"
    assert response.json()["hypotheses"][0]["confidence"]["score"] == 0.769


def test_allows_local_frontend_origin() -> None:
    response = client.get(
        "/api/v1/demo/stale-pipeline",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
