# 0001: Start with an offline sandbox provider

Date: 2026-07-23

The first Sherlock vertical slice uses a versioned JSON fixture through `SandboxMetadataProvider`. This makes the demo deterministic and lets the API and web UI establish a stable contract.

The `DataHubMetadataProvider` now supplies the Frozen Dashboard path with read-only MCP, GraphQL, and snapshot sources. Sandbox remains the default; live modes are opt-in and do not turn metadata into live freshness or execution evidence.
