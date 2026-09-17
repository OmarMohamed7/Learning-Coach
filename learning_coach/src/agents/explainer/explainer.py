
import json
import os

from dotenv import load_dotenv
from graph.state import get_current_topic
from mcp_client.client import get_mcp_tools
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

from logger import get_logger

load_dotenv()

MODEL_NAME = os.getenv("OLLAMA_MODEL", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")

logger = get_logger(__name__)


tools: dict[str,BaseTool] = {}
async def get_mcps_tools() :
    tools = await get_mcp_tools()
    print(f"Discovered {len(tools)} tools:")
    
    tools = {t.name: t for t in tools}
    
    print(tools)
    
EXPLAINER_SYSTEM_PROMPT = """You are an expert tutor explaining topics to a student.

Your explanations must be grounded in the student's actual study materials.
Use the available tools to find and read relevant notes before explaining.

APPROACH (follow this sequence):
1. Call list_study_files() to see what materials are available
2. Call search_notes(topic) to find which files cover this topic
3. Call read_study_file(filename) to read the most relevant file(s)
4. Check prior context: call memory_get(session_id, 'explained_topics')
5. Write your explanation based on what you found in the notes

EXPLANATION FORMAT:
- Start with a real-world analogy (1-2 sentences)
- State the core concept clearly (2-3 sentences)
- Show a concrete code example from the student's notes
- End with one common mistake or gotcha to watch out for

After writing the explanation, store what you explained:
  memory_set(session_id, 'explained_topics', <comma-separated topic titles>)
"""

def execute_tool_call(tool_call: dict) -> str:
  """ Execute a tool call and return the result as a string. Never raises."""
  
  assert len(tools.keys()) > 0
  
  name = tool_call['name']
  args = tool_call['args']
  
  if name not in tools.keys():
    return f"Error: unkown tool `{name}`"
  
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
  
  llm = ChatOllama(
        model=MODEL_NAME,
        base_url=OLLAMA_BASE_URL,
        temperature=0.3,
        format='json'
    ).bind_tools(tools=[t for t in tools.values()])
  
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
    logger.info(f'[Explaainer] LLM Call {iteration+1} / {max_iteration}')
    
    res = llm.invoke(messages)
    messages.append(res)
    
    if not res.tool_calls:
      final_res = res
      logger.info(f"[Explainer] Complete after {iteration + 1} LLM call(s)")
      break
    
    logger.info(f"[Explainer] {len(res.tool_calls)} tool call(s) requested:")
    for tool_call in res.tool_calls:
      logger.info(f" -> {tool_call['name']}({tool_call['args']})")
      result = execute_tool_call({
        tool_call['name']: tool_call['args']
      })
      
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
  return {"messages": messages , "error": None}

  

if __name__ == '__main__':
    import asyncio
    asyncio.run(get_mcps_tools())
    
    