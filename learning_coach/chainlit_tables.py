"""DDL for the tables Chainlit's SQLAlchemyDataLayer needs (chat history and resume).

Column names are camelCase and quoted because that is what the data layer's raw SQL expects.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS users (
        "id" UUID PRIMARY KEY,
        "identifier" TEXT NOT NULL UNIQUE,
        "metadata" JSONB NOT NULL,
        "createdAt" TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS threads (
        "id" UUID PRIMARY KEY,
        "createdAt" TEXT,
        "name" TEXT,
        "userId" UUID,
        "userIdentifier" TEXT,
        "tags" TEXT[],
        "metadata" JSONB,
        FOREIGN KEY ("userId") REFERENCES users("id") ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS steps (
        "id" UUID PRIMARY KEY,
        "name" TEXT NOT NULL,
        "type" TEXT NOT NULL,
        "threadId" UUID NOT NULL,
        "parentId" UUID,
        "streaming" BOOLEAN NOT NULL,
        "waitForAnswer" BOOLEAN,
        "isError" BOOLEAN,
        "metadata" JSONB,
        "tags" TEXT[],
        "input" TEXT,
        "output" TEXT,
        "createdAt" TEXT,
        "command" TEXT,
        "start" TEXT,
        "end" TEXT,
        "generation" JSONB,
        "showInput" TEXT,
        "language" TEXT,
        "indent" INT,
        "defaultOpen" BOOLEAN
    )""",
    """CREATE TABLE IF NOT EXISTS elements (
        "id" UUID PRIMARY KEY,
        "threadId" UUID,
        "type" TEXT,
        "chainlitKey" TEXT,
        "url" TEXT,
        "objectKey" TEXT,
        "name" TEXT NOT NULL,
        "display" TEXT,
        "size" TEXT,
        "language" TEXT,
        "page" INT,
        "autoPlay" BOOLEAN,
        "playerConfig" JSONB,
        "forId" UUID,
        "mime" TEXT,
        "props" JSONB
    )""",
    """CREATE TABLE IF NOT EXISTS feedbacks (
        "id" UUID PRIMARY KEY,
        "forId" UUID NOT NULL,
        "threadId" UUID NOT NULL,
        "value" INT NOT NULL,
        "comment" TEXT
    )""",
]


async def create_chainlit_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for statement in _STATEMENTS:
            await conn.execute(text(statement))
