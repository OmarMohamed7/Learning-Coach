from langgraph.types import interrupt
from graph.state import StudyRoadmap

from logger import get_logger


logger = get_logger(__name__)

def human_approval_node(state: dict) -> dict:
    """
    LangGraph Node: Human Approval
    
    Reads: state["roadmap"]. : The study plan that show to user 
    
    Writes: state["approval"] : whether the user accepted or rejected the roadmap
    
    When approved=False, the coonditional edge routes back to curriculum agent 
    to generate a new roadmap
    """
    
    roadmap: StudyRoadmap | None = state.get("roadmap")
    
    if roadmap is None:
        logger.error("[Human Approval] No Roadmap generated!")
        return {"error": "No Roadmap generated"}
    
    logger.info("[Human Approval] Pausing for roadmap review...")

    logger.info(f"\n{'='*60}")
    logger.info(f"Study Roadmap: {roadmap.goal}")
    logger.info(f"{'='*60}")
    logger.info(f"Total weeks: {roadmap.total_weeks} | Weekly hours: {roadmap.weekly_hours}\n")
    for i, topic in enumerate(roadmap.topics, 1):
        logger.info(f"{i}. {topic.title} ({topic.estimated_minutes} min)")
        logger.info(f"   {topic.description}")
        if topic.prerequisites:
            logger.info(f"   Prerequisites: {', '.join(topic.prerequisites)}")
    logger.info(f"{'='*60}\n")

    decision = interrupt({
        "type": "roadmap_approval",
        "roadmap": roadmap,
        "prompt": (
            "Is this study plan suits you?\n `Yes` to start learning\n `No` to regenrate a different plan\n `Exit` to end the session"
        )
    })

    decision_str = str(decision).lower().strip()
    exited = decision_str in ("exit", "quit", "q")
    approved = decision_str in ("yes", "y", "ok", "approved")

    if exited:
        logger.info("[Human Approval] User exited the session")
    elif approved:
        logger.info("[Human Approval] Roadmap approved, start learning")
    else:
        logger.info("[Human Approval] Roadmap rejected\nRegenrating new one...")

    return{
        "approved": approved,
        "exited": exited,
        "roadmap":roadmap,
        "goal": state.get("goal", ""),
        "session_id":state.get("session_id", ""),
        "current_topic_index": state.get("current_topic_index", 0),
        "quiz_results": state.get("quiz_results", []),
        "weak_areas": state.get("weak_areas", []),
        "study_materials_path": state.get("study_materials_path", "study_materials/sample_notes"),
        "error": None,
        
    }