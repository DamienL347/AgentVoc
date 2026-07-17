"""Tests de l'exigence de signature HMAC sur les endpoints Vapi."""
import hashlib
import hmac

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.security import require_vapi_signature
from app.config import settings
from app.integrations.vapi_client import verify_vapi_signature

SECRET = "test-secret"
BODY   = b'{"message": {"type": "tool-calls"}}'


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "VAPI_WEBHOOK_SECRET", SECRET)

    app = FastAPI()

    @app.post("/protected", dependencies=[Depends(require_vapi_signature)])
    async def protected():
        return {"ok": True}

    return TestClient(app)


def test_valid_signature_accepted(client):
    response = client.post(
        "/protected",
        content=BODY,
        headers={"x-vapi-signature": _sign(BODY, SECRET)},
    )
    assert response.status_code == 200


def test_missing_signature_rejected(client):
    response = client.post("/protected", content=BODY)
    assert response.status_code == 401


def test_invalid_signature_rejected(client):
    response = client.post(
        "/protected",
        content=BODY,
        headers={"x-vapi-signature": _sign(BODY, "wrong-secret")},
    )
    assert response.status_code == 401


def test_tampered_body_rejected(client):
    response = client.post(
        "/protected",
        content=b'{"message": {"type": "hacked"}}',
        headers={"x-vapi-signature": _sign(BODY, SECRET)},
    )
    assert response.status_code == 401


def test_missing_secret_in_production_rejected(monkeypatch):
    monkeypatch.setattr(settings, "VAPI_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "APP_ENV", "production")

    app = FastAPI()

    @app.post("/protected", dependencies=[Depends(require_vapi_signature)])
    async def protected():
        return {"ok": True}

    response = TestClient(app).post("/protected", content=BODY)
    assert response.status_code == 503


def test_verify_signature_helper():
    assert verify_vapi_signature(BODY, _sign(BODY, SECRET), SECRET)
    assert not verify_vapi_signature(BODY, "deadbeef", SECRET)
