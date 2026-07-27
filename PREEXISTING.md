# Pre-existing work disclosure

This document distinguishes work that existed before the hackathon submission
period from the new work developed for this DataHub hackathon submission.

## Pre-existing component: Sherlock-Core

Sherlock-Core is a pre-existing, falsification-driven investigation engine
created and directed by Beatriz Linares Vázquez before the hackathon submission
period.

The pre-existing work includes:

- the core investigation methodology;
- the canonical SherlockInvestigation contract and schema;
- the versioned investigation prompt and its investigation principles;
- expectation-matrix and anomaly analysis;
- competing-hypothesis generation and lifecycle management;
- explicit falsification and resurrection conditions;
- confidence, coherence, and open-case assessment;
- ranked missing evidence and selection of a discriminating next test;
- baseline and follow-up investigation modes;
- the Sherlock-Core **/api/investigate** interface;
- canonical response validation; and
- Sherlock example cases, fixtures, evaluation material, and its original user
  interface.

The baseline used for the DataHub integration is identified as:

Source repository: **https://github.com/aiwhisperer11/sherlock-engine**

Baseline commit: **d1c9f80ae6df0826a8399c6779b5cdc17e63b0be**

Canonical contract: **lib/investigation.schema.json**

Contract version used by DataHub: **SherlockInvestigation 1.0.0**

The packaged schema copy in the DataHub backend is recorded with SHA-256:

**3cad1ea054e1288f406a2463ce3b04819f863684ff78550f8676600df7cc0a1f**

This disclosure does not claim that Sherlock-Core was created from scratch
during the hackathon.

## Work developed for the hackathon

The hackathon project creates a new DataHub-powered application and integration
around Sherlock-Core. The work includes:

- DataHub-specific transport contracts;
- evidence acquisition through the configured DataHub providers;
- deterministic evidence normalization and sensitive-field redaction;
- provenance stored in parallel rather than added to Sherlock's canonical
  payload;
- provider selection in the order MCP Server → GraphQL → frozen snapshot,
  without mixing providers in one investigation;
- explicit, sanitized provider-attempt and fallback reporting;
- marking frozen snapshots as non-live;
- follow-up preparation without assigning evidence IDs that belong to
  Sherlock-Core;
- reconciliation of DataHub provenance with new evidence IDs returned by
  Sherlock-Core;
- automatic Draft 2020-12 validation of complete investigation responses;
- an explicit compatibility check for **schema_version == "1.0.0"**;
- DataHub backend integration and tests; and
- the DataHub-facing user experience.

At the time of this disclosure, the contract, normalization, provenance,
selection, follow-up, and canonical-validation boundary are implemented. The
remote Sherlock-Core service connection, injectable HTTP client, DataHub
investigation endpoint, and full vertical UI flow must not be described as
complete until they are implemented and verified.

## Third-party and open-source components

The submission uses DataHub and its interfaces under their applicable terms
and licenses. It also uses standard open-source frameworks and libraries
declared in the repository's dependency manifests. Each component remains
subject to its own license and attribution requirements.

OpenAI and Anthropic systems were used as AI-assisted development tools.
They are not human project contributors or co-authors.

## Ownership and license

Beatriz Linares Vázquez is the sole human developer and hackathon entrant.

Copyright 2026 Beatriz Linares Vázquez

The hackathon repository is licensed under the Apache License, Version 2.0, as
set out in [**LICENSE**](https://chatgpt.com/g/g-p-6a61d562f6f0819193e91f53eac7c7aa/c/LICENSE). Any separately licensed dependency remains
governed by its own license.
