"""Quiz flow runs on LangGraph interrupts instead of blocking input().

Wires the real quiz_generator / quiz_question nodes and routing functions into
a minimal graph with an in-memory checkpointer; LLM calls are stubbed.
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

import agents.quiz_generator.quiz_generator as qg
from graph.state import AgentState, StudyRoadmap, Topic, initial_state
from graph.workflow import route_after_question, route_after_quiz_generation


QUESTIONS = [
    {"question": "Q1?", "expected_answer": "A1", "difficulty": "easy"},
    {"question": "Q2?", "expected_answer": "A2", "difficulty": "hard"},
]


def build_quiz_graph():
    builder = StateGraph(AgentState)
    builder.add_node("quiz_generator", qg.quiz_generator_node)  # type: ignore
    builder.add_node("quiz_question", qg.quiz_question_node)  # type: ignore
    builder.add_node("progress_coach", lambda state: {})
    builder.set_entry_point("quiz_generator")
    builder.add_conditional_edges("quiz_generator", route_after_quiz_generation, {"quiz_question": "quiz_question", END: END})
    builder.add_conditional_edges("quiz_question", route_after_question, {"quiz_question": "quiz_question", "progress_coach": "progress_coach", END: END})
    builder.add_edge("progress_coach", END)
    return builder.compile(checkpointer=MemorySaver())


def test_quiz_asks_each_question_via_interrupt(monkeypatch):
    calls = {"generate": 0, "grade": []}

    def fake_generate(topic, explanation, n=3):
        calls["generate"] += 1
        return QUESTIONS

    def fake_grade(question, expected, student_answer):
        calls["grade"].append((question, student_answer))
        right = student_answer == expected
        return {
            "correct": right,
            "score": 1.0 if right else 0.0,
            "feedback": "ok" if right else "nope",
            "missing_concept": "" if right else f"gap in {question}",
        }

    monkeypatch.setattr(qg, "generate_questions", fake_generate)
    monkeypatch.setattr(qg, "grade_answer", fake_grade)

    state = initial_state(goal="Learn Python", session_id="t1")
    state["roadmap"] = StudyRoadmap(
        total_weeks=1,
        goal="Learn Python",
        topics=[Topic(title="Loops", description="for/while", estimated_minutes=30)],
    )
    config = {"configurable": {"thread_id": "t1"}}
    graph = build_quiz_graph()

    result = graph.invoke(state, config=config)  # type: ignore
    payload = result["__interrupt__"][0].value
    assert payload["type"] == "quiz_question"
    assert (payload["index"], payload["total"], payload["question"]) == (1, 2, "Q1?")

    result = graph.invoke(Command(resume="A1"), config=config)  # type: ignore
    payload = result["__interrupt__"][0].value
    assert (payload["index"], payload["question"]) == (2, "Q2?")

    result = graph.invoke(Command(resume="wrong"), config=config)  # type: ignore
    assert "__interrupt__" not in result

    # Resuming re-runs a node from the top: generation and earlier grading must not repeat.
    assert calls["generate"] == 1
    assert calls["grade"] == [("Q1?", "A1"), ("Q2?", "wrong")]

    assert result["active_quiz"] is None
    [quiz_res] = result["quiz_results"]
    assert quiz_res.topic == "Loops"
    assert quiz_res.score == 0.5
    assert [q.user_answer for q in quiz_res.questions] == ["A1", "wrong"]
    assert quiz_res.weak_areas == ["gap in Q2?"]
    assert result["weak_areas"] == ["gap in Q2?"]
