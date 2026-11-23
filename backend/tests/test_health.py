from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.main import create_app


@pytest.fixture
def application(tmp_path):
    return create_app(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")


@pytest.fixture
def client(application):
    with TestClient(application) as client:
        yield client


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "QualityOps Agent"


def test_api_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "qualityops-api"}


def test_database_health(client):
    response = client.get("/api/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "sqlite"}


def test_sqlite_can_persist_data(application):
    with application.state.engine.begin() as connection:
        connection.execute(text("CREATE TABLE probe (value TEXT NOT NULL)"))
        connection.execute(text("INSERT INTO probe VALUES ('persisted')"))
    with application.state.engine.connect() as connection:
        assert connection.execute(text("SELECT value FROM probe")).scalar_one() == "persisted"


def test_database_failure_is_service_unavailable(client):
    with patch("sqlalchemy.orm.Session.execute", side_effect=OperationalError("SELECT 1", {}, Exception("private failure"))):
        response = client.get("/api/health/db")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "sqlite"}
    assert "private failure" not in response.text
    assert client.get("/api/health").status_code == 200
