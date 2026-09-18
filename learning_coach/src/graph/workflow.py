from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from agents.curriculum_planner.curriculum_planner import curriculum_planner_node
from agents.explainer.explainer import explainer_node
from agents.human_approval.human_approval import human_approval_node
from agents.progress_coach.progress_coach import progress_coach_node
from agents.quiz_generator.quiz_generator import quiz_generator_node
from graph.state import AgentState, session_is_complete


def route_after_approval(state: dict) -> str:
    return "explainer" if state.get("approved") else "curriculum_planner"


def route_after_progress(state: dict) -> str:
    return END if session_is_complete(state) else "explainer"


def build_graph() -> StateGraph:
    """Assemble the Learning Coach graph. Call `.compile(checkpointer=...)` on the result."""
    builder = StateGraph(AgentState)

    builder.add_node("curriculum_planner", curriculum_planner_node)  # type: ignore
    builder.add_node("human_approval", human_approval_node) # type: ignore
    builder.add_node("explainer", explainer_node) # type: ignore
    builder.add_node("quiz_generator", quiz_generator_node) # type: ignore
    builder.add_node("progress_coach", progress_coach_node) # type: ignore

    builder.set_entry_point("curriculum_planner")
    builder.add_edge("curriculum_planner", "human_approval")
    builder.add_conditional_edges("human_approval", route_after_approval)
    builder.add_edge("explainer", "quiz_generator")
    builder.add_edge("quiz_generator", "progress_coach")
    builder.add_conditional_edges("progress_coach", route_after_progress)

    return builder


def compile_graph(checkpointer: BaseCheckpointSaver):
    """Build and compile the graph with the given checkpointer."""
    return build_graph().compile(checkpointer=checkpointer)
