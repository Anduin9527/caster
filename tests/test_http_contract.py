"""Independent UI origins, versioned routing and generated contract guarantees."""

import pytest
from fastapi.testclient import TestClient

from aigc.api import create_app
from aigc.config import cors_origins
from aigc.store import Store


def test_versioned_and_legacy_routes_share_records_without_starting_workers(tmp_path):
    app = create_app(config={}, store=Store(tmp_path))
    client = TestClient(app)
    created = client.post(
        "/api/v1/characters", json={"id": "hero", "name": "Hero", "fixed_tags": []}
    )
    assert created.status_code == 201
    assert client.get("/characters").json() == client.get("/api/v1/characters").json()
    assert client.get("/health").json() == client.get("/api/v1/health").json()
    snapshot = client.get("/api/v1/production/snapshot?character_id=hero")
    assert snapshot.status_code == 200
    assert snapshot.json()["characters"][0]["id"] == "hero"
    assert snapshot.json()["jobs"] == []
    assert app.state.worker is None
    assert app.state.comfy is None


def test_openapi_publishes_only_versioned_routes_with_typed_read_models():
    app = create_app(config={})
    schema = app.openapi()
    assert all(path.startswith("/api/v1/") for path in schema["paths"])
    snapshot = schema["paths"]["/api/v1/production/snapshot"]["get"]
    assert snapshot["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProductionSnapshot"
    }
    assert "ProductionBatch" in schema["components"]["schemas"]
    assert app.state.store is None and app.state.comfy is None and app.state.agent is None


def test_cors_is_explicit_and_covers_preflight_errors_and_sse_headers(tmp_path):
    origin = "http://127.0.0.1:4173"
    app = create_app(config={"AIGC_CORS_ORIGINS": origin}, store=Store(tmp_path))
    client = TestClient(app)
    preflight = client.options(
        "/api/v1/characters",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type,Last-Event-ID",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    invalid = client.post("/api/v1/characters", json={}, headers={"Origin": origin})
    assert invalid.status_code == 422
    assert invalid.headers["access-control-allow-origin"] == origin
    assert "ETag" in invalid.headers["access-control-expose-headers"]
    denied = client.options(
        "/api/v1/characters",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers
    default = TestClient(create_app(config={}))
    assert (
        "access-control-allow-origin"
        not in default.get("/api/v1/health", headers={"Origin": origin}).headers
    )


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "https://*.example.com",
        "https://example.com/path",
        "https://user:password@example.com",
        "file:///tmp",
        "https://example.com?key=secret",
    ],
)
def test_cors_rejects_non_origin_configuration(value):
    with pytest.raises(ValueError, match="AIGC_CORS_ORIGINS"):
        cors_origins({"AIGC_CORS_ORIGINS": value})
