"""Tools agents can call. Each factory closes over the current user and DB session,
so an agent can only ever touch the data of the user it is serving."""
import json
from collections.abc import Callable

from anthropic import beta_async_tool
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import math

from ..models import Memory, Place, Task
from ..opendata import CATEGORIES


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


def _km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def _find_places(db: AsyncSession, user_id: str, agent: str):
    @beta_async_tool
    async def find_places(category: str, near: str = "", neighbourhood: str = "",
                          query: str = "", limit: int = 5) -> str:
        """Search real points of interest in Milan (official open data of the Comune di Milano).

        Categories: pharmacy, metro_stop, bus_tram_stop, recycling_center, water_house,
        street_market, mm_housing_office.

        Args:
            category: One of the categories above.
            near: Optional landmark to sort by distance from, given as the name of a metro
                station or stop (e.g. "Duomo", "Loreto"). Use this when the user names a place.
            neighbourhood: Optional NIL neighbourhood name, e.g. "Isola", "Navigli", "Città Studi".
            query: Optional words to match in the name or address.
            limit: Max results (default 5).
        """
        if category not in CATEGORIES:
            return f"error: unknown category; use one of {sorted(CATEGORIES)}"
        stmt = select(Place).where(Place.category == category)
        if neighbourhood:
            stmt = stmt.where(Place.nil.ilike(f"%{neighbourhood}%"))
        for w in query.split():
            stmt = stmt.where(or_(Place.name.ilike(f"%{w}%"), Place.address.ilike(f"%{w}%")))
        rows = (await db.scalars(stmt.limit(5000))).all()
        origin = None
        if near:
            anchor = await db.scalar(
                select(Place).where(Place.category.in_(["metro_stop", "bus_tram_stop"]),
                                    Place.name.ilike(f"%{near}%"), Place.lat.is_not(None))
                .order_by(Place.category.desc()).limit(1))  # prefer metro over surface
            if anchor is None:
                return f"error: no metro or bus stop matching '{near}' to measure distance from"
            origin = (anchor.lat, anchor.lon, anchor.name)
            rows = sorted((r for r in rows if r.lat is not None),
                          key=lambda r: _km(origin[0], origin[1], r.lat, r.lon))
        out = []
        for r in rows[: max(1, min(limit, 20))]:
            item = {"name": r.name, "address": r.address, "neighbourhood": r.nil,
                    "municipio": r.municipio, "lat": r.lat, "lon": r.lon, "info": r.data}
            if origin:
                item["km_from_" + origin[2]] = round(_km(origin[0], origin[1], r.lat, r.lon), 2)
            out.append(item)
        if not out:
            return "[] (no match; data may not be imported yet: run `make data`)"
        return json.dumps(out, ensure_ascii=False)

    return find_places


TOOL_FACTORIES: dict[str, Callable] = {
    "find_places": _find_places,
    "remember": _remember,
    "recall": _recall,
    "create_task": _create_task,
    "list_tasks": _list_tasks,
    "update_task": _update_task,
}
