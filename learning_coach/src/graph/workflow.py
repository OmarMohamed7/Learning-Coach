from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from agents.curriculum_planner.curriculum_planner import curriculum_planner_node
from agents.explainer.explainer import explainer_node
from agents.human_approval.human_approval import human_approval_node
from agents.progress_coach.progress_coach import progress_coach_node
from agents.quiz_generator.quiz_generator import quiz_generator_node, quiz_is_pending, quiz_question_node
from graph.state import AgentState, session_is_complete


def route_after_planning(state: dict) -> str:
    return "human_approval" if state.get("roadmap") is not None else END


def route_after_approval(state: dict) -> str:
    if state.get("exited"):
        return END
    return "explainer" if state.get("approved") else "curriculum_planner"


def route_after_explaining(state: dict) -> str:
    return END if state.get("error") else "quiz_generator"


def route_after_quiz_generation(state: dict) -> str:
    return END if state.get("error") else "quiz_question"


def route_after_question(state: dict) -> str:
    if state.get("error"):
        return END
    return "quiz_question" if quiz_is_pending(state) else "progress_coach"


def route_after_progress(state: dict) -> str:
    return END if session_is_complete(state) else "explainer"


def build_graph() -> StateGraph:
    """Assemble the Learning Coach graph. Call `.compile(checkpointer=...)` on the result."""
    builder = StateGraph(AgentState)

    builder.add_node("curriculum_planner",  curriculum_planner_node)  # type: ignore
    builder.add_node("human_approval",      human_approval_node) # type: ignore
    builder.add_node("explainer",           explainer_node) # type: ignore
    builder.add_node("quiz_generator",      quiz_generator_node) # type: ignore
    builder.add_node("quiz_question",       quiz_question_node) # type: ignore
    builder.add_node("progress_coach",      progress_coach_node) # type: ignore

    builder.set_entry_point("curriculum_planner")
    builder.add_conditional_edges("curriculum_planner", route_after_planning, {"human_approval": "human_approval", END: END})
    builder.add_conditional_edges("human_approval", route_after_approval,{"explainer": "explainer", "curriculum_planner": "curriculum_planner", END: END})
    
    builder.add_conditional_edges("explainer", route_after_explaining, {"quiz_generator": "quiz_generator", END: END})
    builder.add_conditional_edges("quiz_generator", route_after_quiz_generation, {"quiz_question": "quiz_question", END: END})
    builder.add_conditional_edges("quiz_question", route_after_question, {"quiz_question": "quiz_question", "progress_coach": "progress_coach", END: END})
    builder.add_conditional_edges("progress_coach", route_after_progress,{"explainer": "explainer", END: END})

    return builder


def compile_graph(checkpointer: BaseCheckpointSaver):
    """Build and compile the graph with the given checkpointer."""
    return build_graph().compile(checkpointer=checkpointer)
