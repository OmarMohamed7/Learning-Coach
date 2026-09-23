
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
import uuid

from graph.state import StudyRoadmap, initial_state, session_is_complete
from observability.langfuse_setup import flush_langfuse, get_langfuse_config
import uvicorn
from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from mcp_client.client import get_mcp_tools
from logger import get_logger
from fastapi import FastAPI
from database import engine, OrmBase, AsyncSessionLocal, CHECKPOINT_DB_URL
from models import create_new_version, get_latest_version, get_agents
from graph.workflow import compile_graph
from langgraph.types import Command
from langfuse import get_client


load_dotenv()

logger = get_logger(__name__)

ALL_AGENT_NAMES = [
    "curriculum_planner",
    "human_approval",
    "explainer",
    "quiz_generator",
    "progress_coach",
]



def export_graph_image(graph):
    try:
        png_bytes = graph.get_graph().draw_mermaid_png()
        with open("graph_structure.png", "wb") as f:
            f.write(png_bytes)

        logger.critical("🤖 Graph visualization successfully saved as 'graph_structure.png'")

    except Exception as e:
        logger.error(f"Could not render graph via mermaid: {e}")


@asynccontextmanager
async def startup():
    """
    Shared startup: DB init, agent version seeding, MCP tool warmup, and
    checkpointer/graph compilation. Yields the compiled graph.

    Used by both the FastAPI `lifespan` (server mode) and `run_session`
    (CLI mode) so there's a single source of truth for how the graph gets
    built — no duplicated setup, no divergence between the two entry points.
    """
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
    logger.info(f"[Main] tools [{(t.name for t in tools)}]")

    if len(tools) <=0:
        logger.error("[Main] No Tools found")

    logger.info("[Main] Setting up LangGraph Postgres checkpointer...")
    async with AsyncExitStack() as stack:
        checkpointer = await stack.enter_async_context(
            AsyncPostgresSaver.from_conn_string(CHECKPOINT_DB_URL)
        )
        await checkpointer.setup()  # creates checkpoint tables if they don't exist yet

        graph = compile_graph(checkpointer)
        export_graph_image(graph)
        logger.info("[Main] Graph compiled with checkpointer.")

        yield graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with startup() as graph:
        app.state.graph = graph
        yield

app = FastAPI(lifespan=lifespan)

   
async def run_session(graph, goal: str, session_id: str | None = None) -> None:
    """ Run a complete interactive study session"""
    is_resume = session_id is not None
    
    if not session_id:
        session_id = str(uuid.uuid4())[:8]
        
    if is_resume:
        logger.info("Resuming existing session...")
    else:
        logger.info(f"Goal: {goal}")
    logger.info(f"{'='*60}")
    
    state = None if is_resume else initial_state(goal, session_id)

    config = get_langfuse_config(session_id)

    logger.info(f"[Config] : {config}")

    try:
        result = await graph.ainvoke(state, config=config)
    except Exception as e:
        if is_resume:
            print(f"\n[ERROR] Could not resume session '{session_id}': {e}")
            print("If the session ID is wrong or the checkpoint database has been deleted, start a new session instead.")
            return
        raise

    while "__interrupt__" in result:
        # Fresh config (and Langfuse handler) per resume: each ainvoke() runs
        # in its own async context, and interrupt()'s exception-based unwind
        # leaves the previous handler's OTel span half-closed. Reusing one
        # handler across resumes causes "context was created in a different
        # Context" errors when it tries to detach a token from a dead context.
        config = get_langfuse_config(session_id)
        interrupt_payload = result["__interrupt__"][0].value

        if interrupt_payload.get("type") == "quiz_question":
            logger.info(
                f"Question {interrupt_payload['index']}/{interrupt_payload['total']} "
                f"[{interrupt_payload.get('difficulty', 'medium')}]: {interrupt_payload['question']}"
            )
            user_input = input(f"{interrupt_payload.get('prompt', 'Your answer:')} ").strip()
            result = await graph.ainvoke(Command(resume=user_input), config=config) # type: ignore
            continue

        raw_roadmap = interrupt_payload.get("roadmap")
        roadmap = (
            StudyRoadmap.from_dict(raw_roadmap) # type: ignore
            if isinstance(raw_roadmap, dict)
            else raw_roadmap
        )
        

        # Display the roadmap for approval
        if roadmap:
            logger.info(f"\n{'='*60}")
            logger.info("Proposed Study Plan")
            logger.info(f"{'='*60}")
            logger.info(f"Goal: {roadmap.goal}")
            logger.info(f"Duration: {roadmap.total_weeks} weeks @ "
                    f"{roadmap.weekly_hours} hrs/week\n")
            for i, topic in enumerate(roadmap.topics, 1):
                prereqs = (f" (needs: {', '.join(topic.prerequisites)})"
                            if topic.prerequisites else "")
                logger.info(f"  {i}. {topic.title} "
                        f"({topic.estimated_minutes} min){prereqs}")
                logger.info(f"     {topic.description}")

        logger.info(f"\n{interrupt_payload.get('prompt', 'Continue?')}")
        user_input = input("> ").strip()

        # Resume the graph with the user's decision
        result = await graph.ainvoke(Command(resume=user_input), config=config) # type: ignore

    # ── Handle errors ─────────────────────────────────────────────────
    if result.get("error"):
        logger.info(f"\n[ERROR] {result['error']}")
        return

    roadmap = result.get("roadmap")
    if roadmap is not None and session_is_complete({"roadmap": roadmap, "current_topic_index": result.get("current_topic_index", 0)}):
        logger.info(f"\n[Session '{session_id}'] Already complete — all topics finished.")
    else:
        logger.info(f"\n[Session '{session_id}'] Stopped with no pending interrupt or error.")
    logger.info(f"Final state: { {k: v for k, v in result.items() if k != 'messages'} }")
    
    # Flushes befor exiting
    flush_langfuse()

    
    
async def run_cli_session(goal: str, session_id: str | None) -> None:
    """CLI mode: build the graph via `startup()` directly (no ASGI server involved),
    then run/resume a single interactive session through it."""
    async with startup() as graph:
        await run_session(graph, goal=goal, session_id=session_id)


if __name__ == "__main__":
    import argparse
    
    langfuse = get_client()

    if langfuse.auth_check():
        logger.info("Langfuse connected!")

    parser = argparse.ArgumentParser(
        description=(
            "Learning Coach: a four-agent study system that plans a "
            "curriculum, explains topics from your notes, quizzes you, and "
            "adapts based on results. All inference runs locally via Ollama."
        ),
        epilog=(
            "Examples:\n"
            "  python main.py \"Learn Python closures\"\n"
            "  python main.py --resume a3f1b2c4\n"
            "  python main.py --serve\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("goal", nargs="?", default="Learn Python closures")
    parser.add_argument("--resume", metavar="SESSION_ID", help="Resume an existing session by ID")
    parser.add_argument("--serve", action="store_true", help="Run as the FastAPI/uvicorn API server instead of a CLI session")

    args = parser.parse_args()

    if args.serve:
        uvicorn.run(app="main:app", host="0.0.0.0", port=8000, reload=True)
    elif args.resume:
        asyncio.run(run_cli_session(goal="", session_id=args.resume))
    else:
        asyncio.run(run_cli_session(goal=args.goal, session_id=None))
        
