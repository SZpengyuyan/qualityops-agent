from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.models import Execution
from app.routers.openapi import get_operation
from app.routers.projects import DatabaseSession, find_project
from app.services.execution import ExecutionInput, build_url, perform, redact
from app.services.flow import CaseExecutionInput, reference_names

router = APIRouter(prefix='/api/projects/{project_id}', tags=['executions'])


def execution_read(execution):
    return {key: getattr(execution, key) for key in ('id', 'project_id', 'operation_id', 'status', 'request', 'response', 'assertions', 'error', 'duration_ms', 'created_at')}


@router.post('/operations/{operation_id}/execute', status_code=201)
async def execute_operation(project_id: UUID, operation_id: UUID, payload: ExecutionInput, session: DatabaseSession):
    project = find_project(project_id, session)
    operation = get_operation(project_id, operation_id, session)
    try:
        if reference_names(CaseExecutionInput.model_validate(payload.model_dump())):
            raise ValueError('单次接口发送不解析流程变量，请保存用例并放入用例集执行。')
        url = build_url(project.base_url, operation, payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    # Release the read transaction before waiting for the remote service.
    project_key = str(project_id)
    session.rollback()
    result = await perform(url, operation, payload)
    record = Execution(project_id=project_key, operation_id=str(operation_id),
                       request=redact({'method': operation['method'], 'path': operation['path'], 'path_params': payload.path_params, 'query_params': payload.query_params, 'body': payload.body}), **result)
    session.add(record)
    session.commit()
    return execution_read(record)


@router.get('/executions')
def list_executions(project_id: UUID, session: DatabaseSession,
                    limit: Annotated[int, Query(ge=1, le=100)] = 20,
                    offset: Annotated[int, Query(ge=0)] = 0):
    find_project(project_id, session)
    where = Execution.project_id == str(project_id)
    total = session.scalar(select(func.count()).select_from(Execution).where(where))
    records = session.scalars(select(Execution).where(where).order_by(Execution.created_at.desc(), Execution.id).offset(offset).limit(limit)).all()
    return {'items': [execution_read(record) for record in records], 'total': total, 'limit': limit, 'offset': offset}


@router.get('/executions/{execution_id}')
def get_execution(project_id: UUID, execution_id: UUID, session: DatabaseSession):
    find_project(project_id, session)
    record = session.get(Execution, str(execution_id))
    if record is None or record.project_id != str(project_id):
        raise HTTPException(status_code=404, detail='Execution not found')
    return execution_read(record)
