"""The model dropdown and custom-endpoint fields in the chat settings panel."""
import asyncio

import chainlit as cl
from chainlit.input_widget import Select, TextInput

from config.endpoint_check import public_https_error, reachability_error
from config.llm_factory import ModelChoice, model_choices


def available_choices() -> list[ModelChoice]:
    custom = cl.user_session.get("custom_choice")
    base = model_choices()
    return [c for c in base if c.provider != "custom"] + [custom] if custom else base


def selected_choice() -> ModelChoice | None:
    """The model picked in the dropdown, read from Chainlit's chat settings (what the browser last sent)."""
    label = (cl.context.session.chat_settings or {}).get("model")
    return next((c for c in available_choices() if c.label == label), None) or cl.user_session.get("model_choice")


async def _check_custom(url: str, model: str) -> tuple[ModelChoice | None, str]:
    """Validate a user-entered endpoint; returns the choice, or None and the reason."""
    if not url or not model:
        return None, "enter both the URL and the model name"
    url = url.rstrip("/")
    error = await asyncio.to_thread(public_https_error, url) or await reachability_error(url, model)
    return (None, error) if error else (ModelChoice("custom", model, url), "")


async def send_model_picker(select: ModelChoice | None = None) -> None:
    saved = cl.context.session.chat_settings or {}
    if cl.user_session.get("custom_choice") is None and saved.get("custom_url") and saved.get("custom_model"):
        url = saved["custom_url"].strip().rstrip("/")
        if not await asyncio.to_thread(public_https_error, url):  # restored chat: re-check the address, skip the network call
            cl.user_session.set("custom_choice", ModelChoice("custom", saved["custom_model"].strip(), url))
            cl.user_session.set("custom_sig", (url, saved["custom_model"].strip()))

    choices = available_choices()
    selected = select or selected_choice() or choices[0]
    labels = [c.label for c in choices]
    custom = cl.user_session.get("custom_choice")
    await cl.ChatSettings([
        Select(id="model", label="Model", values=labels,
               initial_index=labels.index(selected.label) if selected.label in labels else 0),
        TextInput(id="custom_url", label="Custom LLM URL (OpenAI-compatible, https)",
                  initial=custom.base_url if custom else "", placeholder="https://your-tunnel.example.com/v1"),
        TextInput(id="custom_model", label="Custom model name",
                  initial=custom.model if custom else "", placeholder="llama3.1:8b"),
    ]).send()


async def apply_model_setting(settings: dict) -> None:
    url = (settings.get("custom_url") or "").strip()
    model = (settings.get("custom_model") or "").strip()
    if (url, model) != cl.user_session.get("custom_sig"):
        cl.user_session.set("custom_sig", (url, model))
        if not url and not model:
            cl.user_session.set("custom_choice", None)
        else:
            choice, reason = await _check_custom(url, model)
            if choice is None:
                await cl.Message(f"⚠️ Custom LLM not used: {reason}.").send()
            else:
                cl.user_session.set("custom_choice", choice)
                cl.user_session.set("model_choice", choice)
                await cl.Message(f"🔄 Now using **{choice.label}**").send()
                await send_model_picker(select=choice)
            return

    choice = next((c for c in available_choices() if c.label == settings.get("model")), None)
    if choice is None or choice == cl.user_session.get("model_choice"):
        return
    cl.user_session.set("model_choice", choice)
    await cl.Message(f"🔄 Now using **{choice.label}**").send()
