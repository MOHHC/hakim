from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] in ("ok", "degraded")


def test_health_probe_reports_dead_providers_as_degraded(monkeypatch):
    from app.core import llm_client

    async def _all_down(force: bool = False):
        return {
            "gemini": llm_client.ProviderStatus(False, "gemini-2.5-flash: HTTP 403"),
            "groq": llm_client.ProviderStatus(False, "llama: HTTP 404"),
        }

    monkeypatch.setattr(llm_client, "probe_providers", _all_down)
    monkeypatch.setattr("app.config.settings.gemini_api_key", "k")
    body = client.get("/api/health?probe=true").json()
    assert body["status"] == "degraded"
    assert body["components"]["llm"]["status"] == "error"
    assert "403" in body["components"]["llm_gemini"]["detail"]
