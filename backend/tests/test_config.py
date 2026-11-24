import pytest

from app.core.config import settings, validate_runtime_settings


def test_production_rejects_insecure_secret(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "secret_key", "short")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_runtime_settings()


def test_production_accepts_strong_secret(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "secret_key", "x" * 48)
    monkeypatch.setattr(settings, "internal_api_token", "internal-token")
    monkeypatch.setattr(settings, "nexconn_webhook_secret", "whsec")
    monkeypatch.setattr(settings, "frontend_url", "https://nazar.example.com")

    validate_runtime_settings()
