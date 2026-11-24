"""App startup: database tables, agent versions, MCP tools and the compiled graph."""
from contextlib import AsyncExitStack, asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from chainlit_tables import create_chainlit_tables
from database import CHECKPOINT_DB_URL, AsyncSessionLocal, OrmBase, engine
from graph.workflow import compile_graph
from logger import get_logger
from mcp_client.client import get_mcp_tools
from models import create_new_version, get_agents, get_latest_version
import usage_limit  # noqa: F401  (registers the goal_usage table for create_all)

logger = get_logger(__name__)

ALL_AGENT_NAMES = ["curriculum_planner", "human_approval", "explainer", "quiz_generator", "progress_coach"]


def export_graph_image(graph) -> None:
    try:
        with open("graph_structure.png", "wb") as f:
            f.write(graph.get_graph().draw_mermaid_png())
        logger.info("Graph visualization saved as 'graph_structure.png'")
    except Exception as e:
        logger.error(f"Could not render graph via mermaid: {e}")


async def _seed_agents() -> None:
    async with AsyncSessionLocal() as session:
        existing = set(await get_agents(session=session))
        missing = [name for name in ALL_AGENT_NAMES if name not in existing]
        if missing:
            logger.info("[Startup] Seeding missing agents: %s", missing)
        for name in ALL_AGENT_NAMES:
            latest = await get_latest_version(session, name) or await create_new_version(session, name)
            logger.info(f"[Startup] {name} -> v{latest.version}")


@asynccontextmanager
async def startup():
    """Prepare everything the app needs and yield the compiled graph."""
    async with engine.begin() as conn:
        await conn.run_sync(OrmBase.metadata.create_all)
    await create_chainlit_tables(engine)
    await _seed_agents()

    tools = await get_mcp_tools()
    if not tools:
        logger.error("[Startup] No MCP tools found")

    async with AsyncExitStack() as stack:
        checkpointer = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(CHECKPOINT_DB_URL))
        await checkpointer.setup()
        graph = compile_graph(checkpointer)
        export_graph_image(graph)
        logger.info("[Startup] Graph compiled with checkpointer.")
        yield graph
