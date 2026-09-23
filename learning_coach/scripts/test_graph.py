"""Manual smoke test for the Learning Coach LangGraph.

Run from the learning_coach/ directory:
    uv run python scripts/test_graph.py

Requires Ollama running locally, and both MCP servers (filesystem, memory)
up, since curriculum_planner/explainer/quiz_generator call out to them.
Uses an in-memory checkpointer so it needs no Postgres connection — this
only checks the graph wiring (nodes, edges, interrupt/resume), not the
Postgres checkpointer itself.
"""
import argparse
import asyncio
import uuid

from dotenv import load_dotenv

load_dotenv()  # must run before importing graph.workflow — curriculum_planner_llm.py reads OLLAMA_MODEL at import time

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from graph.state import initial_state
from graph.workflow import build_graph
from mcp_client.client import get_mcp_tools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual smoke test for the Learning Coach LangGraph.")
    parser.add_argument("--goal", default="Learn English", help="The learning goal to seed the session with.")
    return parser.parse_args()


async def main():
    args = parse_args()

    print("--- Warming up MCP tool cache ---")
    tools = await get_mcp_tools()
    print(f"--- Loaded {len(tools)} MCP tool(s) ---")

    checkpointer = MemorySaver()
    graph = build_graph().compile(checkpointer=checkpointer)

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    state = initial_state(goal=args.goal, session_id=thread_id)

    print(f"--- thread_id={thread_id} ---")
    print("--- Running until first interrupt (roadmap approval) ---")
    result = await graph.ainvoke(state, config=config) # type: ignore

    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        if payload.get("type") == "quiz_question":
            print(f"\n--- Quiz question {payload['index']}/{payload['total']}, resuming with a canned answer ---")
            answer = "I'm not sure."
        else:
            print("\n--- Paused for human approval, resuming with 'yes' ---")
            answer = "yes"
        result = await graph.ainvoke(Command(resume=answer), config=config) # type: ignore

    print("\n--- Final state ---")
    print({k: v for k, v in result.items() if k != "messages"})

    print("\n--- Roadmap ---")
    print(result.get("roadmap"))


if __name__ == "__main__":
    asyncio.run(main())
