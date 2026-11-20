"""Core data model: every citizen/user owns conversations, tasks and long-term memories.

Domain-specific tables (appointments, permits, tickets...) get added once the
hackathon challenge is announced; `Task.data` (JSON) covers them until then.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)  # language, city, age, needs...
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.created_at", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    agent: Mapped[str | None] = mapped_column(String(64))  # which specialist answered
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Task(Base):
    """Anything an agent does on the user's behalf: a request, appointment, reminder, ticket."""

    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(32), default="open")  # open|in_progress|done|cancelled
    due_at: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Memory(Base):
    """Long-term facts an agent learned about the user (shared across all agents)."""

    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Place(Base):
    """A point of interest in Milan imported from dati.comune.milano.it (see app/opendata.py)."""

    __tablename__ = "places"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    category: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(300))
    address: Mapped[str | None] = mapped_column(String(300))
    nil: Mapped[str | None] = mapped_column(String(120))  # neighbourhood (Nucleo d'Identità Locale)
    municipio: Mapped[str | None] = mapped_column(String(8))
    lat: Mapped[float | None]
    lon: Mapped[float | None]
    data: Mapped[dict] = mapped_column(JSON, default=dict)  # remaining source columns
    source: Mapped[str] = mapped_column(String(200))
