"""PhantomAPI — Basic endpoint tests."""

import os
import pytest
from unittest.mock import MagicMock, patch
from httpx import ASGITransport, AsyncClient

# Force a known API key so auth tests are deterministic (not bypassed)
os.environ.setdefault("API_SECRET_KEY", "test-secret-key")

# Patch the browser engine BEFORE importing app.main so the lifespan
# never tries to launch a real browser during tests.
_mock_engine = MagicMock()
_mock_engine.start = MagicMock()
_mock_engine.chat = MagicMock(return_value="Hello! How can I help?")
_mock_engine.search_web = MagicMock(return_value=[])
_mock_engine.fetch_url = MagicMock(return_value={"title": "", "url": "", "tables": "", "content": ""})
_mock_engine.ready = MagicMock()
_mock_engine.ready.wait = MagicMock(return_value=True)

with patch("app.services.browser.engine", _mock_engine):
    from app.main import app

_TEST_KEY = os.environ["API_SECRET_KEY"]
_AUTH = {"Authorization": f"Bearer {_TEST_KEY}"}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_health_check(client):
    """GET / should return 200 with status running."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert data["service"] == "PhantomAPI"


@pytest.mark.anyio
async def test_list_models(client):
    """GET /v1/models should return model list."""
    response = await client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert len(data["data"]) > 0


@pytest.mark.anyio
async def test_chat_without_auth(client):
    """POST /v1/chat/completions without auth should return 401."""
    response = await client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Hello"}], "model": "gpt-4o-mini"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_responses_without_auth(client):
    """POST /v1/responses without auth should return 401."""
    response = await client.post(
        "/v1/responses",
        json={"input": "Hello", "model": "gpt-4o-mini"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_gui_redirect(client):
    """GET /gui should redirect to the static GUI."""
    response = await client.get("/gui", follow_redirects=False)
    assert response.status_code == 307


@pytest.mark.anyio
async def test_query_endpoints_without_auth(client):
    """GET and POST /query without auth should return 401."""
    res_get = await client.get("/query?query=test")
    assert res_get.status_code == 401

    res_post = await client.post("/query", json={"query": "test"})
    assert res_post.status_code == 401


@pytest.mark.anyio
async def test_chat_endpoint_without_auth(client):
    """POST /chat without auth should return 401."""
    response = await client.post("/chat", json={"message": "test"})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_query_missing_field_returns_422(client):
    """GET /query with no query param and POST /query with no body should return 422."""
    # Missing required 'query' param in GET -> FastAPI returns 422
    res_get = await client.get("/query", headers=_AUTH)
    assert res_get.status_code == 422

    # Missing required 'query' field in POST body -> FastAPI returns 422
    res_post = await client.post("/query", json={}, headers=_AUTH)
    assert res_post.status_code == 422


@pytest.mark.anyio
async def test_chat_empty_payload_returns_400(client):
    """POST /chat with auth but no message fields should return 400."""
    response = await client.post("/chat", json={}, headers=_AUTH)
    assert response.status_code == 400
