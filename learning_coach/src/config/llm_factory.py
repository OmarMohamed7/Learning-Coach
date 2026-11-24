"""Single switch point for the chat model backend.

Set LLM_PROVIDER to ollama (default), claude, gemini, groq, opencode
or openrouter in .env to pick the backend. gemini, groq, opencode and
openrouter use their
OpenAI-compatible endpoints (opencode = OpenCode Zen gateway). Every
agent should call get_llm() instead of instantiating
ChatOllama/ChatAnthropic directly, so switching providers never touches
agent code again.
"""

import os

from langchain_ollama import ChatOllama

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
# Set for Ollama Cloud (OLLAMA_BASE_URL=https://ollama.com); leave empty for a local Ollama.
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
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
    "opencode": (
        "https://opencode.ai/zen/v1",
        "OPENCODE_API_KEY",
        "OPENCODE_MODEL",
        "ling-3.1-flash-free",
    ),
    "openrouter": (
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
        "openai/gpt-4o-mini",
    ),
}


def get_model_name() -> str:
    """Return the effective model ID for the configured provider."""
    if LLM_PROVIDER == "claude":
        return CLAUDE_MODEL
    if LLM_PROVIDER in _OPENAI_COMPAT:
        _, _, model_var, default_model = _OPENAI_COMPAT[LLM_PROVIDER]
        return os.getenv(model_var, default_model)
    return OLLAMA_MODEL


_VALID_PROVIDERS = (*_OPENAI_COMPAT.keys(), "claude", "ollama")


def _build_llm(provider: str, temperature: float, json_mode: bool):
    """Instantiate the chat model for one provider."""
    if provider == "claude":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model_name=CLAUDE_MODEL, temperature=temperature, timeout=None, stop=None)

    if provider in _OPENAI_COMPAT:
        from langchain_openai import ChatOpenAI

        base_url, key_var, model_var, default_model = _OPENAI_COMPAT[provider]
        kwargs = {
            "model": os.getenv(model_var, default_model),
            "base_url": base_url,
            "api_key": os.environ[key_var],
            "temperature": temperature,
            "max_retries": 5,
        }
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        if provider == "openrouter" and os.getenv("OPENROUTER_REASONING", "false").lower() == "true":
            model_kwargs = kwargs.setdefault("model_kwargs", {})
            model_kwargs["extra_body"] = {"reasoning": {"enabled": True}}
        return ChatOpenAI(**kwargs)

    if provider != "ollama":
        raise ValueError(
            f"Unknown LLM_PROVIDER: {provider!r} "
            f"(expected 'ollama', 'claude', 'gemini', 'groq', 'opencode' or 'openrouter')"
        )

    kwargs = {"model": OLLAMA_MODEL, "base_url": OLLAMA_BASE_URL, "temperature": temperature}
    if OLLAMA_API_KEY:
        kwargs["client_kwargs"] = {"headers": {"Authorization": f"Bearer {OLLAMA_API_KEY}"}}
    if json_mode:
        kwargs["format"] = "json"
    return ChatOllama(**kwargs)


def get_llm(temperature: float = 0.1, json_mode: bool = False, tools=None, name: str | None = None):
    """Return a chat model for LLM_PROVIDER, with FALLBACK_LLM_PROVIDER as fallback if set.

    `name` becomes the run (and Langfuse generation) name, e.g. "grade-answer".
    """
    def finish(llm):
        if tools:
            llm = llm.bind_tools(tools)
        return llm.with_config(run_name=name) if name else llm

    primary = finish(_build_llm(LLM_PROVIDER, temperature, json_mode))
    fallback_provider = os.getenv("FALLBACK_LLM_PROVIDER", "").lower()
    if not fallback_provider or fallback_provider == LLM_PROVIDER:
        return primary
    if fallback_provider not in _VALID_PROVIDERS:
        raise ValueError(f"Unknown FALLBACK_LLM_PROVIDER: {fallback_provider!r} (expected one of {_VALID_PROVIDERS})")
    return primary.with_fallbacks([finish(_build_llm(fallback_provider, temperature, json_mode))])
