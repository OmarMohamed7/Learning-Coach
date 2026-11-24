# Single container for Render's free tier: Chainlit app + both MCP servers (one process, localhost only).
# Build context is the repo root. Secrets (DATABASE_URL, OLLAMA_API_KEY, GROQ_API_KEY, CHAINLIT_AUTH_SECRET,
# LANGFUSE_*) are set in the Render dashboard, never here.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY learning_coach/pyproject.toml learning_coach/pyproject.toml
COPY mcp_servers/pyproject.toml mcp_servers/pyproject.toml
COPY logger_lib logger_lib
COPY learning_coach/src learning_coach/src
RUN uv sync --frozen --no-dev --package learning-coach

COPY learning_coach learning_coach
COPY mcp_servers mcp_servers
COPY deploy/render/start.sh /app/start.sh

ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/learning_coach" \
    LLM_PROVIDER=ollama OLLAMA_BASE_URL=https://ollama.com OLLAMA_MODEL=gpt-oss:120b FALLBACK_LLM_PROVIDER=groq \
    MCP_FILESYSTEM_URL=http://127.0.0.1:8001/mcp MCP_MEMORY_URL=http://127.0.0.1:8002/mcp \
    NOTES_PATH=study_materials/sample_notes CHECKPOINT_DB=data/checkpoints.db \
    USE_A2A_QUIZ=false USE_STUDY_BUDDY=false QUIZ_SERVICE_URL=http://unused:9001 STUDY_BUDDY_URL=http://unused:9002 \
    LANGFUSE_BASE_URL=https://us.cloud.langfuse.com LANGFUSE_TRACING_ENVIRONMENT=production DAILY_GOAL_LIMIT=2 LOG_LEVEL=INFO

CMD ["/app/start.sh"]
