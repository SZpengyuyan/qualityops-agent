import asyncio
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Execution
from app.services.execution import ExecutionInput, build_url, json_equal, perform


@pytest.fixture
def operation():
    return {'id': 'test', 'method': 'GET', 'path': '/items/{id}', 'parameters': [], 'request_body': None, 'security': []}


def test_url_uses_project_base_and_encodes_path(operation, monkeypatch):
    monkeypatch.setenv('QUALITYOPS_ALLOWED_ORIGINS', 'http://127.0.0.1:9000')
    value = build_url('http://127.0.0.1:9000/v1/', operation, ExecutionInput(path_params={'id': 'a/b?x=1'}))
    assert value == 'http://127.0.0.1:9000/v1/items/a%2Fb%3Fx%3D1'
    with pytest.raises(ValueError, match='获准'):
        build_url('http://127.0.0.1:8000', operation, ExecutionInput(path_params={'id': 'a'}))
    with pytest.raises(ValueError, match='路径参数'):
        build_url('http://127.0.0.1:9000', operation, ExecutionInput())
    with pytest.raises(ValueError):
        build_url('http://127.0.0.1:9000', operation, ExecutionInput(path_params={'id': '..'}))


def test_pass_fail_and_json_pointer(operation):
    payload = ExecutionInput(checks=[{'pointer': '/a~1b/0/~0key', 'expected': True}])
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'a/b': [{'~key': True}]}))
    result = asyncio.run(perform('http://demo/items', operation, payload, transport))
    assert result['status'] == 'passed'
    assert len(result['assertions']) == 2
    payload.expected_status = 201
    assert asyncio.run(perform('http://demo/items', operation, payload, transport))['status'] == 'failed'
    assert not json_equal({'value': True}, {'value': 1})
    assert json_equal(1, 1.0)


def test_missing_pointer_text_and_redirects(operation):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(302, text='redirect', headers={'Location': 'http://127.0.0.1:8000'})
    result = asyncio.run(perform('http://demo/items', operation, ExecutionInput(checks=[{'pointer': '/missing', 'expected': None}]), httpx.MockTransport(handler)))
    assert len(requests) == 1
    assert result['status'] == 'failed'
    assert result['assertions'][1]['passed'] is False
    assert result['response']['is_json'] is False


@pytest.mark.parametrize('kind', ['timeout', 'connect', 'oversize', 'compressed'])
def test_network_errors_and_response_limits(operation, kind):
    async def handler(request):
        if kind == 'timeout':
            await asyncio.sleep(0.2)
        if kind == 'connect':
            raise httpx.ConnectError('private address', request=request)
        if kind == 'compressed':
            return httpx.Response(200, headers={'Content-Encoding': 'gzip'}, content=b'')
        return httpx.Response(200, content=b'x' * (256 * 1024 + 1))
    result = asyncio.run(perform('http://demo/items', operation, ExecutionInput(timeout_seconds=0.1), httpx.MockTransport(handler)))
    assert result['status'] == 'error'
    assert result['error']
    assert 'private address' not in result['error']


def test_secret_json_fields_are_masked(operation):
    payload = ExecutionInput(checks=[{'pointer': '/token', 'expected': 'private-token'}])
    result = asyncio.run(perform('http://demo/items', operation, payload, httpx.MockTransport(lambda request: httpx.Response(200, json={'token': 'private-token'}))))
    assert result['status'] == 'passed'
    assert 'private-token' not in json.dumps(result)


