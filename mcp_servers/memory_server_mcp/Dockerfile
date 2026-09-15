FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "mcp==1.26.0"

# Shared logging package
COPY logger_lib/logger ./logger

COPY mcp_servers/memory_server_mcp/memory_server.py .

EXPOSE 8002

CMD ["python", "memory_server.py"]
