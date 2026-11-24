import asyncio
import copy
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.models import Execution, Project, SuiteRun, TestCase, TestSuite


@pytest.fixture
def database(tmp_path):
    return f"sqlite:///{(tmp_path / 'assets.db').as_posix()}"


@pytest.fixture
def client(database, monkeypatch):
    monkeypatch.setenv('QUALITYOPS_ALLOWED_ORIGINS', 'http://127.0.0.1:9000')
    with TestClient(create_app(database)) as client:
        yield client


def project(client):
    value = client.post('/api/projects', json={'name': 'Assets', 'base_url': 'http://127.0.0.1:9000'}).json()
    base = '/api/projects/' + value['id']
    spec = (Path(__file__).resolve().parents[2] / 'docs/examples/orders.openapi.json').read_text(encoding='utf-8')
    assert client.put(base + '/openapi', json={'content': spec}).status_code == 200
    operation = client.get(base + '/operations?method=POST').json()['items'][0]
    return base, operation


def case_payload(operation, name='正常创建', quantity=1, expected=201):
    return {'name': name, 'description': 'saved case', 'operation_id': operation['id'],
            'input': {'body': {'product_id': 'demo', 'quantity': quantity}, 'expected_status': expected,
                      'checks': [{'pointer': '/status', 'expected': 'created'}] if expected == 201 else [{'pointer': '/detail', 'expected': 'Insufficient stock'}]}}


def create_case(client, base, operation, **kwargs):
    response = client.post(base + '/test-cases', json=case_payload(operation, **kwargs))
    assert response.status_code == 201, response.text
    return response.json()


async def fake_perform(url, operation, payload):
    status = 409 if payload.body['quantity'] > 3 else 201
    passed = status == payload.expected_status
    return {'status': 'passed' if passed else 'failed', 'response': {'status_code': status, 'body': {'status': 'created'} if status == 201 else {'detail': 'Insufficient stock'}, 'is_json': True},
            'assertions': [{'type': 'status', 'passed': passed, 'expected': payload.expected_status, 'actual': status}], 'error': None, 'duration_ms': 1}


def test_case_crud_execution_and_restart(client, database):
    base, operation = project(client)
    case = create_case(client, base, operation)
    path = base + '/test-cases/' + case['id']
    assert client.get(path).json() == case
    assert len(client.get(base + '/test-cases').json()['items']) == 1
    with patch('app.routers.test_assets.perform', side_effect=fake_perform) as perform:
        record = client.post(path + '/execute').json()
    assert perform.call_count == 1
    assert record['status'] == 'passed'
    original = copy.deepcopy(record['request']['source_case'])
    assert client.put(path, json=case_payload(operation, name='修改后的用例')).status_code == 200
    assert client.get(base + '/executions/' + record['id']).json()['request']['source_case'] == original
    with TestClient(create_app(database)) as restarted:
        assert restarted.get(path).json()['name'] == '修改后的用例'
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404
    assert client.get(base + '/executions/' + record['id']).status_code == 200


def test_ordered_suite_repeat_and_immutable_snapshot(client):
    base, operation = project(client)
    normal = create_case(client, base, operation)
    negative = create_case(client, base, operation, name='库存不足', quantity=4, expected=409)
    payload = {'name': '订单回归', 'case_ids': [negative['id'], normal['id']]}
    response = client.post(base + '/test-suites', json=payload)
    assert response.status_code == 201
    suite = response.json()
    path = base + '/test-suites/' + suite['id']
    assert client.get(path).json()['case_ids'] == payload['case_ids']
    called = []
    async def execute(url, operation, payload):
        called.append(payload.body['quantity'])
        return await fake_perform(url, operation, payload)
    with patch('app.routers.test_assets.perform', side_effect=execute):
        first = client.post(path + '/run')
        second = client.post(path + '/run')
    assert first.status_code == second.status_code == 201, first.text
    run = first.json()
    assert called == [4, 1, 4, 1]
    assert run['status'] == 'passed'
    assert run['summary']['passed'] == 2
    assert [item['case_id'] for item in run['snapshot']] == payload['case_ids']
    assert all(item['execution']['status'] == 'passed' for item in run['results'])
    assert client.put(base + '/test-cases/' + normal['id'], json=case_payload(operation, name='改名')).status_code == 200
    assert client.put(path, json={'name': '改名回归', 'case_ids': [normal['id']]}).status_code == 200
    stored = client.get(base + '/suite-runs/' + run['id']).json()
    assert stored['snapshot'] == run['snapshot']
    assert stored['suite_name'] == '订单回归'
    assert client.get(base + '/suite-runs?limit=1&offset=1').json()['total'] == 2
    assert client.delete(base + '/test-cases/' + normal['id']).status_code == 409
    assert client.delete(path).status_code == 204
    assert client.get(base + '/suite-runs/' + run['id']).status_code == 200
    assert client.delete(base + '/test-cases/' + normal['id']).status_code == 204