def test_execution_route_history_isolation_and_cleanup(tmp_path, monkeypatch):
    monkeypatch.setenv('QUALITYOPS_ALLOWED_ORIGINS', 'http://127.0.0.1:9000')
    database = f"sqlite:///{(tmp_path / 'execution.db').as_posix()}"
    with TestClient(create_app(database)) as client:
        project_input = {'name': 'Execution tests', 'base_url': 'http://127.0.0.1:9000'}
        project = client.post('/api/projects', json=project_input).json()
        second = client.post('/api/projects', json=project_input).json()
        base = f"/api/projects/{project['id']}"
        spec = (Path(__file__).resolve().parents[2] / 'docs/examples/orders.openapi.json').read_text(encoding='utf-8')
        assert client.put(base + '/openapi', json={'content': spec}).status_code == 200
        operation = client.get(base + '/operations?method=POST').json()['items'][0]
        transport = httpx.MockTransport(lambda request: httpx.Response(201, json={'status': 'created'}))
        original = perform
        async def mocked(url, operation, payload):
            return await original(url, operation, payload, transport)
        with patch('app.routers.executions.perform', side_effect=mocked):
            response = client.post(base + f"/operations/{operation['id']}/execute", json={'body': {'product_id': 'demo', 'quantity': 1}, 'expected_status': 201, 'checks': [{'pointer': '/status', 'expected': 'created'}]})
        assert response.status_code == 201, response.text
        record = response.json()
        assert record['status'] == 'passed'
        assert client.get(base + '/executions').json()['total'] == 1
        assert client.get(base + '/executions/' + record['id']).json() == record
        assert client.get(f"/api/projects/{second['id']}/executions/{record['id']}").status_code == 404
        assert client.put(base, json={**project_input, 'name': 'Updated'}).status_code == 200
        assert client.get(base + '/executions').json()['total'] == 1
        with TestClient(create_app(database)) as restarted:
            assert restarted.get(base + '/executions').json()['total'] == 1
        assert client.delete(base).status_code == 204
        with client.app.state.session_factory() as session:
            assert session.get(Execution, record['id']) is None


def test_input_limits_and_unsupported_requests(operation):
    with pytest.raises(ValueError):
        ExecutionInput(body={'n': float('nan')})
    with pytest.raises(ValueError):
        ExecutionInput(body='x' * 70000)
    with pytest.raises(ValueError):
        ExecutionInput(checks=[{'pointer': 'invalid', 'expected': None}])
    with pytest.raises(ValueError):
        build_url('http://127.0.0.1:9000', operation, ExecutionInput(path_params={'id': '1'}, body={}))


def test_demo_service():
    location = Path(__file__).resolve().parents[2] / 'demo-api/main.py'
    module_spec = importlib.util.spec_from_file_location('qualityops_demo', location)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    with TestClient(module.create_app()) as client:
        assert client.get('/health').json()['status'] == 'ok'
        response = client.post('/orders', json={'product_id': 'p1', 'quantity': 1})
        assert response.status_code == 201
        assert client.get('/orders/' + response.json()['id']).json()['status'] == 'created'
        assert len(client.get('/orders').json()) == 1
        assert client.post('/orders', json={'product_id': 'p1', 'quantity': 4}).status_code == 409
        assert client.post('/orders', json={'product_id': 'p1', 'quantity': 0}).status_code == 422
        assert client.get('/orders/missing').status_code == 404


def test_optional_authentication_and_required_parameters(operation, monkeypatch):
    monkeypatch.setenv('QUALITYOPS_ALLOWED_ORIGINS', 'http://127.0.0.1:9000')
    operation['security'] = [{'bearer': []}, {}]
    payload = ExecutionInput(path_params={'id': '1'})
    assert build_url('http://127.0.0.1:9000', operation, payload).endswith('/items/1')
    operation['security'] = [{'bearer': []}]
    with pytest.raises(ValueError, match='认证'):
        build_url('http://127.0.0.1:9000', operation, payload)
    operation['security'] = []
    operation['parameters'] = [{'name': 'limit', 'in': 'query', 'required': True}]
    with pytest.raises(ValueError, match='查询参数'):
        build_url('http://127.0.0.1:9000', operation, payload)
    operation['parameters'] = []
    operation['method'] = 'TRACE'
    with pytest.raises(ValueError, match='HTTP 方法'):
        build_url('http://127.0.0.1:9000', operation, payload)


def test_http_request_serialization(operation):
    operation['method'] = 'POST'
    received = []
    def handler(request):
        received.append(request)
        assert request.method == 'POST'
        assert request.url.params['q'] == 'a b&c'
        assert json.loads(request.content) == {'quantity': 2}
        return httpx.Response(201, json={'ok': True})
    result = asyncio.run(perform('http://demo/items/encoded', operation, ExecutionInput(query_params={'q': 'a b&c'}, body={'quantity': 2}, expected_status=201), httpx.MockTransport(handler)))
    assert result['status'] == 'passed'
    assert len(received) == 1
