from __future__ import annotations

import os

os.environ.update(
    {
        "APP_ENV": "test",
        "SECRET_KEY": "test-secret-key-for-nazar",
        "DATABASE_URL": "sqlite:///./test_nazar.db",
        "SCHEDULER_ENABLED": "false",
        "SERPAPI_API_KEY": "",
        "YOU_API_KEY": "",
        # Explicit openai with no key keeps the default test run offline.
        # Ollama-specific tests monkeypatch the settings to a local provider.
        "LLM_PROVIDER": "openai",
        "LLM_BASE_URL": "https://api.openai.com/v1",
        "LLM_MODEL": "gpt-4o-mini",
        "LLM_API_KEY": "",
        "NEXCONN_APP_KEY": "",
        "NEXCONN_APP_SECRET": "",
        "NEXCONN_WEBHOOK_SECRET": "",
        "RATE_LIMIT_PER_MINUTE": "10000",
        "INTERNAL_API_TOKEN": "",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402,F401
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import rate_limiter  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    rate_limiter.reset()
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def register_user(
    client: TestClient,
    email: str = "asha@example.com",
    name: str = "Asha",
    password: str = "password123",
) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return {
        "token": data["access_token"],
        "user": data["user"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


@pytest.fixture
def user_a(client):
    return register_user(client, "asha@example.com", "Asha")


@pytest.fixture
def user_b(client):
    return register_user(client, "ravi@example.com", "Ravi")
