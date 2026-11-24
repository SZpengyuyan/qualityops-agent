import asyncio
import copy
import hashlib
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Execution, OpenAPIDocument, SuiteRun, TestCase, TestSuite, utc_now
from app.routers.executions import execution_read
from app.routers.openapi import get_operation
from app.routers.projects import DatabaseSession, find_project
from app.services.execution import ExecutionInput, build_url, input_snapshot, perform, redact

router = APIRouter(prefix='/api/projects/{project_id}', tags=['test-assets'])
SUITE_TIMEOUT_SECONDS = 30


class AssetInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default='', max_length=2000)


class CaseInput(AssetInput):
    operation_id: UUID
    input: ExecutionInput


class SuiteInput(AssetInput):
    case_ids: list[UUID] = Field(default_factory=list, max_length=10)

    @field_validator('case_ids')
    @classmethod
    def unique_cases(cls, values):
        if len(set(values)) != len(values):
            raise ValueError('A suite cannot contain duplicate cases')
        return values


def find_asset(model, asset_id, project_id, session):
    asset = session.get(model, str(asset_id))
    if asset is None or asset.project_id != str(project_id):
        raise HTTPException(status_code=404, detail='测试资产不存在或不属于当前项目。')
    return asset


def case_read(case):
    return {**{key: getattr(case, key) for key in ('id', 'project_id', 'name', 'description', 'operation_id', 'input', 'created_at', 'updated_at')},
            'operation': {key: case.operation[key] for key in ('id', 'method', 'path')}}


def suite_read(suite):
    return {key: getattr(suite, key) for key in ('id', 'project_id', 'name', 'description', 'case_ids', 'created_at', 'updated_at')}


def validate_input(base_url, operation, payload, *, running=False):
    try:
        return build_url(base_url, operation, payload, check_origin=running)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def prepare_case(case, project, session):
    operation = get_operation(UUID(project.id), UUID(case.operation_id), session)
    if catalog_snapshot(project.id, operation, session) != case.operation:
        raise HTTPException(status_code=422, detail='接口定义已变更，请编辑并重新保存相关用例。')
    payload = ExecutionInput.model_validate(case.input)
    url = validate_input(project.base_url, operation, payload, running=True)
    return copy.deepcopy(operation), payload, url


