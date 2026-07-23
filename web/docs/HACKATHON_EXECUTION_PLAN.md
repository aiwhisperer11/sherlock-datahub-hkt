# Hackathon Execution Plan — Web Track

The frontend delivers the investigation view for **The Case of the Stale Pipeline**. It stays independently deployable from the backend and communicates through the documented REST API only.

## P0

- Connection state for Sherlock Engine.
- Incident, affected assets, hypotheses, evidence, confidence, and recommendation.
- Loading, success, and error states for the sandbox API.
- A layout that can later incorporate an evidence graph and timeline.

## P1

- Evidence timeline.
- Two-run comparison.
- DataHub deep links.
- JSON and Markdown export.

The existing component boundaries in `src/features/investigation/` intentionally keep those enhancements separate from the dashboard shell. React Flow is not included until the graph interaction requirements are defined.

See [UI architecture](UI_ARCHITECTURE.md), [setup](SETUP.md), and [deployment notes](DEPLOYMENT.md).
