import os
from logger import get_logger

logger = get_logger(__name__)

def _laangfuse_configured() -> bool:
    """
    Checks whether langfuse credentials are present in the environment
    
    Returns False if either key is missing or empty. In the case the system runs without observability rather than raising an error
    """
    
    private_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    
    return bool(public_key and private_key)

def get_langfuse_handler():
    """
    Create a Langfuse callback handler for a session, or None if not configured
    
    Attached to graph.invoke()
    """
    
    if not _laangfuse_configured():
        return None
    
    try:
        from langfuse.langchain import CallbackHandler
        from langfuse import Langfuse, get_client
        
        private_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        host = os.getenv("LANGFUSE_HOST", "").strip()
        
        Langfuse(
            public_key=public_key,
            secret_key=private_key,
            host=host 
        )
        
        return CallbackHandler(
            public_key= public_key
        )
    
    except ImportError:
        logger.error("[Observability] langfuse not installed. Run: pip install langfuse")
        return None
    except Exception as e:
        logger.error(f"[Observability] Failed to create handler: {e}")
        return None

def get_langfuse_config(
    session_id: str,
    user_id: str = "local",
    extra_config: dict | None = None,
) -> dict:
    """
    Build the config for langgraph 
    
    Args:
        session_id:   The study session ID.
        user_id:      Optional user identifier.
        extra_config: Any additional LangGraph config to merge in.

    Returns:
        A dict ready to pass as `config` to graph.invoke().
    """
    langfuse_handler = get_langfuse_handler()
    
    config = {
        "configurable": { "thread_id": session_id},
        "metadata": {
            "langfuse_session_id": session_id,
            "langfuse_user_id": user_id,
            "langfuse_tags": ["learning-coach", "local-inference"],
            # Your custom framework metadata
            "model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            "framework": "langgraph",
        }
    }
    
    if extra_config:
        config.update(extra_config)
    
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
    
        logger.info(f"[Observability] Tracing session {session_id} → "
                f"{os.getenv('LANGFUSE_HOST', 'http://localhost:3000')}")
    else:
        logger.info("[Observability] Langfuse not configured. Running without tracing.")

    return config


def flush_langfuse() -> None:
    """
    Flush any pending Langfuse events before process exit.

    Langfuse sends traces asynchronously in a background thread.
    Call this when a session ends to ensure all traces are sent
    before the process exits.

    If Langfuse is not configured, this is a no-op.
    """
    if not _laangfuse_configured():
        return

    try:
        from langfuse import Langfuse
        Langfuse().flush()
    except Exception:
        pass