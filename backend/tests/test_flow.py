import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.execution import perform
from app.services.flow import CaseExecutionInput, collect_exports, reference_names, resolve_input


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('QUALITYOPS_ALLOWED_ORIGINS', 'http://127.0.0.1:9000')
    with TestClient(create_app(f"sqlite:///{(tmp_path / 'flow.db').as_posix()}")) as client:
        yield client


def setup_flow(client, *, producer_expected=201, extract=None):
    project = client.post('/api/projects', json={'name': 'Flow', 'base_url': 'http://127.0.0.1:9000'}).json()
    base = '/api/projects/' + project['id']
    spec = (Path(__file__).resolve().parents[2] / 'docs/examples/orders.openapi.json').read_text(encoding='utf-8')
    assert client.put(base + '/openapi', json={'content': spec}).status_code == 200
    operations = client.get(base + '/operations').json()['items']
    post = next(op for op in operations if op['method'] == 'POST')
    get = next(op for op in operations if op['path'] == '/orders/{order_id}')
    list_op = next(op for op in operations if op['method'] == 'GET' and op['path'] == '/orders')
    inputs = [
        {'name': 'Create', 'operation_id': post['id'], 'input': {'body': {'product_id': 'demo', 'quantity': 1}, 'expected_status': producer_expected, 'extract': {'order_id': '/id'} if extract is None else extract}},
        {'name': 'Query', 'operation_id': get['id'], 'input': {'path_params': {'order_id': '{{order_id}}'}, 'checks': [{'pointer': '/id', 'expected': '{{order_id}}'}]}},
        {'name': 'Independent', 'operation_id': list_op['id'], 'input': {}},
    ]
    cases = []
    for payload in inputs:
        response = client.post(base + '/test-cases', json=payload)
        assert response.status_code == 201, response.text
        cases.append(response.json())
    return base, cases, inputs


def create_suite(client, base, cases):
    response = client.post(base + '/test-suites', json={'name': 'Flow suite', 'case_ids': [case['id'] for case in cases]})
    assert response.status_code == 201, response.text
    return base + '/test-suites/' + response.json()['id'] + '/run'


def run_with_transport(client, path, handler):
    transport = httpx.MockTransport(handler)
    async def send(url, operation, payload):
        return await perform(url, operation, payload, transport)
    with patch('app.routers.test_assets.perform', side_effect=send):
        return client.post(path)


def test_create_extract_query_repeat_and_actual_snapshot(client):
    base, cases, inputs = setup_flow(client)
    path = create_suite(client, base, cases[:2])
    requests = []
    number = 0
    def handler(request):
        nonlocal number
        requests.append(str(request.url))
        if request.method == 'POST':
            number += 1
            return httpx.Response(201, json={'id': 'order-' + str(number), 'status': 'created'})
        return httpx.Response(200, json={'id': request.url.path.split('/')[-1]})
    first = run_with_transport(client, path, handler)
    second = run_with_transport(client, path, handler)
    assert first.status_code == second.status_code == 201
    a, b = first.json(), second.json()
    assert a['status'] == b['status'] == 'passed'
    assert requests == ['http://127.0.0.1:9000/orders', 'http://127.0.0.1:9000/orders/order-1', 'http://127.0.0.1:9000/orders', 'http://127.0.0.1:9000/orders/order-2']
    assert a['snapshot'][1]['input']['path_params']['order_id'] == '{{order_id}}'
    assert a['results'][0]['exports'] == {'order_id': 'order-1'}
    assert a['results'][1]['resolved_input']['path_params']['order_id'] == 'order-1'
    assert b['results'][1]['resolved_input']['checks'][0]['expected'] == 'order-2'
    assert a['results'][1]['execution']['request']['source_case']['template_input']['path_params']['order_id'] == '{{order_id}}'
    assert client.get(base + '/suite-runs/' + a['id']).json()['results'][1]['resolved_input'] == a['results'][1]['resolved_input']
    assert client.post(base + '/test-cases/' + cases[1]['id'] + '/execute').status_code == 422


@pytest.mark.parametrize('mode', ['failed', 'missing', 'null', 'object', 'oversize', 'partial'])
def test_failed_or_invalid_extraction_skips_dependents_but_runs_independent(client, mode):
    definitions = {'order_id': '/id', 'another': '/missing'} if mode == 'partial' else {'order_id': '/id'}
    base, cases, _ = setup_flow(client, producer_expected=200 if mode == 'failed' else 201, extract=definitions)
    path = create_suite(client, base, cases)
    called = []
    def handler(request):
        called.append(request.url.path)
        if request.method == 'POST':
            value = {'null': None, 'object': {}, 'oversize': 'x' * 5000}.get(mode, 'new-order')
            return httpx.Response(201, json={} if mode == 'missing' else {'id': value})
        return httpx.Response(200, json=[])
    result = run_with_transport(client, path, handler).json()
    assert called == ['/orders', '/orders']
    assert result['results'][1]['status'] == 'skipped'
    assert result['results'][1]['execution'] is None
    assert result['results'][0]['exports'] == {}
    assert result['results'][2]['status'] == 'passed'
    assert result['status'] == ('failed' if mode == 'failed' else 'error')


