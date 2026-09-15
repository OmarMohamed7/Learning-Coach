import json
import os

from langchain_core.messages import HumanMessage, SystemMessage

from agents.curriculum_planner.curriculum_planner_llm import MODEL_NAME, PLANNER_SYSTEM_PROMPT, build_planner_llm
from graph.state import StudyRoadmap, Topic
    
def parse_roadmap_json(json_string: str) -> StudyRoadmap:
    
    """ Parse the LLM's JSON output into a StudyRoadmap dataclass """
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON.\n"
            f"Error: {e}\n"
            f"Raw output (first 300 chars): {json_string[:300]}"
        )
        
    required = ["goal", "total_weeks" , "topics"]
    for field in required:
        if field not in data:
            raise ValueError(f"LLM Response missing required fied: {field}")
        
    if not isinstance(data['topics'], list) or len(data['topics']) == 0:
        raise ValueError("LLM Response `topics` must be non-empty list")
    
    topics = []
    for i,t in enumerate(data['topics']):
        for field in ['title','description', 'estimated_minutes']:
            if field not in t:
                raise ValueError(f"Topic {i} missing required field: '{field}'")
        
        topics.append(Topic(
            title=t["title"],
            description=t["description"],
            estimated_minutes=int(t["estimated_minutes"]),
            prerequisites=t.get("prerequisites", []),
            status=t.get("status", "pending"),
        ))
        
    return StudyRoadmap(
        goal=data["goal"],
        total_weeks=int(data["total_weeks"]),
        weekly_hours=int(data.get("weekly_hours", 5)),
        topics=topics,
    )
    
def curriculum_planner_node(state: dict) -> dict:
    """
    LangGraph node: Curriculm Planner
    
    Reads: state["goal"]
    Writes: satate["roadmap"], state["messages"], state["error"]
    """
    
    goal = state.get("goal","").strip()
    if not goal:
        return {"error" : "No learning goal provided"}
    
    print(f"\n[Curriculum Planner] Building roadmap for: '{goal}'")

    llm = build_planner_llm()
    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=f"Create a study roadmap for: {goal}")
    ]
    
    print(f"[Curriculum Planner] Calling {MODEL_NAME}...")
    response = llm.invoke(messages)
    
    try:
        roadmap = parse_roadmap_json(response.content) # type: ignore
    except ValueError as e:
        print(f"[Curriculum Planner] Parse error: {e}")
        return {
            "error": str(e),
            "messages": messages + [response],
        }

    print(f"[Curriculum Planner] Created {len(roadmap.topics)} topics")
    

    return {
        "roadmap": roadmap,
        "messages": messages + [response],
        "error": None,
    }