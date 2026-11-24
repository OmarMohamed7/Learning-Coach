"""Langfuse tracing: one `coach-turn` trace per graph run, grouped into a session per study goal."""
import os
from contextlib import contextmanager
from typing import Any, Generator

from logger import get_logger

from config.llm_factory import LLM_PROVIDER, get_model_name

logger = get_logger(__name__)

TURN_NAME = "coach-turn"


def langfuse_configured() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY", "").strip() and os.getenv("LANGFUSE_SECRET_KEY", "").strip())


def _client():
    from langfuse import get_client

    return get_client()


class _NoopSpan:
    def update(self, **_: Any) -> None:
        pass


@contextmanager
def trace_turn(
    *, turn: str, session_id: str, user_id: str, input: Any, chat_id: str | None = None
) -> Generator[Any, None, None]:
    """Root observation for one coach turn; yields the span so the caller can set its output."""
    if not langfuse_configured():
        yield _NoopSpan()
        return

    from langfuse import propagate_attributes

    with _client().start_as_current_observation(as_type="agent", name=TURN_NAME, input=input) as root:
        with propagate_attributes(
            trace_name=TURN_NAME,
            session_id=session_id,
            user_id=user_id,
            tags=["learning-coach"],
            metadata={
                "turn": turn,
                "chat_id": chat_id or "",
                "llm_provider": LLM_PROVIDER,
                "llm_model": get_model_name(),
                "fallback_provider": os.getenv("FALLBACK_LLM_PROVIDER", ""),
            },
        ):
            yield root


def get_langfuse_config(session_id: str, user_id: str = "local", extra_config: dict | None = None) -> dict:
    """LangGraph config with a fresh CallbackHandler. Build it inside `trace_turn`, once per run."""
    config: dict = {"configurable": {"thread_id": session_id}}
    if extra_config:
        config.update(extra_config)

    if langfuse_configured():
        try:
            from langfuse.langchain import CallbackHandler

            config["callbacks"] = [CallbackHandler()]
        except Exception as e:
            logger.error(f"[Observability] Could not create Langfuse handler: {e}")
    return config


def shutdown_langfuse() -> None:
    if not langfuse_configured():
        return
    try:
        _client().shutdown()
    except Exception as e:
        logger.error(f"[Observability] Langfuse shutdown failed: {e}")
