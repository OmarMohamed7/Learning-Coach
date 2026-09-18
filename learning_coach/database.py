
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/learning_coach_db"

# langgraph's AsyncPostgresSaver uses psycopg, not asyncpg/SQLAlchemy — same DB, different driver/DSN scheme.
CHECKPOINT_DB_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

engine = create_async_engine(DATABASE_URL, echo=True)

# Create session maker
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base class for models
class OrmBase(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session