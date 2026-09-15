"""Connects to the mcp_servers/ servers and exposes their tools.

Servers are long-running processes reached over streamable-http — start each
one yourself (`python filesystem_server.py`, `python memory_server.py`) and
point this client at their URLs via settings.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from config.settings import settings

MCP_SERVERS: dict[str, dict] = {
    "filesystem": {
        "transport": "streamable_http",
        "url": settings.mcp_filesystem_url,
    },
    "memory": {
        "transport": "streamable_http",
        "url": settings.mcp_memory_url,
    },
}


def build_mcp_client() -> MultiServerMCPClient:
    """Build a client wired to every configured MCP server."""
    return MultiServerMCPClient(MCP_SERVERS)


async def get_mcp_tools() -> list[BaseTool]:
    """Connect to all configured MCP servers and return their tools.

    Each tool comes back as a LangChain BaseTool, ready to bind onto an
    agent or LangGraph node.
    """
    client = build_mcp_client()
    return await client.get_tools()
