from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import OrmBase


class Agent(OrmBase):
    """One row per distinct agent (explainer, quiz_generator, progress_coach, ...)."""

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True, index=True)

    versions: Mapped[list["AgentVersion"]] = relationship(
        back_populates="agent", order_by="AgentVersion.version"
    )


class AgentVersion(OrmBase):
    """A single version of an agent's prompt/config.

    Exactly one row per agent has is_latest=True; creating a new version
    flips the previous latest off in the same transaction (see
    `create_new_version`).
    """

    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version", name="uq_agent_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), index=True)
    version: Mapped[int]
    is_latest: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    agent: Mapped["Agent"] = relationship(back_populates="versions")


async def create_new_version(session: AsyncSession, agent_name: str) -> AgentVersion:
    """Add a new version for `agent_name`, marking it latest and un-flagging the old one."""
    result = await session.execute(select(Agent).where(Agent.name == agent_name))
    agent = result.scalar_one_or_none()
    if agent is None:
        agent = Agent(name=agent_name)
        session.add(agent)
        await session.flush()  # populate agent.id

    result = await session.execute(
        select(AgentVersion).where(
            AgentVersion.agent_id == agent.id, AgentVersion.is_latest == True
        )
    )
    current_latest = result.scalar_one_or_none()
    next_version = 1 if current_latest is None else current_latest.version + 1
    if current_latest is not None:
        current_latest.is_latest = False

    new_version = AgentVersion(
        agent_id=agent.id,
        version=next_version,
        is_latest=True,
    )
    session.add(new_version)
    await session.commit()
    await session.refresh(new_version)
    return new_version


async def get_agents(session: AsyncSession):
    res = await session.execute(
        select(Agent.name)
    )
    
    return res.scalars().all()

async def get_latest_version(session: AsyncSession, agent_name: str) -> AgentVersion | None:
    result = await session.execute(
        select(AgentVersion)
        .join(Agent)
        .where(Agent.name == agent_name, AgentVersion.is_latest == True)  # noqa: E712
    )
    return result.scalar_one_or_none()
