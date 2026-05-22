"""Shared fixtures for the image_query test suite."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import image_query as image_query_module
from api.routes.image_query import router as image_query_router
from api.services import auth, query_log, query_pipeline

# --- Anthropic client mock helpers -----------------------------------------


def _vision_response(payload: dict) -> SimpleNamespace:
    """Build a fake `client.messages.create(...)` return value.

    Matches the shape used in services/vision_extraction.py:
        message.content[0].text  -> JSON string.
    """
    return SimpleNamespace(
        content=[SimpleNamespace(text=json.dumps(payload))],
    )


def make_vision_client(payload: dict | None = None, *, raise_exc: Exception | None = None) -> MagicMock:
    """Return a mock Anthropic client whose `messages.create` returns `payload`."""
    client = MagicMock(name="AnthropicMock")
    if raise_exc is not None:
        client.messages.create.side_effect = raise_exc
    else:
        client.messages.create.return_value = _vision_response(payload or {})
    return client


# --- App / fixtures --------------------------------------------------------


@pytest.fixture
def fake_jwt_decoder():
    """Decode a JWT shaped as 'tier:user_id' for tests. Real impl uses PyJWT."""

    def decode(token: str) -> dict:
        if not token or ":" not in token:
            raise ValueError("bad test token")
        tier, user_id = token.split(":", 1)
        return {"tier": tier, "user_id": user_id}

    return decode


@pytest.fixture
def query_log_rows() -> list[dict]:
    rows: list[dict] = []
    return rows


@pytest.fixture
def text_query_responses() -> list[dict]:
    """Captured args from the /query runner so tests can assert against them."""
    captured: list[dict] = []
    return captured


@pytest.fixture
def app(fake_jwt_decoder, query_log_rows, text_query_responses) -> FastAPI:
    """Build a FastAPI app with the image_query router mounted and all
    dependency seams wired to in-memory fakes."""
    a = FastAPI()
    a.include_router(image_query_router)

    # Wire seams.
    auth.set_jwt_decoder(fake_jwt_decoder)

    def fake_runner(question: str, *, user_id: str, request_id: str) -> dict:
        text_query_responses.append(
            {"question": question, "user_id": user_id, "request_id": request_id}
        )
        return {
            "answer": f"<rag answer for: {question}>",
            "sources": [{"title": "Khan Academy: Quadratic Equations", "url": "https://example.test/khan/quad"}],
            "request_id": request_id,
        }

    query_pipeline.set_text_query_runner(fake_runner)

    def fake_log_writer(row: dict) -> None:
        query_log_rows.append(row)

    query_log.set_query_log_writer(fake_log_writer)

    return a


@pytest.fixture
def client_factory(app):
    """Returns a callable that builds a TestClient with the chosen vision mock."""

    def _make(vision_payload=None, *, raise_exc=None) -> TestClient:
        mock_client = make_vision_client(vision_payload, raise_exc=raise_exc)
        image_query_module.set_anthropic_client(mock_client)
        tc = TestClient(app)
        tc.vision_mock = mock_client  # type: ignore[attr-defined]
        return tc

    return _make


@pytest.fixture
def tiny_png_bytes() -> bytes:
    """A 1x1 PNG. The vision model is mocked, so contents don't matter."""
    # Smallest valid PNG (8 + 25 + 12 + 12 bytes).
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01"
        b"]\xcc\xdb\xc4"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def bearer(tier: str = "paying", user_id: str = "u_42") -> dict[str, str]:
    return {"Authorization": f"Bearer {tier}:{user_id}"}
