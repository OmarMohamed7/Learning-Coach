"""Single switch point for the chat model backend.

Set LLM_PROVIDER to ollama (default), deepseek, claude, gemini, groq,
opencode or openrouter in .env to pick the backend. gemini, groq, deepseek, opencode and
openrouter use their
OpenAI-compatible endpoints (opencode = OpenCode Zen gateway). Every
agent should call get_llm() instead of instantiating
ChatOllama/ChatAnthropic directly, so switching providers never touches
agent code again.
"""

import os
from contextvars import ContextVar
from dataclasses import dataclass

from langchain_core.callbacks import BaseCallbackHandler
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
    "deepseek": (
        os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip(),
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_MODEL",
        "deepseek-chat",
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
    # Any OpenAI-compatible endpoint (vLLM, LM Studio, a gateway...), set through CUSTOM_LLM_* env vars.
    "custom": (
        os.getenv("CUSTOM_LLM_BASE_URL", "").strip(),
        "CUSTOM_LLM_API_KEY",
        "CUSTOM_LLM_MODEL",
        "",
    ),
}


def _default_model(provider: str) -> str:
    if provider == "claude":
        return CLAUDE_MODEL
    if provider in _OPENAI_COMPAT:
        _, _, model_var, default_model = _OPENAI_COMPAT[provider]
        return os.getenv(model_var, default_model)
    return OLLAMA_MODEL


_VALID_PROVIDERS = (*_OPENAI_COMPAT.keys(), "claude", "ollama")
_PROVIDER_LABELS = {
    "ollama": "Ollama Cloud",
    "groq": "Groq",
    "deepseek": "DeepSeek",
    "custom": "Custom",
}
_API_KEY_VARS = {
    "ollama": "OLLAMA_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


@dataclass(frozen=True)
class ModelChoice:
    provider: str
    model: str
    base_url: str = (
        ""  # only for a custom endpoint entered in the UI; empty means use the env/default URL
    )

    @property
    def label(self) -> str:
        return f"{_PROVIDER_LABELS.get(self.provider, self.provider)} · {self.model}"


def _has_key(provider: str) -> bool:
    if provider == "custom":
        return bool(_OPENAI_COMPAT["custom"][0] and _default_model("custom"))
    var = _API_KEY_VARS.get(provider)
    return not var or bool(os.getenv(var, "").strip())


def _env_choice() -> ModelChoice:
    return ModelChoice(LLM_PROVIDER, _default_model(LLM_PROVIDER))


def default_choice() -> ModelChoice:
    """The .env model if its provider has a key, otherwise the first model that does."""
    return model_choices()[0]


def model_choices() -> list[ModelChoice]:
    """Models offered in the UI picker: the configured default first, then any with an API key set."""
    candidates = [
        _env_choice(),
        ModelChoice("deepseek", _default_model("deepseek")),
        ModelChoice("ollama", "gpt-oss:120b"),
        ModelChoice("groq", _default_model("groq")),
        ModelChoice("groq", "openai/gpt-oss-20b"),
        ModelChoice("custom", _default_model("custom")),
    ]
    seen, out = set(), []
    for c in candidates:
        if c not in seen and _has_key(c.provider):
            seen.add(c)
            out.append(c)
    return out or [_env_choice()]


_selected: ContextVar[ModelChoice | None] = ContextVar("selected_model", default=None)


def use_model(choice: ModelChoice | None) -> None:
    """Select the model for the current context (one chat session); None means the .env default."""
    _selected.set(choice)


def current_choice() -> ModelChoice:
    return _selected.get() or default_choice()


def get_model_name() -> str:
    return current_choice().model


def _build_llm(
    provider: str,
    temperature: float,
    json_mode: bool,
    model: str | None = None,
    base_url: str | None = None,
):
    """Instantiate the chat model for one provider."""
    model = model or _default_model(provider)
    if provider == "claude":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model_name=model, temperature=temperature, timeout=None, stop=None
        )

    if provider in _OPENAI_COMPAT:
        from langchain_openai import ChatOpenAI

        default_url, key_var, _, _ = _OPENAI_COMPAT[provider]
        kwargs = {
            "model": model,
            "base_url": base_url or default_url,
            "api_key": (
                os.environ.get(key_var) or "not-needed"
                if provider == "custom"
                else os.environ[key_var]
            ),
            "temperature": temperature,
            "max_retries": 5,
        }
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        if (
            provider == "openrouter"
            and os.getenv("OPENROUTER_REASONING", "false").lower() == "true"
        ):
            model_kwargs = kwargs.setdefault("model_kwargs", {})
            model_kwargs["extra_body"] = {"reasoning": {"enabled": True}}
        return ChatOpenAI(**kwargs)

    if provider != "ollama":
        raise ValueError(
            f"Unknown LLM_PROVIDER: {provider!r} "
            f"(expected 'ollama', 'claude', 'gemini', 'groq', 'deepseek', 'opencode' or 'openrouter')"
        )

    kwargs = {"model": model, "base_url": OLLAMA_BASE_URL, "temperature": temperature}
    if OLLAMA_API_KEY:
        kwargs["client_kwargs"] = {
            "headers": {"Authorization": f"Bearer {OLLAMA_API_KEY}"}
        }
    if json_mode:
        kwargs["format"] = "json"
    return ChatOllama(**kwargs)


def get_llm(
    temperature: float = 0.1,
    json_mode: bool = False,
    tools=None,
    name: str | None = None,
):
    """Chat model for the selected model, falling back to another provider that has a key.

    `name` becomes the run (and Langfuse generation) name, e.g. "grade-answer".
    """

    def finish(llm, is_fallback: bool = False):
        if tools:
            llm = llm.bind_tools(tools)
        config = {"metadata": {"llm_fallback": is_fallback}}
        if name:
            config["run_name"] = name
        return llm.with_config(**config)

    choice = current_choice()
    primary = finish(
        _build_llm(
            choice.provider,
            temperature,
            json_mode,
            choice.model,
            choice.base_url or None,
        )
    )

    fallbacks = []
    if choice.provider != "custom" and _default_model(choice.provider) != choice.model:
        fallbacks.append(
            finish(
                _build_llm(choice.provider, temperature, json_mode), is_fallback=True
            )
        )  # same provider, default model
    other = next(
        (
            p
            for p in (os.getenv("FALLBACK_LLM_PROVIDER", "").lower(), LLM_PROVIDER)
            if p and p != choice.provider and _has_key(p)
        ),
        None,
    )
    if other is not None:
        if other not in _VALID_PROVIDERS:
            raise ValueError(
                f"Unknown FALLBACK_LLM_PROVIDER: {other!r} (expected one of {_VALID_PROVIDERS})"
            )
        fallbacks.append(
            finish(_build_llm(other, temperature, json_mode), is_fallback=True)
        )
    return primary.with_fallbacks(fallbacks) if fallbacks else primary


class FallbackWatcher(BaseCallbackHandler):
    """Records which fallback model answered during a run, so the UI can say so."""

    def __init__(self):
        self.used: set[str] = set()

    def on_chat_model_start(self, serialized, messages, *, metadata=None, **kwargs):
        if (metadata or {}).get("llm_fallback"):
            params = kwargs.get("invocation_params") or {}
            self.used.add(
                params.get("model") or params.get("model_name") or "fallback model"
            )
