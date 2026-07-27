# DataHub → Sherlock-Core: first integration gate

DataHub owns acquisition, minimisation and provenance of read-only metadata.
Sherlock-Core alone owns the canonical `SherlockInvestigation` and all
investigative reasoning. The baseline sent to Sherlock contains only evidence
`id`, `label` and `content`; source references remain in a parallel provenance
object and are never added to a canonical investigation.

The adapter selects one source per request. `auto` tries MCP, GraphQL and then
the explicitly non-live snapshot, recording sanitized attempts. Metadata is
not proof of execution, data freshness or root cause.

`FrozenDashboardResult` remains a compatibility response for the current UI.
`DataHubInvestigationResponse` validates every response automatically against
the packaged Draft 2020-12 canonical schema, plus the required version
`1.0.0`. Source: `aiwhisperer11/sherlock-engine`,
`lib/investigation.schema.json`, commit
`d1c9f80ae6df0826a8399c6779b5cdc17e63b0be`; vendored SHA-256:
`3cad1ea054e1288f406a2463ce3b04819f863684ff78550f8676600df7cc0a1f`.
Structural validation does not establish that metadata is causally true.
Remote transport or embedded Sherlock-Core has not been added in this gate.