def test_failures_continue_and_timeout_skips_remaining(client, monkeypatch):
    base, operation = project(client)
    first = create_case(client, base, operation, quantity=4)
    second = create_case(client, base, operation, name='第二条')
    suite = client.post(base + '/test-suites', json={'name': 'Mixed', 'case_ids': [first['id'], second['id']]}).json()
    path = base + '/test-suites/' + suite['id'] + '/run'
    with patch('app.routers.test_assets.perform', side_effect=fake_perform):
        result = client.post(path).json()
    assert result['status'] == 'failed'
    assert result['summary']['failed'] == result['summary']['passed'] == 1
    monkeypatch.setattr('app.routers.test_assets.SUITE_TIMEOUT_SECONDS', 0.02)
    async def slow(*args):
        await asyncio.sleep(1)
    with patch('app.routers.test_assets.perform', side_effect=slow) as perform:
        result = client.post(path).json()
    assert result['status'] == 'error'
    assert result['summary']['error'] == result['summary']['skipped'] == 1
    assert perform.call_count == 1


def test_preflight_and_cross_project_rejection(client):
    base, operation = project(client)
    other, _ = project(client)
    case = create_case(client, base, operation)
    suite = client.post(base + '/test-suites', json={'name': 'Suite', 'case_ids': [case['id']]}).json()
    assert client.get(other + '/test-cases/' + case['id']).status_code == 404
    assert client.post(other + '/test-suites', json={'name': 'Cross', 'case_ids': [case['id']]}).status_code == 404
    assert client.get(other + '/test-suites/' + suite['id']).status_code == 404
    assert client.post(base + '/test-suites', json={'name': 'Duplicate', 'case_ids': [case['id'], case['id']]}).status_code == 422
    changed = {'openapi': '3.0.3', 'info': {'title': 'Changed', 'version': '1'}, 'paths': {'/orders': {'post': {'summary': 'changed', 'responses': {'201': {'description': 'OK'}}}}}}
    assert client.put(base + '/openapi', json={'content': json.dumps(changed)}).status_code == 200
    with patch('app.routers.test_assets.perform') as perform:
        assert client.post(base + '/test-cases/' + case['id'] + '/execute').status_code == 422
        assert client.post(base + '/test-suites/' + suite['id'] + '/run').status_code == 422
        perform.assert_not_called()
    assert client.get(base + '/suite-runs').json()['total'] == 0


def test_project_cleanup_and_restart_interruption(client, database):
    base, operation = project(client)
    case = create_case(client, base, operation)
    suite = client.post(base + '/test-suites', json={'name': 'Suite', 'case_ids': [case['id']]}).json()
    with client.app.state.session_factory() as session:
        run = SuiteRun(project_id=base.split('/')[-1], suite_id=suite['id'], suite_name='Suite', status='running', snapshot=[], results=[{'case_id': case['id'], 'name': case['name'], 'status': 'running', 'execution_id': None}])
        session.add(run)
        session.commit()
        run_id = run.id
    assert client.delete(base).status_code == 409
    assert client.delete(base + '/test-suites/' + suite['id']).status_code == 409
    with patch('app.routers.test_assets.perform') as perform:
        assert client.post(base + '/test-suites/' + suite['id'] + '/run').status_code == 409
        perform.assert_not_called()
    with TestClient(create_app(database)) as restarted:
        result = restarted.get(base + '/suite-runs/' + run_id).json()
        assert result['status'] == 'interrupted'
        assert result['results'][0]['status'] == 'error'
    assert client.delete(base).status_code == 204
    with client.app.state.session_factory() as session:
        for model in (Execution, TestCase, TestSuite, SuiteRun):
            assert session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize('changes', [{'name': ' '}, {'operation_id': str(uuid4())}, {'input': {'expected_status': 99}}, {'input': {'path_params': {'extra': '1'}}}])
def test_invalid_cases_do_not_write(client, changes):
    base, operation = project(client)
    response = client.post(base + '/test-cases', json={**case_payload(operation), **changes})
    assert response.status_code in (404, 422)
    assert client.get(base + '/test-cases').json()['items'] == []


