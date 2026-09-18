"""Single switch point for the chat model backend.

Set LLM_PROVIDER=ollama (default) or LLM_PROVIDER=claude in .env to pick the
backend. Every agent should call get_llm() instead of instantiating
ChatOllama/ChatAnthropic directly, so switching providers never touches
agent code again.
"""

import os

from langchain_ollama import ChatOllama

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")


def get_llm(temperature: float = 0.1, json_mode: bool = False):
    """Return a chat model for the configured LLM_PROVIDER.

    json_mode maps to Ollama's native format='json'. Claude has no
    equivalent flag — its agents rely on the system prompt's existing
    "return ONLY valid JSON" instruction instead.
    """
    if LLM_PROVIDER == "claude":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model_name=CLAUDE_MODEL, temperature=temperature, timeout=None, stop=None)

    if LLM_PROVIDER != "ollama":
        raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r} (expected 'ollama' or 'claude')")

    kwargs = {"model": OLLAMA_MODEL, "base_url": OLLAMA_BASE_URL, "temperature": temperature}
    if json_mode:
        kwargs["format"] = "json"
    return ChatOllama(**kwargs)
