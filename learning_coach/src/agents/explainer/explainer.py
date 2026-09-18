
import json

from dotenv import load_dotenv
from graph.state import get_current_topic
from mcp_client.client import get_cached_tools, get_mcp_tools
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

from config.llm_factory import get_llm
from logger import get_logger

load_dotenv()

logger = get_logger(__name__)


async def get_mcps_tools():
    """Warm the shared MCP tools cache (call once at startup)."""
    discovered = await get_mcp_tools()
    logger.info(f"Discovered {len(discovered)} tools:")
    logger.info({t.name: t for t in discovered})

EXPLAINER_SYSTEM_PROMPT = """You are an expert tutor explaining topics to a student.

Your explanations must be grounded in the student's actual study materials.
Use the available tools to find and read relevant notes before explaining.

APPROACH (follow this sequence):
1. Call list_study_files() to see what materials are available — this tool takes NO arguments
2. Call search_notes(query) to find which files cover this topic — takes only "query"
3. Call read_study_file(filename) to read the most relevant file(s) — takes only "filename"
4. Check prior context: call memory_get(session_id, key) — this is the ONLY tool besides memory_set that takes "session_id"
5. Write your explanation based on what you found in the notes

IMPORTANT: Only memory_get and memory_set accept a "session_id" argument.
Never pass "session_id" to list_study_files, search_notes, or read_study_file — call them with exactly the arguments named above, nothing else.

EXPLANATION FORMAT:
- Start with a real-world analogy (1-2 sentences)
- State the core concept clearly (2-3 sentences)
- Show a concrete code example from the student's notes
- End with one common mistake or gotcha to watch out for

After writing the explanation, store what you explained:
  memory_set(session_id, 'explained_topics', <comma-separated topic titles>)
"""

def execute_tool_call(tool_call: dict, tools: dict) -> str:
  """ Execute a tool call and return the result as a string. Never raises."""

  name = tool_call['name']
  args = tool_call['args']
  
  if name not in tools.keys():
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
    res = tools[name].invoke(args)
    if isinstance(res, (list,dict)):
      return json.dumps(res)
    
    return str(res)
    
  except Exception as e:
    return f"Error executing {name}({args}): {type(e).__name__}: {e}"


def explainer_node(state: dict) -> dict:
  
  """
  Langgraph node: Explainer Agent
  
  Reads: state["roadmap"], state["current_topic"], state["session_id"]
  Writes: state["messages"], state["error"]
 
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

  llm = get_llm(temperature=0.3, json_mode=True).bind_tools(tools=list(tools.values()))
  
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
    
    res = llm.invoke(messages)
    messages.append(res)
    
    if not res.tool_calls:
      final_res = res
      logger.info(f"[Explainer] Complete after {iteration + 1} LLM call(s)")
      break
    
    logger.info(f"[Explainer] {len(res.tool_calls)} tool call(s) requested:")
    for tool_call in res.tool_calls:
      logger.info(f" -> {tool_call['name']}({tool_call['args']})")
      result = execute_tool_call(tool_call, tools) # type: ignore
      
      log_result = result[:100] + "..." if len(result) > 100 else result
      logger.info(f"    ← {log_result}")
      
      messages.append(
        ToolMessage(
          content= result,
          tool_call_id=tool_call["id"]
        )
      )
    
  if final_res is None:
    return {
        "messages": messages,
        "error": f"Explainer reached max iterations ({max_iteration}).",
    }
    
  logger.info(f"[Explainer] Explaination: {len(final_res.content)} characters")

  logger.info(f"\n{'='*60}")
  logger.info(f"Explanation: {topic.title}")
  logger.info(f"{'='*60}")
  logger.info(final_res.content)
  logger.info(f"{'='*60}\n")

  return {"messages": messages , "error": None}

  

if __name__ == '__main__':
    import asyncio
    asyncio.run(get_mcps_tools())
    
    