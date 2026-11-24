"""Learning Coach entry point (Chainlit UI). Run from learning_coach/: uv run chainlit run main.py

The Chainlit thread id doubles as the LangGraph thread id (later goals in the same chat get
`<thread id>:<suffix>`), so reopening a past chat resumes the graph from its checkpoint.
"""
import asyncio
import uuid
from contextlib import AsyncExitStack
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from sqlalchemy import text

import register  # noqa: F401  (adds the /register page to Chainlit's server)
from auth import authenticate
from config.llm_factory import current_choice, use_model
from database import DATABASE_URL, engine
from graph.state import initial_state
from logger import get_logger
from observability.langfuse_setup import shutdown_langfuse
from ui.asks import ASK_TIMEOUT_SECONDS
from ui.logs import install as install_logs, register_logs_route
from ui.model_picker import apply_model_setting, selected_choice, send_model_picker
from ui.runner import is_running, register_stop_route, run_stoppable, set_graph
from ui.session import graph_tid, user_id
from ui.startup import startup
from usage_limit import DAILY_GOAL_LIMIT, try_consume_goal

logger = get_logger(__name__)

_stack = AsyncExitStack()
register_stop_route()
register_logs_route()
install_logs()


@cl.data_layer
def sql_data_layer():
    return SQLAlchemyDataLayer(conninfo=DATABASE_URL)


@cl.password_auth_callback  # type: ignore
async def auth_callback(username: str, password: str):
    user = await authenticate(username, password)
    return cl.User(identifier=user.username, metadata={"role": "user"}) if user else None


@cl.on_app_startup
async def on_app_startup():
    set_graph(await _stack.enter_async_context(startup()))


@cl.on_app_shutdown
async def on_app_shutdown():
    await _stack.aclose()
    shutdown_langfuse()


async def _goal_allowed() -> int | None:
    """Use one of today's goals; returns how many are left, or None (after telling the user) if none are."""
    allowed, remaining, retry_at = await try_consume_goal(user_id())
    if allowed:
        return remaining
    wait = max(0, int((retry_at - datetime.now(timezone.utc)).total_seconds()))  # type: ignore
    await cl.Message(
        f"You've reached today's limit of **{DAILY_GOAL_LIMIT} study goals**. "
        f"You can start a new one in about **{wait // 3600}h {wait % 3600 // 60}m**."
    ).send()
    return None


async def _session(goal: str | None = None) -> None:
    """Run study goals back to back; each gets its own LangGraph thread."""
    while True:
        if goal is None:
            reply = await cl.AskUserMessage(content="What would you like to learn?", timeout=ASK_TIMEOUT_SECONDS).send()
            if not reply:
                return
            goal = reply["output"].strip()  # type: ignore
        if not goal:
            goal = None
            continue

        remaining = await _goal_allowed()
        if remaining is None:
            return

        chat_id = cl.context.session.thread_id
        first_goal = cl.user_session.get("graph_tid") is None
        cl.user_session.set("graph_tid", chat_id if first_goal else f"{chat_id}:{uuid.uuid4().hex[:8]}")

        use_model(selected_choice())
        await cl.Message(
            f"Starting: **{goal}** _({remaining} of {DAILY_GOAL_LIMIT} goals left today · {current_choice().label})_"
        ).send()
        await run_stoppable(initial_state(goal, graph_tid()))
        goal = None


@cl.on_chat_start
async def on_chat_start():
    await send_model_picker()
    await _session()


async def _latest_graph_tid(thread_id: str) -> str:
    """The most recent LangGraph thread started inside this chat (checkpoint ids are time-ordered)."""
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


async def _continue_resumed_chat(thread: dict) -> None:
    await cl.Message("Welcome back, resuming where you left off...").send()
    try:
        cl.user_session.set("graph_tid", await _latest_graph_tid(thread["id"]))
        await run_stoppable(None)
    except Exception as e:
        logger.error(f"[Chainlit] Could not resume thread {thread['id']}: {e}")
        await cl.Message("Could not resume this session. Type a new goal to start over.").send()
        return
    await _session()


@cl.on_chat_resume
async def on_chat_resume(thread):
    # Chainlit sends the chat history only after this hook returns, so continue the session after that.
    await send_model_picker()
    emitter = cl.context.emitter
    send_history = emitter.resume_thread

    async def send_history_then_continue(t):
        await send_history(t)
        emitter.resume_thread = send_history
        cl.context.session.current_task = asyncio.create_task(_continue_resumed_chat(thread))

    emitter.resume_thread = send_history_then_continue


@cl.on_settings_update
async def on_settings_update(settings: dict):
    await apply_model_setting(settings)


@cl.on_stop
async def on_stop():
    await cl.Message("Stopped. Type a new topic to start again.").send()


@cl.on_message
async def on_message(message: cl.Message):
    """Only reached when no question is pending (after a stop or a finished session): treat it as a new goal."""
    if is_running(user_id()):
        await cl.Message("Please answer the current question, or press Stop to start a new topic.").send()
        return
    await _session(goal=message.content.strip())
