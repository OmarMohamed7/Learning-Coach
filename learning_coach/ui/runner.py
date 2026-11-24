"""Runs the graph for a chat: streams output, answers interrupts, and supports Stop."""
import asyncio
from typing import Callable

import chainlit as cl
from chainlit.auth import get_current_user
from chainlit.server import app as chainlit_server
from fastapi import Depends
from langgraph.types import Command

from agents.explainer.explainer import STREAM_TAG
from config.llm_factory import FallbackWatcher, current_choice, use_model
from observability.langfuse_setup import get_langfuse_config, trace_turn
from ui.asks import ask
from ui.formatting import DISPLAYED, STAGE_DONE, describe_interrupt
from ui.session import graph_tid, user_id

_graph = None
_STOPPERS: dict[str, Callable[[], bool]] = {}  # user id -> stops that user's running session


def set_graph(graph) -> None:
    global _graph
    _graph = graph


def is_running(uid: str) -> bool:
    return uid in _STOPPERS


async def _run(graph_input, *, turn: str, user_input: str | None) -> dict:
    """One graph run, traced as a `coach-turn`: input = what the user sent, output = what they were shown."""
    use_model(cl.user_session.get("model_choice"))
    shown: list[str] = []
    with trace_turn(
        turn=turn, session_id=graph_tid(), user_id=user_id(), input=user_input, chat_id=cl.context.session.thread_id
    ) as root:
        result = await _run_graph(graph_input, shown)
        if "__interrupt__" in result:
            shown.append(describe_interrupt(result["__interrupt__"][0].value))
        elif result.get("error"):
            shown.append(f"Error: {result['error']}")
        root.update(output="\n\n".join(shown) or None)
    return result


async def _run_graph(graph_input, shown: list[str]) -> dict:
    """Stream the graph until it finishes or hits an interrupt; returns the final state or {"__interrupt__": ...}."""
    config = get_langfuse_config(graph_tid(), user_id=user_id())
    watcher = FallbackWatcher()
    config["callbacks"] = [*config.get("callbacks", []), watcher]
    interrupt = None
    done: list[str] = []
    posts: list[str] = []
    live: cl.Message | None = None  # the explanation while it is being written

    async def flush_posts():
        for post in posts:
            await cl.Message(post).send()
        posts.clear()

    async with cl.Step(name="Working on it...", type="run", show_input=True) as step:
        async for mode, data in _graph.astream(graph_input, config=config, stream_mode=["updates", "messages"]):  # type: ignore
            if mode == "messages":
                chunk, meta = data
                token = chunk.content  # type: ignore
                if STREAM_TAG not in (meta.get("tags") or []) or not isinstance(token, str) or not token:  # type: ignore
                    continue
                if live is None:
                    await flush_posts()
                    live = cl.Message(content="")
                    live.parent_id = None  # show it in the chat, not inside the collapsed step
                    await live.send()
                await live.stream_token(token)
                continue

            for node, value in data.items():  # type: ignore
                if node == "__interrupt__":
                    interrupt = value
                    continue
                done.append(f"✅ {STAGE_DONE.get(node, node)}")
                step.output = "\n".join(done)
                await step.update()
                if node not in DISPLAYED or not (value or {}).get(DISPLAYED[node][0]):
                    continue
                key, fmt = DISPLAYED[node]
                if node == "explainer" and live is not None:
                    live.content = fmt(value[key])  # swap in the final text with its topic header
                    await live.update()
                    shown.append(live.content)
                    live = None
                else:
                    posts.append(fmt(value[key]))
                    shown.append(posts[-1])

    await flush_posts()
    if watcher.used:
        await cl.Message(
            f"⚠️ {current_choice().label} failed, so this step was answered by "
            f"**{', '.join(sorted(watcher.used))}** (fallback)."
        ).send()

    if interrupt is not None:
        return {"__interrupt__": interrupt}
    return (await _graph.aget_state(config)).values  # type: ignore


async def _drive(graph_input) -> None:
    """Run the graph, answering each interrupt through the chat until it finishes."""
    if graph_input is None:
        result = await _run(None, turn="resume-chat", user_input=None)
    else:
        result = await _run(graph_input, turn="start-goal", user_input=graph_input.get("goal"))

    while "__interrupt__" in result:
        answer = await ask(result["__interrupt__"][0].value)
        if answer is None:
            await cl.Message("Timed out waiting for your reply. Reopen this chat from the history to continue.").send()
            return
        result = await _run(Command(resume=answer), turn="answer", user_input=answer)

    if result.get("error"):
        await cl.Message(f"**Error:** {result['error']}").send()
    else:
        await cl.Message("Session finished.").send()


async def run_stoppable(graph_input) -> None:
    """Drive the graph in its own task so Stop can cancel it, even while it waits for an answer."""
    task = asyncio.create_task(_drive(graph_input))
    stopped = False
    uid = user_id()

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
        if not stopped:  # Chainlit cancelled the handler, not our Stop button
            raise
        await cl.Message("Stopped. What would you like to learn next?").send()
    finally:
        if _STOPPERS.get(uid) is stop:
            del _STOPPERS[uid]


async def _stop_session(user=Depends(get_current_user)):
    """Called by public/custom.js when the user presses the composer's Stop button."""
    stop = _STOPPERS.get(user.identifier if user else "anonymous")
    return {"stopped": bool(stop and stop())}


def register_stop_route() -> None:
    # Chainlit's catch-all route is already registered; ours must sit in front of it.
    before = len(chainlit_server.router.routes)
    chainlit_server.add_api_route("/stop-session", _stop_session, methods=["POST"], include_in_schema=False)
    ours = chainlit_server.router.routes[before:]
    del chainlit_server.router.routes[before:]
    chainlit_server.router.routes[0:0] = ours
