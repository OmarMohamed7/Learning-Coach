# Learning Coach

A multi-agent learning assistant: four LangGraph-orchestrated agents plan a curriculum, explain material, generate quizzes, and coach progress — backed by MCP tool servers, cross-framework A2A delegation, local LLM inference, and full observability.

## Architecture

```
USER
  │ learning goal / yes-per-per-approval / quiz answers
  ▼
ORCHESTRATION LAYER (LangGraph workflow)
  Curriculum Planner → Human Approval → Explainer → Quiz Generator → Progress Coach
  │                                                        │
  │ checkpoints after every node                           │ callback traces
  ▼                                                        ▼
SQLite checkpoint store                          OBSERVABILITY LAYER (Langfuse)
```

The orchestration layer reads notes and session context, and writes progress, through the **tool layer**; the Quiz Generator node also delegates over **A2A** to standalone agent services; every node fans in to a local **inference layer**.

### Orchestration layer — LangGraph workflow

A single LangGraph graph with checkpointing after every node (SQLite-backed, so a session can pause and resume):

| Node                   | Responsibility                                                                 |
| ---------------------- | ------------------------------------------------------------------------------ |
| **Curriculum Planner** | Turns a learning goal into an ordered study plan                               |
| **Human Approval**     | Interrupts the graph for the user to approve/reject (yes/no) before proceeding |
| **Explainer**          | Reads source notes via MCP and explains the current topic                      |
| **Quiz Generator**     | Generates quiz questions, delegating to an A2A service that shares its logic   |
| **Progress Coach**     | Scores quiz answers and writes progress back via MCP                           |

### Tool layer — MCP servers

| Server                    | Tools                                                           |
| ------------------------- | --------------------------------------------------------------- |
| **MCP Filesystem Server** | `list_study_files`, `read_study_file`, `search_notes`           |
| **MCP Memory Server**     | `memory_set`, `memory_get`, `memory_list_keys`, `memory_delete` |

### A2A layer — cross-framework delegation

Agents exposed as standalone services over JSON-RPC 2.0, callable from the LangGraph workflow (and from each other) regardless of framework:

| Service                        | Port   | Notes                                                                        |
| ------------------------------ | ------ | ---------------------------------------------------------------------------- |
| **Quiz Generator A2A Service** | `9001` | Shares logic with the in-graph Quiz Generator agent                          |
| **CrewAI Study Buddy**         | `9002` | Built on a different framework (CrewAI), reachable via the same A2A protocol |

### Inference layer

All LLM calls fan in to a local **Ollama** server (`localhost:11434`), using `qwen2.5:7b` or `qwen2.5-coder:32b` depending on the task.

### Observability layer

**Langfuse** captures every LLM call, tool call, and node execution as a trace via callbacks from the orchestration layer.

## Tech stack

- **Orchestration:** [LangGraph](https://github.com/langchain-ai/langgraph) + LangChain core, with SQLite/Postgres checkpointers
- **Tool access:** [MCP](https://modelcontextprotocol.io/) (Model Context Protocol)
- **Cross-framework delegation:** [A2A SDK](https://github.com/a2aproject/A2A) (JSON-RPC 2.0)
- **Secondary agent framework:** [CrewAI](https://github.com/crewAIInc/crewAI)
- **Observability:** [Langfuse](https://langfuse.com/)
- **Evaluation:** [DeepEval](https://github.com/confident-ai/deepeval)
- **Local inference:** [Ollama](https://ollama.com/)
- **API/serving:** FastAPI, Uvicorn, Streamlit

## Setup

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Pull the local models with Ollama:

```bash
ollama pull qwen2.5:7b
ollama pull qwen2.5-coder:32b
```

Start Ollama (if not already running):

```bash
ollama serve
```

## Running

```bash
uv run main.py
```

The A2A services (Quiz Generator on `9001`, CrewAI Study Buddy on `9002`) and MCP servers are started separately as the corresponding modules are built out.
