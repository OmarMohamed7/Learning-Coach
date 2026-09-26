"""Single switch point for the chat model backend.

Set LLM_PROVIDER to ollama (default), claude, gemini or groq in .env to pick
the backend. gemini and groq use their free OpenAI-compatible endpoints. Every agent should call get_llm() instead of instantiating
ChatOllama/ChatAnthropic directly, so switching providers never touches
agent code again.
"""

import os

from langchain_ollama import ChatOllama

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")

# OpenAI-compatible hosted providers: (base_url, api-key env var, default model env var, fallback model).
_OPENAI_COMPAT = {
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "gemini-2.5-flash",
    ),
    "groq": (
        "https://api.groq.com/openai/v1",
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "openai/gpt-oss-120b",
    ),
}


def get_llm(temperature: float = 0.1, json_mode: bool = False):
    """Return a chat model for the configured LLM_PROVIDER.

    json_mode maps to Ollama's native format='json'. Claude has no
    equivalent flag — its agents rely on the system prompt's existing
    "return ONLY valid JSON" instruction instead.
    """
    if LLM_PROVIDER == "claude":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model_name=CLAUDE_MODEL, temperature=temperature, timeout=None, stop=None)

    if LLM_PROVIDER in _OPENAI_COMPAT:
        from langchain_openai import ChatOpenAI

        base_url, key_var, model_var, default_model = _OPENAI_COMPAT[LLM_PROVIDER]
        kwargs = {
            "model": os.getenv(model_var, default_model),
            "base_url": base_url,
            "api_key": os.environ[key_var],
            "temperature": temperature,
            "max_retries": 5,
        }
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatOpenAI(**kwargs)

    if LLM_PROVIDER != "ollama":
        raise ValueError(
            f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r} (expected 'ollama', 'claude', 'gemini' or 'groq')"
        )

    kwargs = {"model": OLLAMA_MODEL, "base_url": OLLAMA_BASE_URL, "temperature": temperature}
    if json_mode:
        kwargs["format"] = "json"
    return ChatOllama(**kwargs)
