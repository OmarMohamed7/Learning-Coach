from langgraph.types import interrupt
from graph.state import AgentState, StudyRoadmap

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
    
    decision = interrupt({
        "type": "roadmap_approval",
        "roadmap": roadmap,
        "prompt": (
            "Is this study plan suits you?\n `Yes` to start learning\n `No` to regenrate a different plan"
        )
    })
    
    approved = str(decision).lower().strip() in ("yes", "y", "ok", "approved")
    
    if approved:
        logger.info("[Human Approval] Roadmap approved, start learning")
    else:
        logger.info("[Human Approval] Roadmap rejected\nRegenrating new one...")
        
    return{
        "approved": approved,
        "roadmap":roadmap,
        "goal": state.get("goal", ""),
        "session_id":state.get("session_id", ""),
        "current_topic_index": state.get("current_topic_index", 0),
        "quiz_results": state.get("quiz_results", []),
        "weak_areas": state.get("weak_areas", []),
        "study_materials_path": state.get("study_materials_path", "study_materials/sample_notes"),
        "error": None,
        
    }