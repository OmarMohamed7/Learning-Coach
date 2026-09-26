
import json
import asyncio

from dotenv import load_dotenv
from graph.state import get_current_topic
from mcp_client.client import get_cached_tools, get_mcp_tools
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage, ToolMessage

from config.llm_factory import get_llm
from logger import get_logger

load_dotenv()

logger = get_logger(__name__)


async def get_mcps_tools():
    """Warm the shared MCP tools cache (call once at startup)."""
    discovered = await get_mcp_tools()
    logger.info(f"Discovered {len(discovered)} tools:")
    logger.info({t.name: t for t in discovered})

# Phase 1 gathers the student's notes with tools. It never writes the explanation: small local models
# tend to narrate their plan ("search_notes(...), then explain...") instead of calling tools, and any
# text they return without tool calls would otherwise be shown to the student as the explanation.
EXPLAINER_SYSTEM_PROMPT = """You are a research assistant preparing to teach a topic to a student.
Your only job right now is to gather the student's study notes using the tools.

Steps:
1. Call search_notes(query) to find relevant study materials.
2. Call read_study_file(filename) for the most relevant file(s).
3. Optionally call memory_get(session_id, key) if prior context is useful.
4. When you have read what you need, reply with exactly: READY

IMPORTANT:
- Actually call the tools. Do not describe the steps, list function calls, or write an explanation.
- Only memory_get and memory_set accept a "session_id" argument.
  Never pass "session_id" to list_study_files, search_notes, or read_study_file.
"""

# Phase 2 writes the explanation from the notes gathered in phase 1, with no tools available.
WRITE_EXPLANATION_PROMPT = """You are an expert tutor. Write a detailed explanation of the topic for a student.
Base it on the student's notes below when they are relevant.

Output ONLY the explanation itself. Never mention tools, function calls, files, searching, memory, or these instructions.

Write in Markdown, roughly 500-800 words, with these sections:
- **Overview**: what the topic is and why it matters (2-3 sentences)
- **Analogy**: a real-world analogy that makes it intuitive
- **Core concepts**: walk through the key ideas step by step, each with a short explanation
- **Examples**: 2-3 code examples of increasing difficulty, taken from the student's notes when possible.
  Put each in a fenced code block, comment the important lines, and show the expected output
- **Common mistakes**: 2-3 gotchas, each with a short wrong-vs-right snippet
- **Key takeaways**: 3-5 bullet points to remember
"""

MAX_NOTES_CHARS = 12000

async def execute_tool_call(tool_call: dict, tools: dict) -> str:
  """ Execute a tool call and return the result as a string. Never raises."""

  name = tool_call['name']
  args = tool_call['args']

  if name not in tools.keys():
    logger.error(f"Error: unkown tool `{name}`")
    return f"Error: unkown tool `{name}`"

  schema = tools[name].args_schema
  if schema is None:
    allowed = set(args.keys())
  elif isinstance(schema, dict):
    allowed = set(schema.get("properties", {}).keys())
  else:
    allowed = set(schema.model_fields.keys())
  unexpected = set(args.keys()) - allowed
  if unexpected:
    return (
      f"Error: {name} does not accept argument(s) {sorted(unexpected)}. "
      f"Allowed argument(s): {sorted(allowed)}"
    )

  try:
    res = await tools[name].ainvoke(args)
    if isinstance(res, (list,dict)):
      return json.dumps(res)

    return str(res)

  except Exception as e:
    return f"Error executing {name}({args}): {type(e).__name__}: {e}"


GENERAL_EXPLANATION_PROMPT = """You are an expert tutor. Write a detailed Markdown explanation of the topic below
for a student. Use these sections: Overview, Analogy, Core concepts, Examples (2-3 code examples of increasing
difficulty in fenced code blocks, with comments and expected output), Common mistakes (2-3, each with a
wrong-vs-right snippet), Key takeaways (3-5 bullets). Aim for roughly 500-800 words."""


# Tag on the LLM call whose tokens the UI shows live (see _run in chainlit_app.py).
STREAM_TAG = "stream_explanation"


