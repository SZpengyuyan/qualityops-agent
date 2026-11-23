from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    base_url: Mapped[str] = mapped_column(String(2048))
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(40), default=utc_now, onupdate=utc_now)


class OpenAPIDocument(Base):
    __tablename__ = "openapi_documents"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    api_version: Mapped[str] = mapped_column(Text)
    openapi_version: Mapped[str] = mapped_column(String(20))
    imported_at: Mapped[str] = mapped_column(String(40), default=utc_now)
    spec: Mapped[dict] = mapped_column(JSON)
    operations: Mapped[list] = mapped_column(JSON)


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    operation_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(10))
    request: Mapped[dict] = mapped_column(JSON)
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assertions: Mapped[list] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)
