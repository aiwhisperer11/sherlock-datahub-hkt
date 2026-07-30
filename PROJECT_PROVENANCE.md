# Project provenance

This hackathon submission is a new DataHub-powered application and integration
layer built around Sherlock-Core, a pre-existing investigation engine created
and directed by Beatriz Linares Vázquez before the hackathon submission period.

Sherlock-Core retains the Sherlock name in this submission because it is the
investigation engine used by the project, not a reimplementation created for
the hackathon.

## What Sherlock-Core contributes

Sherlock-Core provides the falsification-driven investigation method and its
canonical investigation contract. Its pre-existing capabilities include:

- expectation-matrix analysis;
- competing hypotheses;
- explicit supporting and contradicting evidence;
- refutation criteria and hypothesis lifecycle management;
- ranked missing evidence;
- confidence and anomaly analysis;
- a discriminating next test; and
- evidence-driven follow-up investigations.

## What the hackathon project adds

The hackathon work adds the DataHub-specific application and integration layer,
including:

- acquisition of metadata evidence from DataHub;
- deterministic normalization into Sherlock's baseline evidence contract;
- provenance retained separately from the canonical investigation payload;
- exclusive provider selection and explicit fallback attempts;
- automatic validation against the packaged SherlockInvestigation 1.0.0
  contract; and
- the DataHub-facing backend and user experience.

The current backend boundary supports the intended acquisition order MCP Server
→ GraphQL → frozen snapshot. A frozen snapshot is explicitly marked as
non-live. The real remote Sherlock-Core service, its HTTP client, and the
end-to-end DataHub endpoint remain separate integration work until they are
actually implemented and verified.

DataHub supplies governed metadata context and evidence. Sherlock-Core remains
responsible for hypotheses, falsification, confidence, anomaly analysis, and
investigation follow-up.

The pre-existing Sherlock-Core work and the work created during the hackathon
are disclosed separately in [**PREEXISTING.md**](https://chatgpt.com/g/g-p-6a61d562f6f0819193e91f53eac7c7aa/c/PREEXISTING.md).