def test_empty_suite_and_run_scope(client):
    base, operation = project(client)
    other, _ = project(client)
    suite = client.post(base + '/test-suites', json={'name': 'Empty'}).json()
    assert client.post(base + '/test-suites/' + suite['id'] + '/run').status_code == 422
    assert client.get(base + '/suite-runs/' + str(uuid4())).status_code == 404
    assert client.get(other + '/suite-runs?limit=0').status_code == 422


def test_component_changes_require_resave_but_identical_import_does_not(client):
    base, operation = project(client)
    case = create_case(client, base, operation)
    spec_path = Path(__file__).resolve().parents[2] / 'docs/examples/orders.openapi.json'
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    client.put(base + '/openapi', json={'content': json.dumps(spec, sort_keys=True)})
    with patch('app.routers.test_assets.perform', side_effect=fake_perform):
        assert client.post(base + '/test-cases/' + case['id'] + '/execute').status_code == 201
    spec['components']['schemas']['Order']['properties']['status']['description'] = 'Changed schema'
    client.put(base + '/openapi', json={'content': json.dumps(spec)})
    with patch('app.routers.test_assets.perform') as perform:
        assert client.post(base + '/test-cases/' + case['id'] + '/execute').status_code == 422
        perform.assert_not_called()
    assert client.put(base + '/test-cases/' + case['id'], json=case_payload(operation)).status_code == 200
    with patch('app.routers.test_assets.perform', side_effect=fake_perform):
        assert client.post(base + '/test-cases/' + case['id'] + '/execute').status_code == 201


def test_run_snapshots_mask_known_secrets(client):
    base, operation = project(client)
    payload = case_payload(operation)
    payload['input']['body']['token'] = 'private-test-value'
    payload['input']['checks'] = [{'pointer': '/token', 'expected': 'private-test-value'}]
    case = client.post(base + '/test-cases', json=payload).json()
    assert case['input']['body']['token'] == 'private-test-value'
    suite = client.post(base + '/test-suites', json={'name': 'Masked', 'case_ids': [case['id']]}).json()
    with patch('app.routers.test_assets.perform', side_effect=fake_perform):
        response = client.post(base + '/test-suites/' + suite['id'] + '/run')
    assert response.status_code == 201
    assert 'private-test-value' not in response.text


def test_inputs_and_base_url_are_frozen_before_first_request(client):
    base, operation = project(client)
    first = create_case(client, base, operation)
    second = create_case(client, base, operation, name='Negative', quantity=4, expected=409)
    suite = client.post(base + '/test-suites', json={'name': 'Frozen', 'case_ids': [first['id'], second['id']]}).json()
    received = []
    async def execute(url, operation, payload):
        received.append((url, payload.expected_status))
        if len(received) == 1:
            with client.app.state.session_factory() as session:
                case = session.get(TestCase, second['id'])
                case.input = {**case.input, 'expected_status': 201}
                project_record = session.get(Project, base.split('/')[-1])
                project_record.base_url = 'http://127.0.0.1:9000/changed'
                session.commit()
        return await fake_perform(url, operation, payload)
    with patch('app.routers.test_assets.perform', side_effect=execute):
        result = client.post(base + '/test-suites/' + suite['id'] + '/run').json()
    assert result['status'] == 'passed'
    assert received == [('http://127.0.0.1:9000/orders', 201), ('http://127.0.0.1:9000/orders', 409)]
    assert result['snapshot'][1]['input']['expected_status'] == 409
    assert client.get(base + '/test-cases/' + second['id']).json()['input']['expected_status'] == 201


def test_asset_and_suite_size_limits(client):
    base, operation = project(client)
    project_id = base.split('/')[-1]
    with client.app.state.session_factory() as session:
        session.add_all([TestCase(project_id=project_id, name='Limit ' + str(index), description='', operation_id=operation['id'], operation=operation, input={}) for index in range(100)])
        session.add_all([TestSuite(project_id=project_id, name='Limit ' + str(index), description='', case_ids=[]) for index in range(50)])
        session.commit()
    assert client.post(base + '/test-cases', json=case_payload(operation)).status_code == 409
    assert client.post(base + '/test-suites', json={'name': 'Too many'}).status_code == 409
    assert client.post(base + '/test-suites', json={'name': 'Too large', 'case_ids': [str(uuid4()) for _ in range(11)]}).status_code == 422
