from sherlock.domain.models import Investigation


class DataHubMetadataProvider:
    """Future adapter for DataHub MCP; deliberately non-functional in this MVP."""

    def load_stale_pipeline_demo(self) -> Investigation:
        # TODO: Inject an authenticated DataHub MCP client and map its responses.
        raise NotImplementedError("DataHub MCP integration is not implemented in the sandbox MVP")
