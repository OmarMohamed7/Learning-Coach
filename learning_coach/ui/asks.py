"""Questions and buttons shown to the user when the graph pauses at an interrupt."""
import asyncio

import chainlit as cl

from graph.state import StudyRoadmap
from logger import get_logger
from ui.formatting import format_roadmap

logger = get_logger(__name__)

ASK_TIMEOUT_SECONDS = 3600


async def _buttons(content: str, options: list[tuple[str, str]]) -> str | None:
    """Show buttons as (value, label) pairs and return the clicked value."""
    choice = await cl.AskActionMessage(
        content=content,
        actions=[cl.Action(name=value, payload={"value": value}, label=label) for value, label in options],
        timeout=ASK_TIMEOUT_SECONDS,
    ).send()
    return choice["payload"]["value"] if choice else None


async def _ask_quiz_question(payload: dict) -> str | None:
    content = (
        f"**Question {payload['index']}/{payload['total']}** "
        f"[{payload.get('difficulty', 'medium')}]\n\n{payload['question']}"
    )
    reply = await cl.AskUserMessage(content=content, timeout=ASK_TIMEOUT_SECONDS).send()
    return reply["output"].strip() if reply else None  # type: ignore


async def _ask_roadmap_approval(payload: dict) -> str | None:
    raw = payload.get("roadmap")
    roadmap = StudyRoadmap.from_dict(raw) if isinstance(raw, dict) else raw
    # Its own message: AskActionMessage replaces its text with "Selected: ..." after a click.
    if roadmap:
        await cl.Message(format_roadmap(roadmap)).send()  # type: ignore
    return await _buttons("Does this study plan suit you?", [("yes", "✅ Approve"), ("no", "❌ Reject")])


async def _ask_next_step(payload: dict) -> str | None:
    move_on = ("next", "➡️ Next topic") if payload.get("has_next") else ("next", "✅ Finish session")
    return await _buttons(
        f"Finished **{payload.get('topic', 'this topic')}**. What next?",
        [("quiz", "📝 Take the quiz"), move_on],
    )


_ASKERS = {
    "quiz_question": _ask_quiz_question,
    "next_step": _ask_next_step,
    "roadmap_approval": _ask_roadmap_approval,
}


async def ask(payload: dict) -> str | None:
    """Show an interrupt payload and return the user's reply (None on timeout)."""
    asker = _ASKERS.get(payload.get("type"), _ask_roadmap_approval)  # type: ignore
    return await _surviving_reconnects(lambda: asker(payload))


async def _surviving_reconnects(make_ask):
    """Run the ask, re-asking if the socket reconnects (Chainlit drops an open ask on reconnect)."""
    session = cl.context.session
    while True:
        socket_id = session.socket_id
        task = asyncio.create_task(make_ask())
        try:
            while not task.done() and session.socket_id == socket_id:
                await asyncio.wait({task}, timeout=1)
            if task.done():
                return task.result()
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.warning("[Chainlit] Socket reconnected while waiting for an answer: asking again")
