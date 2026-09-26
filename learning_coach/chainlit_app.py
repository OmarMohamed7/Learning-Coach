"""Learning Coach entry point (Chainlit UI). Run from learning_coach/: uv run chainlit run chainlit_app.py

The Chainlit thread id doubles as the LangGraph thread_id (the first goal of a chat uses it as-is; later goals
in the same chat get `<thread id>:<suffix>`), so reopening a past conversation resumes the graph from its checkpoint.
"""
import asyncio
import uuid
from contextlib import AsyncExitStack, asynccontextmanager

import chainlit as cl
from chainlit.auth import get_current_user
from chainlit.server import app as chainlit_server
from fastapi import Depends
from sqlalchemy import text
from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

load_dotenv()

import register  # noqa: F401  (adds the /register page to Chainlit's server)
from auth import authenticate
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit_tables import create_chainlit_tables
from database import CHECKPOINT_DB_URL, DATABASE_URL, OrmBase, AsyncSessionLocal, engine
from graph.workflow import compile_graph
from mcp_client.client import get_mcp_tools
from models import create_new_version, get_agents, get_latest_version
from agents.explainer.explainer import STREAM_TAG
from graph.state import StudyRoadmap, initial_state
from logger import get_logger
from observability.langfuse_setup import flush_langfuse, get_langfuse_config

logger = get_logger(__name__)

