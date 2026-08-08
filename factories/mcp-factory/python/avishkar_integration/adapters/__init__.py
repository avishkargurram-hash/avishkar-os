"""Reference ProtocolAdapter implementations. `MCPAdapter` and
`RESTAdapter` are not re-exported from the package root (unlike
router.MockProvider) because MCPAdapter's default construction path
needs the optional `mcp` package -- import them explicitly:

    from avishkar_integration.adapters.mcp_adapter import MCPAdapter
    from avishkar_integration.adapters.rest_adapter import RESTAdapter
"""
