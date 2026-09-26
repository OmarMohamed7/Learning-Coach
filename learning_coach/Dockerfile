# Runs both the Chainlit app and the quiz A2A service (different CMD, same image).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy PYTHONUNBUFFERED=1

# Workspace manifests first so the dependency layer caches.
COPY pyproject.toml uv.lock ./
COPY learning_coach/pyproject.toml learning_coach/pyproject.toml
COPY mcp_servers/pyproject.toml mcp_servers/pyproject.toml
COPY logger_lib logger_lib
COPY learning_coach/src learning_coach/src
RUN uv sync --frozen --no-dev --package learning-coach

COPY learning_coach learning_coach
WORKDIR /app/learning_coach
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/learning_coach"

EXPOSE 8000
CMD ["chainlit", "run", "chainlit_app.py", "--host", "0.0.0.0", "--port", "8000", "--headless"]
