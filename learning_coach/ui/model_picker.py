"""The Model dropdown in the chat settings panel."""
import chainlit as cl
from chainlit.input_widget import Select

from config.llm_factory import model_choices


async def send_model_picker() -> None:
    choices = model_choices()
    selected = cl.user_session.get("model_choice") or choices[0]
    labels = [c.label for c in choices]
    await cl.ChatSettings([
        Select(id="model", label="Model", values=labels,
               initial_index=labels.index(selected.label) if selected.label in labels else 0)
    ]).send()


async def apply_model_setting(settings: dict) -> None:
    choice = next((c for c in model_choices() if c.label == settings.get("model")), None)
    if choice is None or choice == cl.user_session.get("model_choice"):
        return
    cl.user_session.set("model_choice", choice)
    await cl.Message(f"🔄 Now using **{choice.label}**").send()
