

from dataclasses import asdict, field

from pydantic import BaseModel, Field
from pydantic.dataclasses import dataclass


from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

type statuses = Literal["pending","in_progress","completed","needs_review"]

@dataclass
class Topic:
    """ A single topic within study roadmap"""
    title: str
    description: str
    estimated_minutes: int
    prerequisites: list[str] = field(default_factory=list)
    status: statuses = "pending" 
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data:dict) -> "Topic":
        return cls(
            title = data['title'],
            description = data['description'],
            estimated_minutes = data['estimated_minutes'],
            prerequisites = data.get('prerequisites',[]),
            status = data['status']
        )
        
@dataclass
class StudyRoadmap:
    """ The full study plan produced by the Curriculum Planner. """
    total_weeks: int
    topics: list[Topic]
    goal: str = Field(min_length=3, max_length=500) # type: ignoreß
    weekly_hours: int = 5
    
    def is_complete(self) -> bool:
        return all(t.status in ("completed", "needs_review") for t in self.topics)
    
@dataclass
class QuizQuestion:
    """The Question of quiz."""
    question: str
    expected_answer: str
    user_answer: str
    correct: bool
    score: float
    feedback: str = ""

@dataclass
class QuizResult:
    """The complete result of one quiz session on a single topic."""
    topic: str
    questions: list
    score: float       # 0.0 to 1.0
    weak_areas: list[str]
    timestamp: str = ""
    
    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "score": self.score,
            "weak_areas": self.weak_areas,
            "timestamp": self.timestamp,
            "questions": [q.to_dict() for q in self.questions],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QuizResult":
        """
        Reconstruct from a plain dict.

        Called when LangGraph deserializes quiz_results from a SQLite
        checkpoint as raw dicts (msgpack round-trip). This happens when
        resuming a crashed or interrupted session.
        """
        return cls(
            topic=data.get("topic", ""),
            questions=[],           # Questions not needed for coaching logic
            score=float(data.get("score", 0.0)),
            weak_areas=data.get("weak_areas", []),
            timestamp=data.get("timestamp", ""),
        )

    def passed(self) -> bool:
        """A score of 0.5 or above is considered a pass."""
        return self.score >= 0.5

    def strong_pass(self) -> bool:
        """A score of 0.75 or above, ready to move to next topic."""
        return self.score >= 0.75

    
    
class AgentState(TypedDict):
    """
    This shared state for the Learning Coach
    
    Partial updates: when a node returns {"approved": True}, Langgraph merges that
    into exsiting state. It doesn't replace the whole dict.
    Nodes only return the key they changed.
    
    The one exception is `messages`: it uses add_messages reducer, which appends
    to the list instead of replacing it.
    """
    
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    goal: str
    roadmap: StudyRoadmap | None
    approved: bool
    current_topic_index: int
    quiz_results: list[QuizResult]
    weak_areas: list[str]
    study_materials_path: str
    error: str | None
    
# Utilities functions that agent nodes use to read from state safely

def initial_state(
    goal: str,
    session_id: str,
    study_materials_path: str = "study_materials/sample_notes",
) -> dict:
    """ Create the initial state of a new study session"""
    return {
        "messages":[],
        "session_id": session_id,
        "goal": goal,
        "roadmap": None,
        "approved": False,
        "current_topic_index": 0,
        "quiz_results" : [],
        "weak_areas": [],
        "study_materials_path": study_materials_path,
        "error": None
    }
    
    
def get_current_topic(state: dict) -> Topic | None:
    """ Get the current topic being studied, or None if done"""
    
    roadmap: StudyRoadmap | None = state.get("roadmap")
    if roadmap is None:
        return None
    
    idx = state.get("current_topic_index", 0)
    if idx >= len(roadmap.topics): 
        return None
    return roadmap.topics[idx]

def session_is_complete(state:dict) -> bool:
    roadmap: StudyRoadmap| None = state.get("roadmap")
    if roadmap is None:
        return False
    
    idx = state.get("current_topic_index", 0)
    return idx >= len(roadmap.topics)

def get_latest_quiz_result(state:dict) -> QuizResult | None:
    
    res = state.get("quiz_results", [])
    if not res:
        return None
    
    latest = res[-1]
    
    if isinstance(latest , dict):
        return QuizResult.from_dict(latest)
    
    return latest