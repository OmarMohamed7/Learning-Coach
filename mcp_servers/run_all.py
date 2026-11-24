"""Runs the filesystem (8001) and memory (8002) MCP servers in ONE process.

Used by single-container hosts (Render free tier, 512 MB) where a second Python process would cost
~60 MB. Both servers bind 127.0.0.1, so only the app in the same container can reach them.
Run from the directory that holds study_materials/ (NOTES_PATH is relative to the working dir).
"""
import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("MCP_HTTP_HOST", "127.0.0.1")
os.environ.pop("MCP_HTTP_PORT", None)  # each server keeps its own default port (8001 / 8002)

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
