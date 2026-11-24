"""Per-chat values kept in the Chainlit user session."""
import chainlit as cl


def user_id() -> str:
    user = cl.user_session.get("user")
    return user.identifier if user else "anonymous"


def graph_tid() -> str:
    """LangGraph thread of the current goal (the first goal reuses the Chainlit thread id)."""
    return cl.user_session.get("graph_tid") or cl.context.session.thread_id