ASK_TIMEOUT_SECONDS = 3600

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

    Called once from `on_app_startup` when the Chainlit server boots.
    """
    logger.info("Hello from Learning Coach!\n")
    logger.info("[Main] Connecting to database...\n")
    async with engine.begin() as conn:
        await conn.run_sync(OrmBase.metadata.create_all)
    await create_chainlit_tables(engine)

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

# AsyncExitStack handles non-blocking I/O. 
# It is used when your resources rely on async def __aenter__ and async def __aexit__ 
# like an aiohttp client session or an asyncpg database pool connection.
_stack = AsyncExitStack()
_graph = None


@cl.data_layer
def sql_data_layer():
    # Persists threads/steps so the sidebar can list past chats and resume them.
    return SQLAlchemyDataLayer(conninfo=DATABASE_URL)


@cl.password_auth_callback  # type: ignore
async def auth_callback(username: str, password: str):
    user = await authenticate(username, password)
    if user is None:
        return None
    return cl.User(identifier=user.username, metadata={"role": "user"})


@cl.on_app_startup
async def on_app_startup():
    global _graph
    _graph = await _stack.enter_async_context(startup())


@cl.on_app_shutdown
async def on_app_shutdown():
    await _stack.aclose()


def _graph_tid() -> str:
    return cl.user_session.get("graph_tid") or cl.context.session.thread_id


def _config():
    user = cl.user_session.get("user")
    return get_langfuse_config(
        _graph_tid(),
        user_id=user.identifier if user else "anonymous",
    )


def _format_roadmap(roadmap: StudyRoadmap) -> str:
    lines = [
        "### Proposed Study Plan",
        f"**Goal:** {roadmap.goal}",
        f"**Duration:** {roadmap.total_weeks} weeks @ {roadmap.weekly_hours} hrs/week",
        "",
    ]
    for i, topic in enumerate(roadmap.topics, 1):
        prereqs = f" _(needs: {', '.join(topic.prerequisites)})_" if topic.prerequisites else ""
        lines.append(f"{i}. **{topic.title}** ({topic.estimated_minutes} min){prereqs}")
        lines.append(f"   {topic.description}")
    return "\n".join(lines)


async def _ask(payload: dict) -> str | None:
    """Show an interrupt payload and return the user's reply (None on timeout).

    Roadmap approval uses Approve/Reject buttons; quiz questions take typed answers.
    """
    if payload.get("type") == "quiz_question":
        content = (
            f"**Question {payload['index']}/{payload['total']}** "
            f"[{payload.get('difficulty', 'medium')}]\n\n{payload['question']}"
        )
        reply = await cl.AskUserMessage(content=content, timeout=ASK_TIMEOUT_SECONDS).send()
        return reply["output"].strip() if reply else None  # type: ignore
    else:
        raw = payload.get("roadmap")
        roadmap = StudyRoadmap.from_dict(raw) if isinstance(raw, dict) else raw  # type: ignore
        # Sent as its own message: AskActionMessage replaces its text with "Selected: ..." after a click,
        # which would otherwise erase the roadmap from the chat.
        if roadmap:
            await cl.Message(_format_roadmap(roadmap)).send()
        choice = await cl.AskActionMessage(
            content="Does this study plan suit you?",
            actions=[
                cl.Action(name="approve", payload={"value": "yes"}, label="✅ Approve"),
                cl.Action(name="reject", payload={"value": "no"}, label="❌ Reject"),
            ],
            timeout=ASK_TIMEOUT_SECONDS,
        ).send()
        return choice["payload"]["value"] if choice else None


STAGE_DONE = {
    "curriculum_planner": "Study roadmap drafted",
    "human_approval": "Plan reviewed",
    "explainer": "Explanation prepared from your notes",
    "quiz_generator": "Quiz questions generated",
    "quiz_question": "Answer graded",
    "progress_coach": "Progress reviewed",
}


def _format_explanation(explanation: dict) -> str:
    return (
        f"### 📘 Topic {explanation['index']}/{explanation['total']}: {explanation['topic']}\n\n"
        f"{explanation['text']}"
    )


def _format_grade(grade: dict) -> str:
    icon = "✅" if grade["correct"] else "❌"
    text = f"{icon} **Question {grade['index']}/{grade['total']} — score: {grade['score']:.0%}**"
    if grade.get("feedback"):
        text += f"\n\n{grade['feedback']}"
    return text


def _format_coach_note(note: dict) -> str:
    text = f"### 🎯 Progress Coach — {note['topic']}: {note['score']:.0%}\n\n{note['summary']}"
    if note.get("encouragement"):
        text += f"\n\n_{note['encouragement']}_"
    if note.get("next_topic"):
        text += f"\n\n**Up next:** {note['next_topic']}"
    else:
        text += "\n\n🎉 **You've finished every topic in your roadmap!**"
    return text


# Graph node -> (state key it writes for display, formatter)
DISPLAYED = {
    "explainer": ("explanation", _format_explanation),
    "quiz_question": ("last_grade", _format_grade),
    "progress_coach": ("coach_note", _format_coach_note),
}


async def _run(graph_input) -> dict:
    """Run the graph until it finishes or hits an interrupt.

    Shows a spinner step that lists each stage as it completes. Returns the same shape
    `ainvoke` did: the final state, or {"__interrupt__": ...} when waiting for the user.
    """
    config = _config()
    interrupt = None
    done: list[str] = []
    posts: list[str] = []
    live: cl.Message | None = None  # the explanation while it is being written

    async def flush_posts():
        # Posted in graph order (e.g. the grade, then the coach note) before the next explanation starts.
        for post in posts:
            await cl.Message(post).send()
        posts.clear()

    async with cl.Step(name="Working on it...", type="run", show_input=True) as step:
        async for mode, data in _graph.astream(  # type: ignore
            graph_input, config=config, stream_mode=["updates", "messages"] # type: ignore
        ):
            if mode == "messages":
                chunk, meta = data
                token = chunk.content # type: ignore
                if STREAM_TAG not in (meta.get("tags") or []) or not isinstance(token, str) or not token: # type: ignore
                    continue
                if live is None:
                    await flush_posts()
                    live = cl.Message(content="")
                    live.parent_id = None  # show it in the chat, not inside the collapsed step
                    await live.send()
                await live.stream_token(token)
                continue

            for node, value in data.items(): # type: ignore
                if node == "__interrupt__":
                    interrupt = value
                    continue
                done.append(f"✅ {STAGE_DONE.get(node, node)}")
                step.output = "\n".join(done)
                await step.update()
                if node in DISPLAYED:
                    key, fmt = DISPLAYED[node]
                    if (value or {}).get(key):
                        if node == "explainer" and live is not None:
                            live.content = fmt(value[key])  # swap in the final text with its topic header
                            await live.update()
                            live = None
                        else:
                            posts.append(fmt(value[key]))

    await flush_posts()

    if interrupt is not None:
        return {"__interrupt__": interrupt}
    return (await _graph.aget_state(config)).values  # type: ignore


async def _drive(graph_input) -> None:
    """Run the graph, answering each interrupt through the chat until it finishes."""
    result = await _run(graph_input)

    while "__interrupt__" in result:
        answer = await _ask(result["__interrupt__"][0].value)
        if answer is None:
            await cl.Message("Timed out waiting for your reply. Reopen this chat from the history to continue.").send()
            return
        # Fresh config per run (fresh Langfuse handler): each run happens in its own async context, and reusing a
        # handler across interrupt resumes breaks OTel context detach.
        result = await _run(Command(resume=answer))

    if result.get("error"):
        await cl.Message(f"**Error:** {result['error']}").send()
    else:
        await cl.Message("Session finished.").send()
    flush_langfuse()


# user identifier -> callable that stops that user's running session (used by POST /stop-session).
_STOPPERS: dict[str, callable] = {}  # type: ignore


def _user_id() -> str:
    user = cl.user_session.get("user")
    return user.identifier if user else "anonymous"


async def _run_stoppable(graph_input) -> None:
    """Drive the graph in its own task so a stop request can cancel it, even while it waits for an answer."""
    task = asyncio.create_task(_drive(graph_input))
    stopped = False
    uid = _user_id()

    def stop() -> bool:
        nonlocal stopped
        if task.done():
            return False
        stopped = True
        task.cancel()
        return True

    _STOPPERS[uid] = stop
    try:
        await task
    except asyncio.CancelledError:
        # Our own stop sets `stopped`; anything else is Chainlit cancelling the handler, so let it through.
        if not stopped:
            raise
        await cl.Message("Stopped. What would you like to learn next?").send()
    finally:
        if _STOPPERS.get(uid) is stop:
            del _STOPPERS[uid]
        flush_langfuse()


async def _session(goal: str | None = None) -> None:
    """Run study sessions back to back: each goal gets its own LangGraph thread, and finishing or stopping
    one asks for the next goal."""
    while True:
        if goal is None:
            reply = await cl.AskUserMessage(
                content="What would you like to learn?", timeout=ASK_TIMEOUT_SECONDS
            ).send()
            if not reply:
                return
            goal = reply["output"].strip()  # type: ignore
        if not goal:
            goal = None
            continue

        # The first goal keeps the Chainlit thread id so old chats stay resumable.
        if cl.user_session.get("graph_tid") is None:
            cl.user_session.set("graph_tid", cl.context.session.thread_id)
        else:
            cl.user_session.set("graph_tid", f"{cl.context.session.thread_id}:{uuid.uuid4().hex[:8]}")

        await cl.Message(f"Starting: **{goal}**").send()
        await _run_stoppable(initial_state(goal, _graph_tid()))
        goal = None


async def _stop_session(user=Depends(get_current_user)):
    """Called by public/custom.js when the user presses the composer's Stop button."""
    stop = _STOPPERS.get(user.identifier if user else "anonymous")
    return {"stopped": bool(stop and stop())}


