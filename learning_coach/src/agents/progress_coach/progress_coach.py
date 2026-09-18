""" 
The Progress Coach does three things in sequence: 
    1- evaluate the quiz result
    2- give the student feedback
    3- decide what happens next.
"""
import json
from datetime import datetime, timezone

from graph.state import get_latest_quiz_result
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from config.llm_factory import get_llm
from logger import get_logger
from mcp_client.client import get_cached_tools
from .progress_coach_prompt import COACHING_PROMPT

PASS_THRESHOLD = 0.8

logger = get_logger(__name__)

def get_coaching_message(topic: str, score: float, weak_areas: list[str]) -> dict:
    """Ask the LLM for a personalised coaching message."""
    llm = get_llm(temperature=0.4, json_mode=True)
    context = {
        "topic":         topic,
        "score_percent": f"{score:.0%}",
        "weak_areas":    weak_areas if weak_areas else ["none identified"],
    }
    try:
        response = llm.invoke([
            SystemMessage(content=COACHING_PROMPT.format(
                topic= topic,
                score=score,
                weak_areas= weak_areas if weak_areas else []
                )),
            HumanMessage(content=json.dumps(context)),
        ])
        return json.loads(response.content) # type: ignore
    except Exception as e:
        logger.error(f"[Progress Coach] LLM call failed: {e}")
        return {
            "summary":      f"You scored {score:.0%} on {topic}. Keep going!",
            "encouragement": "Every topic builds on the last.",
        }
        
def progress_coach_node(state: dict) -> dict:
    """
    LangGraph Node: Progress Coach
    
    Reads: state['quiz_results'], state['roadmap'], state['current_topic_index'], state['session_id']
    
    Writes: state['roadmap'], state['current_topic_incdex'], state['messages'], state['error']
    
    """
    
    latest = get_latest_quiz_result(state= state)
    if latest is None:
        return {"error": "No quiz results. Quiz Generator must run first"}
    
    roadmap = state.get("roadmap")
    if roadmap is None:
        return {"error": "No roadmap found"}
    idx = state.get("current_topic_index", 0)
    session_id = state.get("session_id", "unknown")
    score = latest.score

    logger.info(f"\n[Progress Coach] Topic: '{latest.topic}'")
    logger.info(f"[Progress Coach] Score: {score:.0%}")
    if latest.weak_areas:
        logger.info(f"[Progress Coach] Weak areas: {', '.join(latest.weak_areas)}")
        
    # Get Coach message from llm
    coaching = get_coaching_message(topic= latest.topic , score= latest.score, weak_areas= latest.weak_areas)
    
    topics = roadmap.get("topics", []) if isinstance(roadmap, dict) else roadmap.topics
    
    if idx < len(topics):
        topic = topics[idx]
        new_status = "completed" if score >= PASS_THRESHOLD else "needs_review"
        if isinstance(topic, dict):
            topic["status"] = new_status
        else:
            topic.status = new_status
            
    next_idx = idx + 1
    all_done = next_idx >= len(topics)

    mcp_tools = get_cached_tools()
    if not mcp_tools:
        return {"error": "No MCP tools available. Did startup fail to load them?"}
    tools = {t.name: t for t in mcp_tools}

    logger.info("Persist progress to MCP memory")
    tools["memory_set"].invoke({
        "session_id": session_id,
        "key": f"progress_topic_{idx}",
        "value": json.dumps({
            "topic":      latest.topic,
            "score":      score,
            "weak_areas": latest.weak_areas,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
        }),
    })
    
    # Print coaching feedback
    logger.info(f"\n{'─'*60}")
    logger.info(f"Coach: {coaching['summary']}")
    logger.info(f"{coaching['encouragement']}")

    if all_done:
        results = state.get("quiz_results", [])
        avg = sum(r.score for r in results) / max(len(results), 1)
        logger.info(f"\nSession complete! Average: {avg:.0%}")
    else:
        next_topic = topics[next_idx]
        next_title = next_topic.get("title") if isinstance(next_topic, dict) else next_topic.title
        logger.info(f"\nNext topic: '{next_title}'")
    logger.info(f"{'─'*60}\n")

    return {
        "roadmap":              roadmap,
        "current_topic_index":  next_idx,
        "messages":             [AIMessage(content=coaching["summary"])],
        "error":                None,
    }