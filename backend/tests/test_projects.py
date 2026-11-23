from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def database_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'projects.db').as_posix()}"


@pytest.fixture
def client(database_url):
    with TestClient(create_app(database_url)) as client:
        yield client


def payload(**overrides):
    return {"name": "Demo API", "description": "测试项目", "base_url": "http://127.0.0.1:9000", **overrides}


def test_project_crud(client):
    assert client.get("/api/projects").json() == {"items": [], "total": 0, "limit": 20, "offset": 0}
    response = client.post("/api/projects", json=payload(name="  Demo API  "))
    assert response.status_code == 201
    project = response.json()
    assert project["name"] == "Demo API"
    assert project["base_url"] == "http://127.0.0.1:9000/"
    assert project["created_at"].endswith("+00:00")
    path = f"/api/projects/{project['id']}"
    assert client.get(path).json() == project
    assert client.get("/api/projects").json()["total"] == 1
    response = client.put(path, json=payload(name="Updated", description=""))
    assert response.status_code == 200
    assert response.json()["name"] == "Updated"
    assert response.json()["created_at"] == project["created_at"]
    assert response.json()["updated_at"] >= project["updated_at"]
    assert client.get(path).json()["description"] == ""
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404
    assert client.get("/api/projects").json()["total"] == 0


@pytest.mark.parametrize("changes", [
    {"name": "  "}, {"name": "x" * 101}, {"description": "x" * 2001},
    {"base_url": "ftp://example.com"}, {"base_url": "not-a-url"},
    {"base_url": "https://user:secret@example.com"},
    {"base_url": "https://example.com?api_key=secret"},
    {"base_url": "https://example.com#fragment"}, {"unexpected": "value"},
    {"base_url": "https://example.com/" + "测" * 300},
])
def test_invalid_input_never_writes(client, changes):
    assert client.post("/api/projects", json=payload(**changes)).status_code == 422
    assert client.get("/api/projects").json()["total"] == 0


def test_missing_project_and_invalid_id(client):
    path = f"/api/projects/{uuid4()}"
    assert client.get(path).status_code == 404
    assert client.put(path, json=payload()).status_code == 404
    assert client.delete(path).status_code == 404
    assert client.get("/api/projects/not-a-uuid").status_code == 422


def test_pagination_and_validation(client):
    first = client.post("/api/projects", json=payload(name="First")).json()
    second = client.post("/api/projects", json=payload(name="Second")).json()
    page = client.get("/api/projects?limit=1&offset=0").json()
    assert page["total"] == 2
    assert page["items"][0]["id"] == second["id"]
    assert client.get("/api/projects?limit=1&offset=1").json()["items"][0]["id"] == first["id"]
    assert client.get("/api/projects?limit=0").status_code == 422
    assert client.get("/api/projects?offset=-1").status_code == 422


def test_project_survives_application_restart(database_url):
    with TestClient(create_app(database_url)) as first:
        project = first.post("/api/projects", json=payload()).json()
    with TestClient(create_app(database_url)) as second:
        assert second.get(f"/api/projects/{project['id']}").json() == project


def test_failed_update_preserves_existing_project(client):
    project = client.post("/api/projects", json=payload()).json()
    path = f"/api/projects/{project['id']}"
    assert client.put(path, json=payload(name="")).status_code == 422
    assert client.get(path).json() == project
