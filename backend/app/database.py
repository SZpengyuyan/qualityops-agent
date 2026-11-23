"""Database configuration and session lifecycle."""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str):
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("This MVP supports SQLite only")
    if url.database and url.database != ":memory:":
        path = Path(url.database)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        path.parent.mkdir(parents=True, exist_ok=True)
        url = url.set(database=str(path))
    return create_engine(url, connect_args={"check_same_thread": False})


def create_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def configured_database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./data/qualityops.db")


def get_session(request: Request):
    with request.app.state.session_factory() as session:
        yield session
