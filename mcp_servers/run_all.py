"""Runs both MCP servers in one process on 127.0.0.1 (for single-container hosts)."""
import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("MCP_HTTP_HOST", "127.0.0.1")
os.environ.pop("MCP_HTTP_PORT", None)

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / "file_server_mcp"), str(HERE / "memory_server_mcp")]

import filesystem_server  # noqa: E402
import memory_server  # noqa: E402


async def main() -> None:
    await asyncio.gather(
        filesystem_server.mcp.run_streamable_http_async(),
        memory_server.mcp.run_streamable_http_async(),
    )


if __name__ == "__main__":
    asyncio.run(main())