# Chainlit's catch-all route is already registered; ours must sit in front of it.
_before = len(chainlit_server.router.routes)
chainlit_server.add_api_route("/stop-session", _stop_session, methods=["POST"], include_in_schema=False)
_ours = chainlit_server.router.routes[_before:]
del chainlit_server.router.routes[_before:]
chainlit_server.router.routes[0:0] = _ours


@cl.on_stop
async def on_stop():
    # Chainlit's own Stop button (shown while the coach is busy) cancels the whole handler.
    await cl.Message("Stopped. Type a new topic to start again.").send()


@cl.on_chat_start
async def on_chat_start():
    await _session()


async def _latest_graph_tid(thread_id: str) -> str:
    """The most recent LangGraph thread started inside this Chainlit chat (checkpoint ids are time-ordered)."""
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT thread_id FROM checkpoints WHERE thread_id = :tid OR thread_id LIKE :prefix "
                    "ORDER BY checkpoint_id DESC LIMIT 1"
                ),
                {"tid": thread_id, "prefix": f"{thread_id}:%"},
            )
        ).first()
    return row[0] if row else thread_id


@cl.on_chat_resume
async def on_chat_resume(thread):
    await cl.Message("Welcome back, resuming where you left off...").send()
    try:
        cl.user_session.set("graph_tid", await _latest_graph_tid(thread["id"]))
        await _run_stoppable(None)
    except Exception as e:
        logger.error(f"[Chainlit] Could not resume thread {thread['id']}: {e}")
        await cl.Message("Could not resume this session. Type a new goal to start over.").send()
        return
    await _session()


@cl.on_message
async def on_message(message: cl.Message):
    """Only reached when no question is pending (after a stop or a finished session): treat it as a new goal."""
    if _user_id() in _STOPPERS:
        await cl.Message("Please answer the current question, or press Stop to start a new topic.").send()
        return
    await _session(goal=message.content.strip())
