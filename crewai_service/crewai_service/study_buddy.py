import os

from crewai import LLM, Agent, Crew, Task

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "")


def build_crew(question: str) -> Crew:
    llm = LLM(model=f"ollama/{OLLAMA_MODEL}", base_url=OLLAMA_BASE_URL)

    buddy = Agent(
        role="Study Buddy",
        goal="Help a learner understand a topic with clear, encouraging answers",
        backstory=(
            "A friendly peer tutor who explains concepts simply, gives one "
            "concrete example, and suggests what to practice next."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
    )
    task = Task(
        description=f"Answer the learner's question:\n{question}",
        expected_output="A short explanation, one example, and one practice suggestion.",
        agent=buddy,
    )
    return Crew(agents=[buddy], tasks=[task], verbose=False)
