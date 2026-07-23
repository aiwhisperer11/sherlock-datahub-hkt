# DataHub Integration Plan

## Current status

No live DataHub or MCP connection is implemented. `DataHubMetadataProvider` is intentionally a skeleton. This prevents a demo fixture from being misrepresented as live metadata.

## Capability gate

Before implementing an adapter, run a local DataHub Quickstart and inspect the installed DataHub MCP server. Record the actual tool names and confirm which of these are available:

1. Asset metadata: schema, owners, tags, last-modified time.
2. Upstream and downstream lineage.
3. Freshness, assertions, incidents, and data-quality signals.
4. Stable DataHub URLs that can be retained as evidence links.

The selected NYC Taxi asset URN must be discovered from the running DataHub instance, never hardcoded from an assumption.

## Proposed adapter responsibilities

| Concern | Adapter output |
| --- | --- |
| Asset reader | name, platform, type, schema, ownership, tags, last modified |
| Lineage reader | structured upstream/downstream assets with graph depth |
| Freshness reader | observed timestamp, lag, SLA context, source link |
| Evidence mapper | traceable `Evidence` with source and reliability |

## Fallback rule

If live metadata cannot be read during a demo, return a snapshot explicitly labelled with `is_snapshot`, `snapshot_timestamp`, and a human-readable note. Do not silently substitute fixture data for a live response.

## Security

Credentials stay out of the repository. Any future URL or token is supplied through documented environment variables only; `.env` files remain ignored.
