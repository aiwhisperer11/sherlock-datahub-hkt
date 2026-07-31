# Governance terms investigation

This fixture preserves a real Sherlock investigation into a metadata-quality
contradiction: the operational `inventories` and `warehouses` assets have the
`PII`, `Order Total`, and `Revenue by Customer Class` glossary terms, while
the captured descriptions and schemas do not visibly explain the order and
customer terms.

Iteration 1 records the contradiction and competing explanations. Iteration 2
uses previously captured lineage and asset-term evidence to distinguish a
localized mismatch in `inventories` from a repeated pattern in the
`warehouses` branch. It does not establish one global root cause.

No mutation or ingestion was performed to create these fixtures. They are
Sherlock results derived from previously captured live metadata; they do not,
by themselves, demonstrate an MCP execution. Any raw MCP responses are kept
separately from these derived investigation snapshots.

`manifest.json` records the canonical schema, validation status, and immutable
SHA-256 digests for both snapshots.
