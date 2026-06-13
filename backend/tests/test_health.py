"""Phase 1 verification tests — health endpoints and app wiring."""

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health_returns_ok(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    from backend.config import get_settings

    assert body["version"] == get_settings().app_version
    assert body["environment"] == "dev"


def test_health_deep_reports_dependencies(client: TestClient) -> None:
    """Without containers running, deep check must degrade gracefully — never 500."""
    resp = client.get("/api/v1/health/deep")
    assert resp.status_code == 200
    body = resp.json()
    assert "dependencies" in body
    assert set(body["dependencies"].keys()) == {"redis", "postgres"}
    assert body["status"] in {"ok", "degraded"}


def test_openapi_docs_served(client: TestClient) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"] == "avatarforge API"


def test_unknown_route_404(client: TestClient) -> None:
    assert client.get("/api/v1/nonexistent").status_code == 404


def test_engines_listed():
    from fastapi.testclient import TestClient

    from backend.main import create_app

    client = TestClient(create_app())
    resp = client.get("/api/v1/avatar/engines")
    assert resp.status_code == 200
    body = resp.json()
    assert "sadtalker" in body["engines"]
    assert body["default"]


def test_root_serves_console():
    from fastapi.testclient import TestClient

    from backend.main import create_app

    client = TestClient(create_app())
    resp = client.get("/")
    # Either the console HTML (200) or a clean 404 JSON if not built — never a crash.
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        assert "avatarforge" in resp.text.lower()


def test_console_includes_architecture_view(client: TestClient) -> None:
    """The operator console ships the Architecture view (system-design tab)."""
    html = client.get("/").text
    assert "function Architecture" in html
    assert ">Architecture<" in html  # nav button
    assert "Engine registry" in html and "LangGraph pipeline" in html


def test_console_includes_assistant_view(client: TestClient) -> None:
    """The console ships the conversational Assistant with the memory panel."""
    html = client.get("/").text
    assert "function Assistant" in html and ">Assistant<" in html
    assert "Memory & preferences" in html and "/studio/chat" in html


def test_console_includes_characters_view(client: TestClient) -> None:
    """The console ships the Characters gallery (digital character assets)."""
    html = client.get("/").text
    assert "function Characters" in html and ">Characters<" in html
    assert "/characters/" in html