def test_dependency_validation_prevents_http_and_invalid_order(client):
    base, cases, _ = setup_flow(client)
    with patch('app.routers.test_assets.perform') as send:
        for ids in ([cases[1]['id']], [cases[1]['id'], cases[0]['id']]):
            response = client.post(base + '/test-suites', json={'name': 'Invalid', 'case_ids': ids})
            assert response.status_code == 422
        send.assert_not_called()
    producer = client.get(base + '/test-cases/' + cases[0]['id']).json()
    duplicate = client.post(base + '/test-cases', json={'name': 'Other producer', 'operation_id': producer['operation_id'], 'input': producer['input']}).json()
    assert client.post(base + '/test-suites', json={'name': 'Duplicate', 'case_ids': [cases[0]['id'], duplicate['id']]}).status_code == 422
    path = create_suite(client, base, cases[:2])
    assert client.put(base + '/test-cases/' + producer['id'], json={'name': producer['name'], 'operation_id': producer['operation_id'], 'input': {**producer['input'], 'extract': {}}}).status_code == 200
    with patch('app.routers.test_assets.perform') as send:
        assert client.post(path).status_code == 422
        send.assert_not_called()
    assert client.get(base + '/suite-runs').json()['total'] == 0


@pytest.mark.parametrize('payload', [
    {'body': 'prefix {{id}}'}, {'body': '{{}}'}, {'body': {'{{key}}': 'value'}},
    {'extract': {'1id': '/id'}}, {'extract': {'token': '/id'}}, {'extract': {'id': '/access_token'}},
    {'extract': {'id': 'id'}}, {'extract': {'id': '/~bad'}},
    {'extract': {f'id{i}': '/id' for i in range(11)}},
])
def test_invalid_templates_and_extraction_definitions(payload):
    with pytest.raises(ValueError):
        CaseExecutionInput.model_validate(payload)


def test_scalar_types_one_pass_and_bounded_resolution():
    payload = CaseExecutionInput(path_params={'id': '{{id}}'}, query_params={'q': '{{count}}', 'active': '{{active}}'},
                                 body={'quantity': '{{count}}', 'active': '{{active}}'}, checks=[{'pointer': '/ok', 'expected': '{{active}}'}])
    assert reference_names(payload) == {'id', 'count', 'active'}
    actual = resolve_input(payload, {'id': '{{untrusted}}', 'count': 3, 'active': False})
    assert actual.path_params['id'] == '{{untrusted}}'
    assert actual.query_params == {'q': '3', 'active': 'false'}
    assert actual.body == {'quantity': 3, 'active': False}
    assert actual.checks[0].expected is False
    with pytest.raises(ValueError, match='缺少'):
        resolve_input(payload, {})
    with pytest.raises(ValueError, match='64 KiB'):
        resolve_input(CaseExecutionInput(body=['{{x}}'] * 5000), {'x': 'x' * 4000})
    assert collect_exports({'zero': '/n', 'flag': '/b'}, {'status': 'passed', 'response': {'is_json': True, 'body': {'n': 0, 'b': False}}}) == {'zero': 0, 'flag': False}


def test_no_previous_run_value_is_reused_after_producer_failure(client):
    base, cases, _ = setup_flow(client)
    path = create_suite(client, base, cases[:2])
    def successful(request):
        return httpx.Response(201, json={'id': 'old-id'}) if request.method == 'POST' else httpx.Response(200, json={'id': 'old-id'})
    assert run_with_transport(client, path, successful).json()['status'] == 'passed'
    requests = []
    def failed(request):
        requests.append(request.method)
        return httpx.Response(500, json={'detail': 'failed'})
    result = run_with_transport(client, path, failed).json()
    assert requests == ['POST']
    assert result['status'] == 'failed'
    assert result['results'][1]['status'] == 'skipped'
    assert result['results'][1]['resolved_input'] is None


def test_single_producer_exports_and_raw_send_rejects_templates(client):
    base, cases, _ = setup_flow(client)
    transport = httpx.MockTransport(lambda request: httpx.Response(201, json={'id': 'single-id'}))
    async def send(url, operation, payload):
        return await perform(url, operation, payload, transport)
    with patch('app.routers.test_assets.perform', side_effect=send) as sender:
        response = client.post(base + '/test-cases/' + cases[0]['id'] + '/execute')
        assert response.status_code == 201
        assert response.json()['request']['source_case']['exports'] == {'order_id': 'single-id'}
        assert client.post(base + '/test-cases/' + cases[1]['id'] + '/execute').status_code == 422
        assert sender.call_count == 1
    with patch('app.routers.executions.perform') as sender:
        response = client.post(base + '/operations/' + cases[1]['operation_id'] + '/execute', json={'path_params': {'order_id': '{{order_id}}'}})
        assert response.status_code == 422
        sender.assert_not_called()


def test_resolved_validation_errors_do_not_echo_request_fields():
    payload = CaseExecutionInput(body={'padding': 'x' * 65000, 'value': '{{data}}', 'password': 'test-secret'})
    with pytest.raises(ValueError) as error:
        resolve_input(payload, {'data': 'x' * 480})
    assert 'test-secret' not in str(error.value)
    assert '无效' in str(error.value)
