
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from mcp_client.client import get_mcp_tools, _tools_cache
from logger import get_logger
from src.config import settings
from fastapi import FastAPI

load_dotenv()

logger = get_logger(__name__)

def main():
    logger.info("Hello from Learning Coach!")
    logger.info("Ollama base URL: %s", settings.ollama_base_url)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("[Main] Getting tools...")
    await get_mcp_tools()
    tools = _tools_cache
    logger.info(f"[Main] tools {tools}")
    
    yield
    
app = FastAPI(lifespan=lifespan)
    
if __name__ == "__main__":
    main()
