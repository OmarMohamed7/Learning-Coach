import json
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import interrupt

from config.llm_factory import get_llm
from graph.state import QuizQuestion, QuizResult, get_current_topic

from .quiz_prompts import GENERATION_PROMPT, GRADING_PROMPT

from logger import get_logger

logger = get_logger(__name__)


def generate_questions(topic: str, explanation: str, n: int = 3) -> list[dict]:
    """ Generate n quiz questions from the Explainer's topic """
    
    llm = get_llm(temperature=0.4, json_mode=True)

    prompt = GENERATION_PROMPT.format(n=n)
    
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=f" Topic: {topic}\n\nExplaination:\n{explanation}")
    ]
    
    try:
        response = llm.invoke(messages)
        data = json.loads(response.content) # type: ignore
        questions = data.get("questions", [])
        if questions and isinstance(questions, list):
            return questions
        
    except Exception as e:
        logger.error(f"[Quiz Generator] LLM call failed during question generation: {e}")

    # Fallback: one generic question
    return [{
        "question": f"In your own words, explain the key concept of {topic} and why it matters.",
        "expected_answer": "A clear explanation demonstrating conceptual understanding.",
        "difficulty": "medium",
    }]
    
def grade_answer(question: str, expected: str, student_answer: str) -> dict:
    """ Grade a student's answer using the LLM as judge. """
    llm = get_llm(temperature=0.1, json_mode=True)

    prompt = GRADING_PROMPT.format(
        question= question,
        expected_answer= expected,
        student_answer= student_answer
    )
    
    try:
        res = llm.invoke([HumanMessage(content=prompt)])
        return json.loads(res.content) # type: ignore
    
    except Exception as e:
        logger.error(f"[Quiz Generator] LLM call failed during grading: {e}")
        return {
            "correct": False,
            "score": 0.5,
            "feedback": "Could not grade automatically. Please review manually.",
            "missing_concept": "",
        }
        
def build_quiz_result(topic: str, answers: list[dict]) -> QuizResult:
    """ Aggregate graded answers into the QuizResult the Progress Coach reads. """
    graded_questions = [
        QuizQuestion(**{k: v for k, v in a.items() if k != "missing_concept"}) for a in answers
    ]
    weak_areas = list({a["missing_concept"] for a in answers if a.get("missing_concept")})

    avg_score = (sum(q.score for q in graded_questions) / len(graded_questions)) if graded_questions else 0.0
    correct_count = sum(1 for q in graded_questions if q.correct)

    logger.info(f"{'='*60}")
    logger.info(f"Quiz complete! Score: {avg_score:.0%} ({correct_count}/{len(graded_questions)} correct)")
    if weak_areas:
        logger.info(f"Areas to review: {', '.join(weak_areas)}")
    logger.info(f"{'='*60}\n")

    return QuizResult(
        topic=topic,
        questions=graded_questions,
        score=avg_score,
        weak_areas=weak_areas,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def quiz_generator_node(state: dict) -> dict:
    """ 
    Langgraph node: Quiz Generator
    
    Generates the questions once and stores them in state["active_quiz"];
    quiz_question_node then asks them one at a time.

    Reads: state['roadmap'], state["current_topic_index"], state["messages"]
    Writes: state["active_quiz"], state["error"]
    """
    
    topic = get_current_topic(state=state)
    if not topic:
        return {"error": "No Current topic. Curriculum Planner must run first"}
    
    # Exctract the Explainer's final response from message history.
    # Explainer Final message is the last AI Message that has no tool_calls
    messages = state.get("messages", "")
    explanation = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls",None):
            explanation = str(msg.content)
            break
        
    if not explanation:
        logger.warning(f"[Quiz Generator] Warning: no explanation found, generating generic quiz")
        explanation = f"Topic: {topic.title}. {topic.description}"
        
    logger.info(f"\n[Quiz Generator] Generating quiz for: {topic.title}")
    questions = generate_questions(topic=topic.title, explanation=explanation)

    logger.info(f"\n{'='*60}")
    logger.info(f"Quiz: {topic.title}")
    logger.info(f"{'='*60}")
    logger.info("Answer each question in your own words. Press Enter to submit.\n")

    return {
        "active_quiz": {"topic": topic.title, "questions": questions, "answers": []},
        "error": None,
    }


def quiz_question_node(state: dict) -> dict:
    """
    Langgraph node: Quiz Question

    Asks the next unanswered question via interrupt(), grades the answer and
    records it. The graph loops back here until every question is answered,
    then this node writes the final QuizResult.

    One question per node run matters: on resume LangGraph re-executes the
    node from the top, so anything before interrupt() must be cheap and
    deterministic — generation and earlier grading must not live here.

    Reads: state["active_quiz"], state["quiz_results"], state["weak_areas"]
    Writes: state["active_quiz"], state["last_grade"], state["quiz_results"], state["weak_areas"], state["error"]
    """
    quiz = state.get("active_quiz")
    if not quiz or not quiz.get("questions"):
        return {"error": "No active quiz. Quiz Generator must run first"}

    questions = quiz["questions"]
    answers = list(quiz.get("answers", []))
    i = len(answers)
    q_data = questions[i]

    question_text = q_data["question"]
    expected = q_data["expected_answer"]
    difficulty = q_data.get("difficulty", "medium")

    user_answer = interrupt({
        "type": "quiz_question",
        "topic": quiz["topic"],
        "index": i + 1,
        "total": len(questions),
        "difficulty": difficulty,
        "question": question_text,
        "prompt": "Your answer:",
    })
    user_answer = str(user_answer or "").strip()

    if not user_answer:
        logger.error("No Answer Provided!")

    logger.info("Grading...")
    grade = grade_answer(question=question_text, expected=expected, student_answer=user_answer)

    score = float(grade.get("score", 0.0))
    correct = bool(grade.get("correct", False))
    feedback = grade.get("feedback") or ""
    missing = grade.get("missing_concept") or ""

    status = "✓" if correct else "✗"
    logger.info(f"{status} Score: {score:.0%}. {feedback}\n")

    answers.append({
        "question": question_text,
        "expected_answer": expected,
        "user_answer": user_answer,
        "correct": correct,
        "score": score,
        "feedback": feedback,
        "missing_concept": missing,
    })

    last_grade = {
        "index": i + 1,
        "total": len(questions),
        "score": score,
        "correct": correct,
        "feedback": feedback,
    }

    if len(answers) < len(questions):
        return {"active_quiz": {**quiz, "answers": answers}, "last_grade": last_grade, "error": None}

    quiz_res = build_quiz_result(topic=quiz["topic"], answers=answers)
    all_weak_areas = list(set(state.get("weak_areas", []) + quiz_res.weak_areas))

    return {
        "quiz_results": state.get("quiz_results", []) + [quiz_res], # The Progress Coach needs the current quiz result. The session summary needs all of them. 
        "weak_areas": all_weak_areas,
        "active_quiz": None,
        "last_grade": last_grade,
        "error": None,
        "roadmap": state.get("roadmap"),
        "current_topic_index": state.get("current_topic_index", 0),
        "session_id": state.get("session_id", 0)
    }


def quiz_is_pending(state: dict) -> bool:
    """ True while the active quiz still has unanswered questions. """
    quiz = state.get("active_quiz")
    return bool(quiz) and len(quiz.get("answers", [])) < len(quiz.get("questions", []))
