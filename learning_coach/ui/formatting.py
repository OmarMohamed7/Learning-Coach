"""How graph output is shown in the chat."""
from graph.state import StudyRoadmap

STAGE_DONE = {
    "curriculum_planner": "Study roadmap drafted",
    "human_approval": "Plan reviewed",
    "explainer": "Explanation prepared from your notes",
    "choose_next_step": "Next step chosen",
    "quiz_generator": "Quiz questions generated",
    "quiz_question": "Answer graded",
    "progress_coach": "Progress reviewed",
}


def format_roadmap(roadmap: StudyRoadmap) -> str:
    lines = [
        "### Proposed Study Plan",
        f"**Goal:** {roadmap.goal}",
        f"**Duration:** {roadmap.total_weeks} weeks @ {roadmap.weekly_hours} hrs/week",
        "",
    ]
    for i, topic in enumerate(roadmap.topics, 1):
        prereqs = f" _(needs: {', '.join(topic.prerequisites)})_" if topic.prerequisites else ""
        lines.append(f"{i}. **{topic.title}** ({topic.estimated_minutes} min){prereqs}")
        lines.append(f"   {topic.description}")
    return "\n".join(lines)


def format_explanation(explanation: dict) -> str:
    text = f"### 📘 Topic {explanation['index']}/{explanation['total']}: {explanation['topic']}\n\n{explanation['text']}"
    if not explanation.get("from_notes", True):
        text += "\n\n---\n_ℹ️ None of your study notes matched this topic, so it was explained from general knowledge._"
    return text


def format_grade(grade: dict) -> str:
    icon = "✅" if grade["correct"] else "❌"
    text = f"{icon} **Question {grade['index']}/{grade['total']} — score: {grade['score']:.0%}**"
    if grade.get("feedback"):
        text += f"\n\n{grade['feedback']}"
    if grade.get("correct_answer"):
        text += f"\n\n**Correct answer:** {grade['correct_answer']}"
    return text


def format_coach_note(note: dict) -> str:
    text = f"### 🎯 Progress Coach — {note['topic']}: {note['score']:.0%}\n\n{note['summary']}"
    if note.get("encouragement"):
        text += f"\n\n_{note['encouragement']}_"
    if note.get("next_topic"):
        text += f"\n\n**Up next:** {note['next_topic']}"
    else:
        text += "\n\n🎉 **You've finished every topic in your roadmap!**"
    return text


# Graph node -> (state key it writes for display, formatter)
DISPLAYED = {
    "explainer": ("explanation", format_explanation),
    "quiz_question": ("last_grade", format_grade),
    "progress_coach": ("coach_note", format_coach_note),
}


def describe_interrupt(payload: dict) -> str:
    """The pending question as plain text, for the trace output."""
    kind = payload.get("type")
    if kind == "quiz_question":
        return f"Question {payload['index']}/{payload['total']}: {payload['question']}"
    if kind == "next_step":
        return f"Asked whether to take the quiz on '{payload.get('topic')}' or move on."
    return "Asked to approve the proposed study plan."
