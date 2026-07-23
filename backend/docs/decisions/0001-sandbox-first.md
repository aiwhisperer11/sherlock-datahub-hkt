# 0001: Start with an offline sandbox provider

Date: 2026-07-23

The first Sherlock vertical slice uses a versioned JSON fixture through `SandboxMetadataProvider`. This makes the demo deterministic and lets the API and web UI establish a stable contract before a real DataHub MCP integration is introduced.

The `MetadataProvider` protocol is the boundary for that later work. The DataHub implementation intentionally raises `NotImplementedError` rather than implying external connectivity.
