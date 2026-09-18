
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator

import uvicorn
from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from mcp_client.client import get_mcp_tools
from logger import get_logger
from src.config import settings
from fastapi import FastAPI
from database import engine, OrmBase, AsyncSessionLocal, CHECKPOINT_DB_URL
from models import create_new_version, get_latest_version, get_agents
from graph.workflow import compile_graph

load_dotenv()

logger = get_logger(__name__)

ALL_AGENT_NAMES = [
    "curriculum_planner",
    "human_approval",
    "explainer",
    "quiz_generator",
    "progress_coach",
]

def export_graph_image():
    try:
        png_bytes = app.state.graph.get_graph().draw_mermaid_png()
        with open("graph_structure.png", "wb") as f:
            f.write(png_bytes)
        
        logger.critical("🤖 Graph visualization successfully saved as 'graph_structure.png'")
        
    except Exception as e:
        logger.error(f"Could not render graph via mermaid: {e}")
    

@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Hello from Learning Coach!\n")
    logger.info("[Main] Connecting to database...\n")
    async with engine.begin() as conn:
        await conn.run_sync(OrmBase.metadata.create_all)
    
    logger.info("[Main] Getting Agents and ensuring each agent has a version...")
    async with AsyncSessionLocal() as session:
        existing = set(await get_agents(session=session))
        missing = [name for name in ALL_AGENT_NAMES if name not in existing]
        if missing:
            logger.info("[Main] Seeding missing agents: %s", missing)

        for name in ALL_AGENT_NAMES:
            latest = await get_latest_version(session, name)
            if latest is None:
                latest = await create_new_version(session, name)
            logger.info(f"[Main] {name} -> v{latest.version}")
            
            
    logger.info("[Main] Getting tools...")
    tools = await get_mcp_tools()
    logger.info(f"[Main] tools {tools}")
    
    if len(tools) <=0:
        logger.error("[Main] No Tools found")

    logger.info("[Main] Setting up LangGraph Postgres checkpointer...")
    async with AsyncExitStack() as stack:
        checkpointer = await stack.enter_async_context(
            AsyncPostgresSaver.from_conn_string(CHECKPOINT_DB_URL)
        )
        await checkpointer.setup()  # creates checkpoint tables if they don't exist yet

        app.state.graph = compile_graph(checkpointer)
        
        # Export graph image
        export_graph_image()
        
        logger.info("[Main] Graph compiled with checkpointer.")

        yield

app = FastAPI(lifespan=lifespan)

    
if __name__ == "__main__":
    uvicorn.run(app="main:app", host="0.0.0.0", port=8000, reload=True)
