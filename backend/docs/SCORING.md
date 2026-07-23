# Confidence Scoring

The implemented scoring formula is deliberately explainable:

```text
confidence = evidence_coverage × source_reliability × consistency × lineage_proximity
```

All components are constrained to `[0, 1]` and returned alongside the computed score. This lets a reviewer see why a hypothesis is strong or weak without relying on an opaque model.

| Component | Meaning |
| --- | --- |
| `evidence_coverage` | How much relevant evidence has been collected |
| `source_reliability` | Trustworthiness of the evidence source |
| `consistency` | Whether independent evidence agrees |
| `lineage_proximity` | Closeness of evidence to the affected asset |

The execution-plan draft also contained a weighted-average alternative. The multiplicative formula is the current source of truth because it matches the initial product contract and appropriately penalizes a missing or weak evidence dimension. A future status mapping and contradiction penalty must be documented and tested before it is added.

Insufficient or conflicting evidence should lead to an `inconclusive` conclusion rather than artificial confidence.
