import asyncio
import json

from a2a.types import AgentCapabilities, AgentCard, AgentSkill, Part, Role
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
    TextPart,
)
from agents.quiz_generator.quiz_generator import generate_questions, grade_answer

from logger import get_logger

logger = get_logger(__name__)

QUIZ_SKILL = AgentSkill(
    id="generate-and-grade-quiz",
    name="Generate and Grade Quiz",
    description=(
        "Given a topic and optional explanation text, generate questions "
        "that test conceptual understanding. If answers are provided, grades "
        "each answer and returns a score with identified weak areas."
    ),
    tags=["quiz" , "assessment", "education", "grading"],
    examples=[
        "Generate a quiz on Python closures",
        "Grade these answers for a decorators quiz "
    ]
)

QUIZ_AGENT_CARD = AgentCard(
    name="Quiz Genrator Service",
    description=(
        "Generates and grades quizez using LLM-as-judge"
        "Framewotk-agnostic: work with any A2A-compatible agent."
    ),
    url="localhost:9001/",
    version="1.0.0",
    default_input_modes=["text"],
    default_output_modes=["text"],
    capabilities=AgentCapabilities(streaming=False),
    skills=[QUIZ_SKILL]
    
)

class QuizAgentExecutor(AgentExecutor):
    """ 
    Handle Incoming A2A quiz task.
    
    REQUEST FORMAT (JSON in the text part)
    {
        "topic":            "Any topic",
        "explaination":     "Explaination",
        "answers":          ["Answer 1","Answer 2","..."]
    }
    
    RESPONSE FORMAT
    {
        "status":           "ready | graded",
        "topic":            "Python Closures",
        "questions":        ["qest1", "quest2"],
        "score":            0.90,
        "graded_questions": ["quest1", ...],
        "weak_areas":       ["area1", ...]
    }
    
    """
    
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        
        response_text = context.get_user_input() 
        
        if not response_text:
            logger.error("There is no inputs")
            return
        
        
        try:
            request_data = json.loads(response_text)
        except json.JSONDecodeError:
            # Handle bad JSON
            return

            
        topic             = request_data.get("topic", "General Knowledge")
        explanation       = request_data.get("explanation", "")
        provided_answers  = request_data.get("answers", [])
        
        logger.info(f"[Quiz A2A] Task received: topic='{topic}', "
              f"answers_provided={len(provided_answers)}")
        
        questions_data = await asyncio.to_thread(
            generate_questions, topic, explanation, 3
        )
        
        if not provided_answers:
            result = {
                "status": "questions_ready",
                "topic": topic,
                "questions": questions_data,
                "message": (
                    "Questions generated. Submit again with 'answers' key to grade."
                ),
            }
        else: 
            # Grade the provided answers
            graded = []
            total_score = 0.0
            weak_areas = []

            for q_data, answer in zip(questions_data, provided_answers):
                grade = await asyncio.to_thread(
                    grade_answer,question=q_data["question"], expected= q_data["expected_answer"], student_answer=answer
                )
                
                score = float(grade.get("score", "0.0"))
                total_score += score
                
                missing = grade.get("missing_concept","")
                if missing:
                    weak_areas.append(missing)
                    
                graded.append({
                    "question":  q_data["question"],
                    "answer":    answer,
                    "score":     score,
                    "correct":   bool(grade.get("correct", False)),
                    "feedback":  grade.get("feedback", ""),
                })
            
            avg_score = total_score / len(questions_data) if questions_data else 0.0

            
            result = {
                "status":           "graded",
                "topic":            topic,
                "score":            avg_score,
                "questions":        questions_data,
                "graded_questions": graded,
                "weak_areas":       list(set(weak_areas)),
            }

        logger.info(f"[Quiz A2A] Task complete: status={result['status']}")

        # Emit Event
        await event_queue.enqueue_event(
            Message(
                message_id="",
                role=Role.agent,
                parts=[
                    Part(
                        root=TextPart(
                            text=json.dumps(result, indent=2)
                        )
                    )
                ],
            )
        )