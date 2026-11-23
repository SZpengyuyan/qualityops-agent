import copy
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import OpenAPIDocument
from app.services.openapi import ImportError, parse_openapi


@pytest.fixture
def spec():
    return json.loads((Path(__file__).resolve().parents[2] / 'docs/examples/orders.openapi.json').read_text(encoding='utf-8'))


@pytest.fixture
def database_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'openapi.db').as_posix()}"


@pytest.fixture
def client(database_url):
    with TestClient(create_app(database_url)) as client:
        yield client


def project_path(client):
    project = client.post('/api/projects', json={'name': 'OpenAPI tests', 'base_url': 'http://localhost:9000'}).json()
    return f"/api/projects/{project['id']}"


def import_spec(client, path, spec):
    return client.put(path + '/openapi', json={'content': json.dumps(spec)})


@pytest.mark.parametrize('version', ['3.0.3', '3.1.0'])
def test_import_list_filter_detail(client, spec, version):
    spec['openapi'] = version
    path = project_path(client)
    assert client.get(path + '/openapi').json() is None
    assert client.get(path + '/operations').json()['total'] == 0
    response = import_spec(client, path, spec)
    assert response.status_code == 200, response.text
    assert response.json()['operation_count'] == 3
    assert response.json()['title'] == 'Orders Demo API'
    assert response.json()['tags'] == ['Orders']
    assert client.get(path + '/openapi').json() == response.json()
    page = client.get(path + '/operations?method=post&tag=Orders&q=createOrder&limit=1').json()
    assert page['total'] == 1
    operation = page['items'][0]
    assert operation['request_body']['required'] is True
    assert set(operation['responses']) == {'201', '409'}
    assert client.get(path + '/operations/' + operation['id']).json() == operation
    operations = client.get(path + '/operations?limit=1&offset=2').json()
    assert operations['items'][0]['parameters'][0]['name'] == 'order_id'
    assert operations['items'][0]['parameters'][0]['required'] is True
    assert client.get(path + '/operations?q=不存在').json()['total'] == 0


def test_parameter_override_and_security(spec):
    item = spec['paths']['/orders/{order_id}']
    item['get']['parameters'] = [{'name': 'order_id', 'in': 'path', 'required': True, 'description': 'override', 'schema': {'type': 'string'}}]
    spec['security'] = [{'bearer': []}]
    spec['components']['securitySchemes'] = {'bearer': {'type': 'http', 'scheme': 'bearer'}}
    _, operations = parse_openapi(json.dumps(spec))
    operation = operations[-1]
    assert len(operation['parameters']) == 1
    assert operation['parameters'][0]['description'] == 'override'
    assert operation['security'] == [{'bearer': []}]
    assert operation['servers'] == spec['servers']


def test_atomic_replacement_and_invalid_import_preserves_old(client, spec):
    path = project_path(client)
    assert import_spec(client, path, spec).status_code == 200
    original = client.get(path + '/operations').json()
    invalid = copy.deepcopy(spec)
    del invalid['info']
    assert import_spec(client, path, invalid).status_code == 422
    assert client.get(path + '/operations').json() == original
    spec['paths'] = {'/health': {'get': {'responses': {'200': {'description': 'healthy'}}}}}
    assert import_spec(client, path, spec).json()['operation_count'] == 1
    assert client.get(path + '/operations').json()['items'][0]['path'] == '/health'
    assert client.get(path + '/operations/' + original['items'][0]['id']).status_code == 404


@pytest.mark.parametrize('content', [
    'openapi: 3.0.3', '[]', '{"swagger":"2.0"}', '{"openapi":"3.2.0"}',
    '{"openapi":"3.0.3","openapi":"3.1.0"}', '{"openapi":"3.0.3","x-test":NaN}',
])
def test_reject_bad_formats(client, content):
    path = project_path(client)
    assert client.put(path + '/openapi', json={'content': content}).status_code == 422
    assert client.get(path + '/openapi').json() is None


@pytest.mark.parametrize('reference', ['https://example.com/schema.json', 'file:///etc/passwd', './schema.json', '#/components/missing'])
def test_reject_references_before_validator(spec, reference):
    spec['components']['schemas']['External'] = {'$ref': reference}
    with patch('app.services.openapi.OpenAPIV30SpecValidator') as validator:
        with pytest.raises(ImportError):
            parse_openapi(json.dumps(spec))
        validator.assert_not_called()


def test_internal_schema_recursion_remains_symbolic(spec):
    spec['components']['schemas']['Order']['properties']['child'] = {'$ref': '#/components/schemas/Order'}
    _, operations = parse_openapi(json.dumps(spec))
    assert operations[0]['responses']['200']['content']['application/json']['schema']['items']['$ref'] == '#/components/schemas/Order'


def test_bounds_and_schema_dialect(spec):
    with pytest.raises(ImportError, match='1 MiB'):
        parse_openapi(' ' * (1024 * 1024 + 1))
    spec['paths'] = {f'/item{i}': {'get': {'responses': {'200': {'description': 'OK'}}}} for i in range(501)}
    with pytest.raises(ImportError, match='500'):
        parse_openapi(json.dumps(spec))
    spec['$id'] = 'https://example.com'
    with pytest.raises(ImportError, match='Schema'):
        parse_openapi(json.dumps(spec))


def test_isolation_persistence_and_project_deletion(client, spec, database_url):
    first = project_path(client)
    second = project_path(client)
    import_spec(client, first, spec)
    assert client.get(second + '/openapi').json() is None
    assert client.get(second + '/operations').json()['total'] == 0
    with TestClient(create_app(database_url)) as restarted:
        assert restarted.get(first + '/openapi').json()['operation_count'] == 3
    assert client.delete(first).status_code == 204
    with client.app.state.session_factory() as session:
        assert session.get(OpenAPIDocument, first.split('/')[-1]) is None
    assert client.get(first + '/operations').status_code == 404


def test_not_found_and_pagination(client, spec):
    missing = f'/api/projects/{uuid4()}'
    assert import_spec(client, missing, spec).status_code == 404
    path = project_path(client)
    assert client.get(path + '/operations/' + str(uuid4())).status_code == 404
    assert client.get(path + '/operations?limit=0').status_code == 422
    assert client.get(path + '/operations?offset=-1').status_code == 422


@pytest.mark.parametrize('content', [
    '{"openapi":"3.0.3","x-number":1e10000}',
    '{"openapi":"3.0.3","x-number":' + '1' * 5000 + '}',
    '\ud800',
    r'{"openapi":"3.0.3","info":{"title":"\ud800","version":"1"},"paths":{}}',
])
def test_invalid_numeric_and_unicode_values_are_rejected(content):
    with pytest.raises(ImportError):
        parse_openapi(content)