def catalog_snapshot(project_id, operation, session):
    document = session.get(OpenAPIDocument, str(project_id))
    digest = hashlib.sha256(json.dumps(document.spec, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    return {**copy.deepcopy(operation), '_document_hash': digest}


def snapshot_case(case, base_url, payload):
    return {'case_id': case.id, 'name': case.name, 'description': case.description,
            'operation_id': case.operation_id, 'method': case.operation['method'], 'path': case.operation['path'],
            'base_url': base_url, 'input': input_snapshot(payload), 'case_updated_at': case.updated_at}


def store_execution(project_id, operation, payload, result, snapshot, session):
    record = Execution(project_id=project_id, operation_id=operation['id'],
                       request=redact({'method': operation['method'], 'path': operation['path'],
                                       'path_params': payload.path_params, 'query_params': payload.query_params,
                                       'body': payload.body, 'source_case': snapshot}), **result)
    session.add(record)
    session.flush()
    return record


@router.get('/test-cases')
def list_cases(project_id: UUID, session: DatabaseSession):
    find_project(project_id, session)
    return {'items': [case_read(case) for case in session.scalars(select(TestCase).where(TestCase.project_id == str(project_id)).order_by(TestCase.created_at.desc(), TestCase.id)).all()]}


def write_case(project_id, payload, case, session):
    project = find_project(project_id, session)
    operation = get_operation(project_id, payload.operation_id, session)
    validate_input(project.base_url, operation, payload.input)
    case.name, case.description = payload.name, payload.description
    case.operation_id, case.operation = str(payload.operation_id), catalog_snapshot(project_id, operation, session)
    case.input = payload.input.model_dump()
    session.add(case)
    session.commit()
    return case_read(case)


@router.post('/test-cases', status_code=201)
def create_case(project_id: UUID, payload: CaseInput, session: DatabaseSession):
    find_project(project_id, session)
    if session.scalar(select(func.count()).select_from(TestCase).where(TestCase.project_id == str(project_id))) >= 100:
        raise HTTPException(status_code=409, detail='当前每个项目最多保存 100 条用例。')
    return write_case(project_id, payload, TestCase(project_id=str(project_id)), session)


@router.get('/test-cases/{case_id}')
def get_case(project_id: UUID, case_id: UUID, session: DatabaseSession):
    find_project(project_id, session)
    return case_read(find_asset(TestCase, case_id, project_id, session))


@router.put('/test-cases/{case_id}')
def update_case(project_id: UUID, case_id: UUID, payload: CaseInput, session: DatabaseSession):
    find_project(project_id, session)
    return write_case(project_id, payload, find_asset(TestCase, case_id, project_id, session), session)


@router.delete('/test-cases/{case_id}', status_code=204)
def delete_case(project_id: UUID, case_id: UUID, session: DatabaseSession):
    find_project(project_id, session)
    case = find_asset(TestCase, case_id, project_id, session)
    suites = session.scalars(select(TestSuite).where(TestSuite.project_id == str(project_id))).all()
    if any(str(case_id) in suite.case_ids for suite in suites):
        raise HTTPException(status_code=409, detail='用例仍被用例集引用，请先从用例集中移除。')
    session.delete(case)
    session.commit()
    return Response(status_code=204)


@router.post('/test-cases/{case_id}/execute', status_code=201)
async def execute_case(project_id: UUID, case_id: UUID, session: DatabaseSession):
    project = find_project(project_id, session)
    case = find_asset(TestCase, case_id, project_id, session)
    operation, payload, url = prepare_case(case, project, session)
    snapshot = snapshot_case(case, project.base_url, payload)
    session.rollback()
    result = await perform(url, operation, payload)
    find_project(project_id, session)
    record = store_execution(str(project_id), operation, payload, result, snapshot, session)
    session.commit()
    return execution_read(record)


@router.get('/test-suites')
def list_suites(project_id: UUID, session: DatabaseSession):
    find_project(project_id, session)
    return {'items': [suite_read(suite) for suite in session.scalars(select(TestSuite).where(TestSuite.project_id == str(project_id)).order_by(TestSuite.created_at.desc(), TestSuite.id)).all()]}


def write_suite(project_id, payload, suite, session):
    for case_id in payload.case_ids:
        find_asset(TestCase, case_id, project_id, session)
    suite.name, suite.description = payload.name, payload.description
    suite.case_ids = [str(case_id) for case_id in payload.case_ids]
    session.add(suite)
    session.commit()
    return suite_read(suite)


@router.post('/test-suites', status_code=201)
def create_suite(project_id: UUID, payload: SuiteInput, session: DatabaseSession):
    find_project(project_id, session)
    if session.scalar(select(func.count()).select_from(TestSuite).where(TestSuite.project_id == str(project_id))) >= 50:
        raise HTTPException(status_code=409, detail='当前每个项目最多保存 50 个用例集。')
    return write_suite(project_id, payload, TestSuite(project_id=str(project_id)), session)


@router.get('/test-suites/{suite_id}')
def get_suite(project_id: UUID, suite_id: UUID, session: DatabaseSession):
    find_project(project_id, session)
    return suite_read(find_asset(TestSuite, suite_id, project_id, session))


@router.put('/test-suites/{suite_id}')
def update_suite(project_id: UUID, suite_id: UUID, payload: SuiteInput, session: DatabaseSession):
    find_project(project_id, session)
    return write_suite(project_id, payload, find_asset(TestSuite, suite_id, project_id, session), session)


@router.delete('/test-suites/{suite_id}', status_code=204)
def delete_suite(project_id: UUID, suite_id: UUID, session: DatabaseSession):
    find_project(project_id, session)
    suite = find_asset(TestSuite, suite_id, project_id, session)
    if session.scalar(select(SuiteRun.id).where(SuiteRun.project_id == str(project_id), SuiteRun.suite_id == str(suite_id), SuiteRun.status == 'running')):
        raise HTTPException(status_code=409, detail='用例集正在执行，请等待完成后删除。')
    session.delete(suite)
    session.commit()
    return Response(status_code=204)


def run_read(run, session, *, detail=True):
    result = {key: getattr(run, key) for key in ('id', 'project_id', 'suite_id', 'suite_name', 'status', 'created_at', 'finished_at')}
    result['summary'] = {'total': len(run.results), **{status: sum(item['status'] == status for item in run.results) for status in ('passed', 'failed', 'error', 'skipped', 'pending', 'running')}}
    if detail:
        result['snapshot'] = run.snapshot
        ids = [item['execution_id'] for item in run.results if item.get('execution_id')]
        records = {record.id: execution_read(record) for record in session.scalars(select(Execution).where(Execution.project_id == run.project_id, Execution.id.in_(ids))).all()} if ids else {}
        result['results'] = [{**item, 'execution': records.get(item.get('execution_id'))} for item in run.results]
    return result


@router.post('/test-suites/{suite_id}/run', status_code=201)
async def run_suite(project_id: UUID, suite_id: UUID, session: DatabaseSession):
    project = find_project(project_id, session)
    suite = find_asset(TestSuite, suite_id, project_id, session)
    if not suite.case_ids:
        raise HTTPException(status_code=422, detail='用例集为空，请先添加用例。')
    prepared, snapshots = [], []
    for case_id in suite.case_ids:
        case = find_asset(TestCase, case_id, project_id, session)
        prepared.append(prepare_case(case, project, session))
        snapshots.append(snapshot_case(case, project.base_url, prepared[-1][1]))
    run = SuiteRun(project_id=str(project_id), suite_id=suite.id, suite_name=suite.name, status='running',
                   snapshot=snapshots, results=[{'case_id': item['case_id'], 'name': item['name'], 'status': 'pending', 'execution_id': None, 'error': None} for item in snapshots])
    session.add(run)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail='此项目已有运行中的用例集，请勿重复启动。') from None
    index = 0
    try:
        async with asyncio.timeout(SUITE_TIMEOUT_SECONDS):
            for index, (operation, payload, url) in enumerate(prepared):
                run.results = [{**item, 'status': 'running'} if position == index else item for position, item in enumerate(run.results)]
                session.commit()
                result = await perform(url, operation, payload)
                record = store_execution(str(project_id), operation, payload, result, snapshots[index], session)
                run.results = [{**item, 'status': result['status'], 'execution_id': record.id, 'error': result['error']} if position == index else item for position, item in enumerate(run.results)]
                session.commit()
    except TimeoutError:
        run.results = [{**item, 'status': 'error' if position == index else 'skipped', 'error': '用例集达到 30 秒总时限；远端操作结果可能未知，未自动重试。'} if item['status'] in {'running', 'pending'} else item for position, item in enumerate(run.results)]
    run.status = 'error' if any(item['status'] == 'error' for item in run.results) else 'failed' if any(item['status'] == 'failed' for item in run.results) else 'passed'
    run.finished_at = utc_now()
    session.commit()
    return run_read(run, session)


@router.get('/suite-runs')
def list_runs(project_id: UUID, session: DatabaseSession, limit: Annotated[int, Query(ge=1, le=100)] = 10, offset: Annotated[int, Query(ge=0)] = 0):
    find_project(project_id, session)
    where = SuiteRun.project_id == str(project_id)
    total = session.scalar(select(func.count()).select_from(SuiteRun).where(where))
    runs = session.scalars(select(SuiteRun).where(where).order_by(SuiteRun.created_at.desc(), SuiteRun.id).offset(offset).limit(limit)).all()
    return {'items': [run_read(run, session, detail=False) for run in runs], 'total': total}


@router.get('/suite-runs/{run_id}')
def get_run(project_id: UUID, run_id: UUID, session: DatabaseSession):
    find_project(project_id, session)
    return run_read(find_asset(SuiteRun, run_id, project_id, session), session)
