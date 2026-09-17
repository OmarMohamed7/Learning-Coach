"""Connects to the mcp_servers/ servers and exposes their tools.

Servers are long-running processes reached over streamable-http — start each
one yourself (`python filesystem_server.py`, `python memory_server.py`) and
point this client at their URLs via settings.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from config.settings import settings

_tools_cache: list[BaseTool] | None = None

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

tools = []

def build_mcp_client() -> MultiServerMCPClient:
    """Build a client wired to every configured MCP server."""
    return MultiServerMCPClient(MCP_SERVERS) # type: ignore


async def get_mcp_tools() -> list[BaseTool]:
    """Connect to all configured MCP servers and return their tools.

    Each tool comes back as a LangChain BaseTool, ready to bind onto an
    agent or LangGraph node.
    """
    
    global _tools_cache
    if _tools_cache is None:
        client = build_mcp_client()
        _tools_cache =  await client.get_tools()

    return _tools_cache


def get_cached_tools() -> list[BaseTool]:
    """Return whatever tools are already cached, without connecting.

    Call `get_mcp_tools()` once at startup to populate the cache; call this
    from sync code afterwards to read it without an `await`.
    """
    return _tools_cache or []
