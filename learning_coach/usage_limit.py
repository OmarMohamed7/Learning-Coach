"""Per-user cap on study goals in a rolling 24h window, stored in Postgres."""
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, func, select, text
from sqlalchemy.orm import Mapped, mapped_column

from database import AsyncSessionLocal, OrmBase

DAILY_GOAL_LIMIT = int(os.getenv("DAILY_GOAL_LIMIT", "2"))
WINDOW = timedelta(hours=24)


class GoalUsage(OrmBase):
    __tablename__ = "goal_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )


async def try_consume_goal(user_id: str) -> tuple[bool, int, datetime | None]:
    """Record a goal if under the limit. Returns (allowed, remaining, retry_at)."""
    since = datetime.now(timezone.utc) - WINDOW
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:uid))"), {"uid": user_id})
        used, oldest = (
            await session.execute(
                select(func.count(GoalUsage.id), func.min(GoalUsage.created_at)).where(
                    GoalUsage.user_id == user_id, GoalUsage.created_at > since
                )
            )
        ).one()
        if used >= DAILY_GOAL_LIMIT:
            return False, 0, oldest + WINDOW
        session.add(GoalUsage(user_id=user_id))
    return True, DAILY_GOAL_LIMIT - used - 1, None