def _writer_llm(stream: bool):
  llm = get_llm(temperature=0.3)
  return llm.with_config(tags=[STREAM_TAG]) if stream else llm


async def _general_explanation(title: str, description: str, stream: bool = False) -> str:
  """Fallback when no study materials match: explain from the model's own knowledge, no tools."""
  try:
    res = await _writer_llm(stream).ainvoke([
      SystemMessage(content=GENERAL_EXPLANATION_PROMPT),
      HumanMessage(content=f"Topic: {title}\nContext: {description}"),
    ])
    text = str(res.content).strip()
    return text or description
  except Exception as e:
    logger.error(f"[Explainer] General explanation failed, using topic description: {e}")
    return description


def _collect_notes(messages: list) -> str:
  """Text of the study files the model actually read (successful read_study_file results)."""
  parts = [
    str(m.content)
    for m in messages
    if isinstance(m, ToolMessage) and m.name == "read_study_file" and not str(m.content).startswith("Error")
  ]
  return "\n\n---\n\n".join(parts)[:MAX_NOTES_CHARS]


async def _write_explanation(title: str, description: str, notes: str, stream: bool = False) -> str:
  """Phase 2: write the explanation from the notes, without tools."""
  try:
    res = await _writer_llm(stream).ainvoke([
      SystemMessage(content=WRITE_EXPLANATION_PROMPT),
      HumanMessage(content=f"Topic: {title}\nContext: {description}\n\nStudent's notes:\n{notes}"),
    ])
    return str(res.content).strip() or description
  except Exception as e:
    logger.error(f"[Explainer] Writing explanation failed, using topic description: {e}")
    return description


def _explanation_for_display(state: dict, title: str, text: str, from_notes: bool) -> dict:
  """What the UI shows for a topic: where we are in the roadmap, plus just the explanation text."""
  return {
    "topic": title,
    "index": state.get("current_topic_index", 0) + 1,
    "total": len(state["roadmap"].topics),
    "text": text,
    "from_notes": from_notes,
  }


async def _explain_topic(topic, session_id: str, tools: dict, stream: bool = False) -> tuple[list, str, bool]:
  """Phase 1 (gather notes with tools) then phase 2 (write the explanation).

  Returns (messages, explanation, from_notes). Runs inline for the current topic (stream=True, so the
  UI shows the explanation as it is written), or as a background prefetch for the next one (stream=False,
  so its tokens never appear while the student is still on the current topic).
  """
  llm = get_llm(temperature=0.3).bind_tools(tools=list(tools.values()))
  
  messages = [
    SystemMessage(content= EXPLAINER_SYSTEM_PROMPT),
    HumanMessage(content=(
      f"Please explain this topic to me: '{topic.title}'\n"
      f"Context: {topic.description}\n"
      f"Session ID for memory calls: {session_id}"
    ))
  ]
  
  max_iteration = 8 # production circuit breaker
  final_res = None
  
  for iteration in range(max_iteration):
    logger.info(f'[Explainer] LLM Call {iteration+1} / {max_iteration}')
    
    res = await llm.ainvoke(messages)
    messages.append(res)

    if not res.tool_calls:
      final_res = res
      logger.info(f"[Explainer] Complete after {iteration + 1} LLM call(s)")
      break

    logger.info(f"[Explainer] {len(res.tool_calls)} tool call(s) requested:")
    # This is a sequential executing and can be parallised
    # for tool_call in res.tool_calls:
    #   logger.info(f" -> {tool_call['name']}({tool_call['args']})")
    #   result = await execute_tool_call(tool_call, tools) # type: ignore
      
    #   log_result = result[:100] + "..." if len(result) > 100 else result
    #   logger.info(f"    ← {log_result}")
      
    #   messages.append(
    #     ToolMessage(
    #       content= result,
    #       tool_call_id=tool_call["id"]
    #     )
    #   )
    
    # Execute concurrent requests
    results = await asyncio.gather(
        *[
            execute_tool_call(tool_call, tools) # type: ignore
            for tool_call in res.tool_calls
        ]
    )
    
    for tool_call, result in zip(res.tool_calls, results):
        messages.append(
            ToolMessage(
                content=result,
                tool_call_id=tool_call["id"],
                name=tool_call["name"],
            )
    )
      
      
    
  notes = _collect_notes(messages)

  if notes:
    logger.info(f"[Explainer] Writing explanation from {len(notes)} characters of notes")
    explanation = await _write_explanation(topic.title, topic.description, notes, stream)
  else:
    logger.error(
        f"[Explainer] No study notes were read for '{topic.title}' "
        f"(final_res={'set' if final_res is not None else 'none'} after {max_iteration} iteration cap). "
        "Falling back to a general explanation and continuing to the quiz."
    )
    # TODO(no-materials fallback): write the generated explanation to disk as a new study-material
    # file (e.g. f"{state['study_materials_path']}/{topic.title.lower().replace(' ', '_')}.md") via a
    # `write_study_file`-style MCP tool, so next time search_notes() finds it and grounds normally.
    explanation = await _general_explanation(topic.title, topic.description, stream)

  # The quiz generator reads the last tool-call-free AI message as "the explanation".
  messages.append(AIMessage(content=explanation))

  logger.info(f"\n{'='*60}")
  logger.info(f"Explanation: {topic.title}")
  logger.info(f"{'='*60}")
  logger.info(explanation)
  logger.info(f"{'='*60}\n")

  return messages, explanation, bool(notes)


