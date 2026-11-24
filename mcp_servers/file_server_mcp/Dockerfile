FROM python:3.12-slim

WORKDIR /app


RUN pip install --no-cache-dir "mcp==1.26.0"

# Shared logging package
COPY logger_lib/logger ./logger

COPY mcp_servers/file_server_mcp/filesystem_server.py .
COPY mcp_servers/file_server_mcp/audit_query.py .

# Notes are baked in (Cloud Run has no host volumes); rebuild the image to update them.
COPY learning_coach/study_materials/sample_notes ./study_materials/sample_notes
ENV NOTES_PATH=/app/study_materials/sample_notes

EXPOSE 8001

CMD ["python", "filesystem_server.py"]
