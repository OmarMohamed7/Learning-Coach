import asyncio
import os

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Message,
    Part,
    Role,
    TextPart,
)

from crewai_service.study_buddy import build_crew

PORT = int(os.getenv("PORT", "9002"))

STUDY_BUDDY_SKILL = AgentSkill(
    id="study-buddy",
    name="Study Buddy",
    description="Answers a learner's question with a short explanation, an example and a practice tip.",
    tags=["education", "tutoring", "crewai"],
    examples=["Explain Python closures like I'm new to programming"],
)

AGENT_CARD = AgentCard(
    name="CrewAI Study Buddy",
    description="A CrewAI agent exposed over A2A; callers need no CrewAI dependency.",
    url=f"http://localhost:{PORT}/",
    version="1.0.0",
    default_input_modes=["text"],
    default_output_modes=["text"],
    capabilities=AgentCapabilities(streaming=False),
    skills=[STUDY_BUDDY_SKILL],
)


class StudyBuddyExecutor(AgentExecutor):
    """Request: plain text question. Response: plain text answer."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        question = context.get_user_input()
        if not question:
            answer = "Please send a question."
        else:
            result = await asyncio.to_thread(build_crew(question).kickoff)
            answer = str(result)

        await event_queue.enqueue_event(
            Message(
                message_id="",
                role=Role.agent,
                parts=[Part(root=TextPart(text=answer))],
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        return await super().cancel(context, event_queue)


def create_study_buddy_server():
    handler = DefaultRequestHandler(
        agent_executor=StudyBuddyExecutor(), task_store=InMemoryTaskStore()
    )
    return A2AStarletteApplication(agent_card=AGENT_CARD, http_handler=handler).build()


def main() -> None:
    uvicorn.run(create_study_buddy_server(), host="0.0.0.0", port=PORT)
