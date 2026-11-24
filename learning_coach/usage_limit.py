"""Per-user daily cap on study goals (each goal triggers ~10-20 LLM calls, so this is the cost guard).

Stored in Postgres so opening a new chat, reloading, or redeploying does not reset it.
Window is rolling: a slot frees up 24h after the goal that used it.
"""
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, func, select, text
from sqlalchemy.orm import Mapped, mapped_column

from database import AsyncSessionLocal, OrmBase

DAILY_GOAL_LIMIT = int(os.getenv("DAILY_GOAL_LIMIT", "5"))
WINDOW = timedelta(hours=24)


class GoalUsage(OrmBase):
    """One row per study goal a user started."""

    __tablename__ = "goal_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )


async def try_consume_goal(user_id: str) -> tuple[bool, int, datetime | None]:
    """Record one goal for `user_id` if they are under the limit.

    Returns (allowed, remaining_after_this, retry_at). retry_at is set only when refused.
    A transaction-scoped advisory lock per user stops two tabs from both taking the last slot.
    """
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
