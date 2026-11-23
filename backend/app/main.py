"""Application factory for health and project management endpoints."""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import Base, build_engine, configured_database_url, create_session_factory, get_session
from app.routers.projects import router as projects_router

logger = logging.getLogger(__name__)


def create_app(database_url: str | None = None) -> FastAPI:
    engine = build_engine(database_url or configured_database_url())
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title="QualityOps Agent", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.include_router(projects_router)

    @app.get("/")
    def root():
        return {"name": "QualityOps Agent", "version": "0.1.0", "docs": "/docs"}

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "qualityops-api"}

    @app.get("/api/health/db")
    def database_health(session: Session = Depends(get_session)):
        try:
            session.execute(text("SELECT 1")).scalar_one()
        except SQLAlchemyError:
            logger.exception("Database health check failed")
            return JSONResponse(
                status_code=503,
                content={"status": "error", "database": "sqlite"},
            )
        return {"status": "ok", "database": "sqlite"}

    return app


app = create_app()
