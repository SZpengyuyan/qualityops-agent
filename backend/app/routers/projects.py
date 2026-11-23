from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import OpenAPIDocument, Project
from app.schemas import ProjectInput, ProjectList, ProjectRead

router = APIRouter(prefix="/api/projects", tags=["projects"])
DatabaseSession = Annotated[Session, Depends(get_session)]


def find_project(project_id: UUID, session: Session) -> Project:
    project = session.get(Project, str(project_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("", response_model=ProjectList)
def list_projects(
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    total = session.scalar(select(func.count()).select_from(Project))
    items = session.scalars(
        select(Project).order_by(Project.created_at.desc(), Project.id).limit(limit).offset(offset)
    ).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectInput, session: DatabaseSession):
    project = Project(**payload.model_dump())
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: UUID, session: DatabaseSession):
    return find_project(project_id, session)


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(project_id: UUID, payload: ProjectInput, session: DatabaseSession):
    project = find_project(project_id, session)
    for field, value in payload.model_dump().items():
        setattr(project, field, value)
    session.commit()
    session.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: UUID, session: DatabaseSession):
    project = find_project(project_id, session)
    document = session.get(OpenAPIDocument, str(project_id))
    if document:
        session.delete(document)
        session.flush()
    session.delete(project)
    session.commit()
    return Response(status_code=204)
