"""Connects to the mcp_servers/ servers and exposes their tools.

Servers are long-running processes reached over streamable-http — start each
one yourself (`python filesystem_server.py`, `python memory_server.py`) and
point this client at their URLs via settings.
"""

from __future__ import annotations

import os
import time
from urllib.parse import urlsplit

import httpx
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from config.settings import settings

_tools_cache: list[BaseTool] | None = None


class GoogleIdTokenAuth(httpx.Auth):
    """Adds a Google-signed ID token to each request, so a private Cloud Run service lets it in.

    The token is minted for the service's base URL (its audience) from the runtime service account,
    and refreshed shortly before its one-hour expiry.
    """

    def __init__(self, url: str):
        parts = urlsplit(url)
        self.audience = f"{parts.scheme}://{parts.netloc}"
        self._token: str | None = None
        self._expires_at = 0.0

    def _get_token(self) -> str:
        if self._token is None or time.time() > self._expires_at - 300:
            import google.auth.transport.requests
            import google.oauth2.id_token

            token = google.oauth2.id_token.fetch_id_token(
                google.auth.transport.requests.Request(), self.audience
            )
            if not token:
                raise RuntimeError(f"Could not get a Google ID token for {self.audience}")
            self._token, self._expires_at = token, time.time() + 3600
            return token
        return self._token

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self._get_token()}"
        yield request


def _server(url: str) -> dict:
    conn: dict = {"transport": "streamable_http", "url": url}
    # On Cloud Run the MCP services are private (no unauthenticated access): MCP_AUTH=google turns on ID tokens.
    if os.getenv("MCP_AUTH", "").lower() == "google":
        conn["auth"] = GoogleIdTokenAuth(url)
    return conn


MCP_SERVERS: dict[str, dict] = {
    "filesystem": _server(settings.mcp_filesystem_url),
    "memory": _server(settings.mcp_memory_url),
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
