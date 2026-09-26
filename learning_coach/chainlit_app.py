"""Learning Coach entry point (Chainlit UI). Run from learning_coach/: uv run chainlit run chainlit_app.py

The Chainlit thread id doubles as the LangGraph thread_id, so reopening a past
conversation resumes the graph from its checkpoint.
"""
from contextlib import AsyncExitStack, asynccontextmanager

import chainlit as cl
from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

load_dotenv()

import register  # noqa: F401  (adds the /register page to Chainlit's server)
from auth import authenticate
from database import CHECKPOINT_DB_URL, OrmBase, AsyncSessionLocal, engine
from graph.workflow import compile_graph
from mcp_client.client import get_mcp_tools
from models import create_new_version, get_agents, get_latest_version
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


def _config():
    user = cl.user_session.get("user")
    return get_langfuse_config(
        cl.context.session.thread_id,
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

    async with cl.Step(name="Working on it...", type="run", show_input=True) as step:
        async for update in _graph.astream(graph_input, config=config, stream_mode="updates"):  # type: ignore
            for node, value in update.items():
                if node == "__interrupt__":
                    interrupt = value
                    continue
                done.append(f"✅ {STAGE_DONE.get(node, node)}")
                step.output = "\n".join(done)
                await step.update()
                if node in DISPLAYED:
                    key, fmt = DISPLAYED[node]
                    if (value or {}).get(key):
                        posts.append(fmt(value[key]))

    # Posted in graph order after the step closes and before the caller asks the next question, so
    # e.g. the grade comes first, then the coach note, then the next topic's explanation above its questions.
    for post in posts:
        await cl.Message(post).send()

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
        await cl.Message("Session finished. Start a new chat to study something else.").send()
    flush_langfuse()


@cl.on_chat_start
async def on_chat_start():
    reply = await cl.AskUserMessage(
        content="What would you like to learn?", timeout=ASK_TIMEOUT_SECONDS
    ).send()
    if not reply:
        return
    goal = reply["output"].strip() # type: ignore
    await _drive(initial_state(goal, cl.context.session.thread_id))


@cl.on_chat_resume
async def on_chat_resume(thread):
    await cl.Message("Welcome back, resuming where you left off...").send()
    try:
        await _drive(None)
    except Exception as e:
        logger.error(f"[Chainlit] Could not resume thread {thread['id']}: {e}")
        await cl.Message("Could not resume this session. Start a new chat.").send()


@cl.on_message
async def on_message(message: cl.Message):
    await cl.Message("Please answer the current question, or start a new chat for a new goal.").send()
