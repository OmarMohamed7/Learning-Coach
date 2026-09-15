"""Typed access to the .env configuration for the Learning Accelerator."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _as_bool(value: str) -> bool:
    return value.strip().lower() in _TRUE_VALUES


class Settings(BaseModel):
    # Model configuration
    ollama_model: str
    ollama_base_url: str

    # Storage
    checkpoint_db: Path
    notes_path: Path

    # Langfuse observability (optional — empty keys disable tracing)
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str

    # A2A service URLs
    quiz_service_url: str
    study_buddy_url: str

    # A2A feature toggles
    use_a2a_quiz: bool
    use_study_buddy: bool

    # MCP servers — long-running processes reached over streamable-http.
    mcp_filesystem_url: str
    mcp_memory_url: str

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @classmethod
    def from_env(cls, env_file: str | Path = ".env") -> "Settings":
        load_dotenv(env_file, override=False)

        return cls(
            ollama_model=os.environ["OLLAMA_MODEL"],
            ollama_base_url=os.environ["OLLAMA_BASE_URL"],
            checkpoint_db=Path(os.environ["CHECKPOINT_DB"]),
            notes_path=Path(os.environ["NOTES_PATH"]),
            langfuse_public_key=os.environ.get("LANGFUSE_PUBLIC_KEY") or None,
            langfuse_secret_key=os.environ.get("LANGFUSE_SECRET_KEY") or None,
            langfuse_host=os.environ["LANGFUSE_HOST"],
            quiz_service_url=os.environ["QUIZ_SERVICE_URL"],
            study_buddy_url=os.environ["STUDY_BUDDY_URL"],
            use_a2a_quiz=_as_bool(os.environ["USE_A2A_QUIZ"]),
            use_study_buddy=_as_bool(os.environ["USE_STUDY_BUDDY"]),
            mcp_filesystem_url=os.environ.get("MCP_FILESYSTEM_URL")
            or "http://localhost:8001/mcp",
            mcp_memory_url=os.environ.get("MCP_MEMORY_URL")
            or "http://localhost:8002/mcp",
        )


settings = Settings.from_env()