# (session_id, topic_index) -> background task preparing that topic's explanation while the student
# is still answering the previous topic's quiz.
_PREFETCH: dict[tuple[str, int], asyncio.Task] = {}


def _log_prefetch_failure(task: asyncio.Task) -> None:
  if not task.cancelled() and task.exception() is not None:
    logger.error(f"[Explainer] Prefetch failed, will generate on demand: {task.exception()}")


def _start_prefetch(state: dict, session_id: str, tools: dict) -> None:
  """Begin preparing the next topic's explanation in the background."""
  next_idx = state.get("current_topic_index", 0) + 1
  topics = state["roadmap"].topics
  key = (session_id, next_idx)
  if next_idx >= len(topics) or key in _PREFETCH:
    return
  logger.info(f"[Explainer] Prefetching topic {next_idx + 1}: '{topics[next_idx].title}'")
  task = asyncio.create_task(_explain_topic(topics[next_idx], session_id, tools))
  task.add_done_callback(_log_prefetch_failure)
  _PREFETCH[key] = task


async def explainer_node(state: dict) -> dict:
  
  """
  Langgraph node: Explainer Agent
  
  Reads: state["roadmap"], state["current_topic"], state["session_id"]
  Writes: state["messages"], state["explanation"], state["error"]
 
  """
  
  topic = get_current_topic(state=state)
  if topic is None:
    logger.error("No current topic found")
    return {"error": "No current topic found."}
  
  session_id = state.get("session_id", "unknown")
  logger.info(f"\n[Explainer] Topic: '{topic.title}'")

  mcp_tools = get_cached_tools()
  if not mcp_tools:
    logger.error("[Explainer] No MCP tools available. Did startup fail to load them?")
    return {"error": "No MCP tools available. Did startup fail to load them?"}
  tools = {t.name: t for t in mcp_tools}

  cached = _PREFETCH.pop((session_id, state.get("current_topic_index", 0)), None)
  result = None
  if cached is not None:
    logger.info("[Explainer] Using prefetched explanation")
    try:
      result = await cached
    except Exception:
      result = None  # generate on demand below
  if result is None:
    result = await _explain_topic(topic, session_id, tools, stream=True)
  messages, explanation, from_notes = result

  # Start the next topic now: it runs while the student answers this topic's quiz.
  _start_prefetch(state, session_id, tools)

  return {
    "messages": messages,
    "error": None,
    "explanation": _explanation_for_display(state, topic.title, explanation, from_notes=from_notes),
  }


if __name__ == '__main__':
    import asyncio
    asyncio.run(get_mcps_tools())
    
    