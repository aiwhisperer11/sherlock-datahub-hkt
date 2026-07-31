import json
from pathlib import Path

from sherlock.integrations.sherlock_core.boundary import validate_unchanged


FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "investigations" / "governance_terms"


def load_snapshot(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def hypothesis(snapshot: dict, hypothesis_id: str) -> dict:
    return next(item for item in snapshot["hypotheses"] if item["id"] == hypothesis_id)


def test_governance_terms_snapshots_validate_against_canonical_schema() -> None:
    validate_unchanged(load_snapshot("iteration_1.json"))
    validate_unchanged(load_snapshot("iteration_2.json"))


def test_governance_terms_follow_up_preserves_evidence_and_hypothesis_ids() -> None:
    iteration_1 = load_snapshot("iteration_1.json")
    iteration_2 = load_snapshot("iteration_2.json")

    assert iteration_1["meta"]["case_id"] == iteration_2["meta"]["case_id"]
    assert {item["id"] for item in iteration_1["case"]["evidence"]} == {"E1", "E2", "E3", "E4", "E5"}
    assert [item["id"] for item in iteration_2["case"]["evidence"][:5]] == ["E1", "E2", "E3", "E4", "E5"]
    assert [item["id"] for item in iteration_2["case"]["evidence"][5:]] == ["E6", "E7", "E8", "E9"]
    assert all(item["provided_in_iteration"] == 2 for item in iteration_2["case"]["evidence"][5:])
    assert {item["id"] for item in iteration_1["hypotheses"]} == {item["id"] for item in iteration_2["hypotheses"]}


def test_governance_terms_iteration_2_preserves_conservative_conclusions() -> None:
    iteration_2 = load_snapshot("iteration_2.json")
    h1 = hypothesis(iteration_2, "H1")
    h2 = hypothesis(iteration_2, "H2")

    assert h1["status"] == "active"
    assert h2["status"] == "rejected"
    assert h2["confidence"] == 6
    assert h2["killed_by"] is None
    assert set(iteration_2["next_test"]) == {"description", "discriminates_between", "outcome_map"}
    assert "solo lectura" in iteration_2["next_test"]["description"].lower()
    assert any(word in iteration_2["next_test"]["description"].lower() for word in ("audit", "procedencia"))

    rendered = json.dumps(iteration_2, ensure_ascii=False).lower()
    assert "causa única global" not in rendered
    assert "incidente operativo" not in rendered
    assert "propagación automática" not in rendered
    assert "no se ha demostrado asignación a nivel de campo" in rendered
