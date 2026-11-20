"""Tools agents can call. Each factory closes over the current user and DB session,
so an agent can only ever touch the data of the user it is serving."""
import json
from collections.abc import Callable

from anthropic import beta_async_tool
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Memory, Task


def build_tools(names: list[str], *, db: AsyncSession, user_id: str, agent: str) -> list:
    return [TOOL_FACTORIES[n](db, user_id, agent) for n in names]


def _remember(db: AsyncSession, user_id: str, agent: str):
    @beta_async_tool
    async def remember(fact: str) -> str:
        """Save a durable fact about the user (e.g. "lives in Turin", "allergic to penicillin").

        Args:
            fact: One short self-contained sentence.
        """
        db.add(Memory(user_id=user_id, agent=agent, content=fact))
        await db.commit()
        return "saved"

    return remember


def _recall(db: AsyncSession, user_id: str, agent: str):
    @beta_async_tool
    async def recall(query: str = "") -> str:
        """Look up facts previously saved about the user, from any agent.

        Args:
            query: Optional keywords; empty returns the most recent facts.
        """
        stmt = select(Memory).where(Memory.user_id == user_id)
        words = [w for w in query.split() if len(w) > 2]
        if words:
            stmt = stmt.where(or_(*[Memory.content.ilike(f"%{w}%") for w in words]))
        rows = (await db.scalars(stmt.order_by(Memory.created_at.desc()).limit(20))).all()
        return json.dumps([{"fact": m.content, "by": m.agent} for m in rows]) or "[]"

    return recall


def _create_task(db: AsyncSession, user_id: str, agent: str):
    @beta_async_tool
    async def create_task(title: str, due_at: str = "", details: str = "") -> str:
        """Track a request, appointment, reminder or follow-up for the user.

        Args:
            title: Short description, e.g. "Renew ID card".
            due_at: Optional ISO date/time or free text deadline.
            details: Optional extra info (documents needed, office, notes).
        """
        task = Task(
            user_id=user_id, agent=agent, title=title, due_at=due_at or None,
            data={"details": details} if details else {},
        )
        db.add(task)
        await db.commit()
        return json.dumps({"task_id": task.id, "status": task.status})

    return create_task


def _list_tasks(db: AsyncSession, user_id: str, agent: str):
    @beta_async_tool
    async def list_tasks(status: str = "") -> str:
        """List the user's tasks across all agents.

        Args:
            status: Optional filter: open, in_progress, done, cancelled.
        """
        stmt = select(Task).where(Task.user_id == user_id)
        if status:
            stmt = stmt.where(Task.status == status)
        rows = (await db.scalars(stmt.order_by(Task.created_at.desc()).limit(50))).all()
        return json.dumps([
            {"id": t.id, "title": t.title, "status": t.status, "due_at": t.due_at, "agent": t.agent}
            for t in rows
        ])

    return list_tasks


def _update_task(db: AsyncSession, user_id: str, agent: str):
    @beta_async_tool
    async def update_task(task_id: str, status: str) -> str:
        """Change a task's status.

        Args:
            task_id: The id returned by create_task or list_tasks.
            status: One of open, in_progress, done, cancelled.
        """
        if status not in {"open", "in_progress", "done", "cancelled"}:
            return "error: invalid status"
        task = await db.get(Task, task_id)
        if task is None or task.user_id != user_id:
            return "error: task not found"
        task.status = status
        await db.commit()
        return "updated"

    return update_task


TOOL_FACTORIES: dict[str, Callable] = {
    "remember": _remember,
    "recall": _recall,
    "create_task": _create_task,
    "list_tasks": _list_tasks,
    "update_task": _update_task,
}
