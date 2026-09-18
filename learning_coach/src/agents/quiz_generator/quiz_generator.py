import json
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

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
        
# Interactive session of quiz
def run_quiz(topic:str, explanation: str) -> QuizResult:
    """ Run an interactive quiz session in the terminal. """
    logger.info(f"\n{'='*60}")
    logger.info(f"Quiz: {topic}")
    logger.info(f"{'='*60}")
    logger.info("Answer each question in your own words. Press Enter to submit.\n")
    
    question_data = generate_questions(topic=topic, explanation= explanation)
    graded_questions: list[QuizQuestion] = []
    total_score = 0.0
    weak_areas = []
    
    for i, q_data in enumerate(question_data,1):
        question_text = q_data["question"]
        expected = q_data["expected_answer"]
        difficulty = q_data.get("difficulty" , "meduim")
        
        logger.info(f"Question {i} [{difficulty}]: {question_text}")
        user_answer = input("Your answer: ").strip()
        
        if not user_answer:
            logger.error("No Answer Provided!")
            
        logger.info("Grading...")
        
        grade = grade_answer(question= question_text, expected= expected , student_answer=user_answer)
        
        score = float(grade.get("score", 0.0))
        correct = bool(grade.get("correct",False))
        feedback = grade['feedback'] or ""
        missing = grade['missing_concept'] or ""

        total_score += score
        status = "✓" if correct else "✗"

        logger.info(f"{status} Score: {score:.0%}. {feedback}\n")

        if missing:
            weak_areas.append(missing)

        graded_questions.append(QuizQuestion(
            question=question_text,
            expected_answer=expected,
            user_answer=user_answer,
            correct=correct,
            feedback=feedback,
            score=score,
        ))
        
    avg_score = (total_score / len(question_data)) if question_data else 0.0
    correct_count = sum(1 for q in graded_questions if q.correct)
        
    logger.info(f"{'='*60}")
    logger.info(f"Quiz complete! Score: {avg_score:.0%} ({correct_count}/{len(graded_questions)} correct)")
    if weak_areas:
        logger.info(f"Areas to review: {', '.join(set(weak_areas))}")
    logger.info(f"{'='*60}\n")
    
    
    return QuizResult(
        topic=topic,
        questions=graded_questions,
        score=avg_score,
        weak_areas=list(set(weak_areas)),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    
def quiz_generator_node(state: dict) -> dict:
    """ 
    Langgraph node: Quiz Generator
    
    Reads: state['roadmap'], state["current_topic_index"], state["messages"]
    Writes: state["quiz_results"], state["weak_areas"], state["error"]
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
    quiz_res = run_quiz(topic= topic.title, explanation= explanation)
    
    existing_results = state.get("quiz_results", [])
    all_weak_areas = list(set(
        state.get("weak_areas",[]) + quiz_res.weak_areas
    ))
    
    return {
        "quiz_results": existing_results + [quiz_res], # The Progress Coach needs the current quiz result. The session summary needs all of them. 
        "weak_areas": all_weak_areas,
        "error": None,
        "roadmap": state.get("roadmap"),
        "current_topic_index": state.get("current_topic_index", 0),
        "session_id": state.get("session_id", 0)
    }