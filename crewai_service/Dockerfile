FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY crewai_service/pyproject.toml crewai_service/uv.lock ./
RUN uv sync --frozen --no-dev

COPY crewai_service/crewai_service ./crewai_service

EXPOSE 9002

CMD ["uv", "run", "--no-sync", "python", "-m", "crewai_service"]
