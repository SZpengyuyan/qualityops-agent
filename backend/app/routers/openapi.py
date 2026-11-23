from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.models import OpenAPIDocument, utc_now
from app.routers.projects import DatabaseSession, find_project
from app.services.openapi import ImportError, parse_openapi

router = APIRouter(prefix="/api/projects/{project_id}", tags=["openapi"])


class ImportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=2, max_length=1024 * 1024)


class DocumentRead(BaseModel):
    project_id: str
    title: str
    api_version: str
    openapi_version: str
    imported_at: str
    operation_count: int
    tags: list[str]


class OperationRead(BaseModel):
    id: str
    method: str
    path: str
    operation_id: str | None
    summary: str
    description: str
    tags: list[str]
    deprecated: bool
    parameters: list[dict[str, Any]]
    request_body: dict[str, Any] | None
    responses: dict[str, Any]
    security: list[dict[str, Any]]
    servers: list[dict[str, Any]]


class OperationPage(BaseModel):
    items: list[OperationRead]
    total: int
    limit: int
    offset: int


def document_read(document: OpenAPIDocument) -> dict:
    return {
        "project_id": document.project_id, "title": document.title,
        "api_version": document.api_version, "openapi_version": document.openapi_version,
        "imported_at": document.imported_at, "operation_count": len(document.operations),
        "tags": sorted({tag for op in document.operations for tag in op["tags"]}),
    }


@router.get("/openapi", response_model=DocumentRead | None)
def get_document(project_id: UUID, session: DatabaseSession):
    find_project(project_id, session)
    document = session.get(OpenAPIDocument, str(project_id))
    return document_read(document) if document else None


@router.put("/openapi", response_model=DocumentRead)
def import_document(project_id: UUID, payload: ImportInput, session: DatabaseSession):
    find_project(project_id, session)
    try:
        spec, operations = parse_openapi(payload.content)
    except ImportError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    document = session.get(OpenAPIDocument, str(project_id))
    if document is None:
        document = OpenAPIDocument(project_id=str(project_id))
        session.add(document)
    document.title = spec["info"]["title"]
    document.api_version = spec["info"]["version"]
    document.openapi_version = spec["openapi"]
    document.imported_at = utc_now()
    document.spec = spec
    document.operations = operations
    session.commit()
    return document_read(document)


@router.get("/operations", response_model=OperationPage)
def list_operations(
    project_id: UUID, session: DatabaseSession,
    method: str | None = None, tag: str | None = None,
    q: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    find_project(project_id, session)
    document = session.get(OpenAPIDocument, str(project_id))
    items = document.operations if document else []
    items = [op for op in items if (not method or op["method"] == method.upper())
             and (not tag or tag in op["tags"])
             and (not q or q.casefold() in f"{op['path']} {op['summary']} {op['operation_id'] or ''}".casefold())]
    return {"items": items[offset:offset + limit], "total": len(items), "limit": limit, "offset": offset}


@router.get("/operations/{operation_id}", response_model=OperationRead)
def get_operation(project_id: UUID, operation_id: UUID, session: DatabaseSession):
    find_project(project_id, session)
    document = session.get(OpenAPIDocument, str(project_id))
    if document:
        for operation in document.operations:
            if operation["id"] == str(operation_id):
                return operation
    raise HTTPException(status_code=404, detail="Operation not found")
